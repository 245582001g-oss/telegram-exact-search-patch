#Requires -Version 5.1
# Shared helpers for the explicit-path install and restore scripts.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$OriginalSha256 = '24b0715d9b74374c1d70c9f9537f631d45c51d08a520f3a9a8b9e5df92ad169b'
$PatchedSha256 = '894b04982521932a159397872604e0c96c9bd0bd8d48643f4a245899ea0a29c0'

function Resolve-PatchFilePath {
    param([string] $Value, [string] $RequiredName)
    if ([string]::IsNullOrWhiteSpace($Value) -or
        ($Value -notmatch '^[A-Za-z]:[\\/]' -and $Value -notmatch '^\\\\[^\\]+\\[^\\]+[\\/]')) {
        throw 'A fully qualified Windows file path is required.'
    }
    $resolved = [System.IO.Path]::GetFullPath($Value)
    if ($RequiredName -and [System.IO.Path]::GetFileName($resolved) -ine $RequiredName) {
        throw ('Path must name {0}.' -f $RequiredName)
    }
    $item = Get-Item -LiteralPath $resolved -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw ('Expected a regular file, not a directory or file link: {0}' -f $resolved)
    }
    return $resolved
}

function Assert-PatchHash {
    param([string] $FilePath, [string] $Expected)
    $actual = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash
    if ($actual -ine $Expected) {
        throw ('SHA256 mismatch; refusing this file: {0}. Expected {1}; got {2}.' -f
            $FilePath, $Expected, $actual)
    }
}

function Assert-TelegramStopped {
    # Refuse while any normal Telegram.exe process exists. Never stop or start it.
    if (@(Get-Process -Name Telegram -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'Exit Telegram completely (including its tray icon), then run this script again.'
    }
}

function Open-PatchLock {
    param([string] $TargetPath)
    try {
        # Keep this empty sidecar after use: deleting it can break mutual exclusion.
        return [System.IO.File]::Open($TargetPath + '.chinese-search.lock',
            [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None)
    } catch [System.IO.IOException] {
        throw 'Another install or restore may be running, or the patch lock cannot be opened.'
    }
}

function Copy-VerifiedPatchFile {
    param([string] $Source, [string] $Destination, [string] $Expected)
    $reader = $null
    $writer = $null
    $created = $false
    try {
        # Do not allow the source to be rewritten or replaced while copying.
        $reader = [System.IO.File]::Open($Source, [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
        $writer = New-Object System.IO.FileStream($Destination,
            [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None, 65536, [System.IO.FileOptions]::WriteThrough)
        $created = $true
        $reader.CopyTo($writer)
        $writer.Flush($true)
        $writer.Dispose()
        $writer = $null
        $reader.Dispose()
        $reader = $null
        Assert-PatchHash $Destination $Expected
    } catch {
        if ($null -ne $writer) { $writer.Dispose(); $writer = $null }
        if ($null -ne $reader) { $reader.Dispose(); $reader = $null }
        if ($created) { [System.IO.File]::Delete($Destination) }
        throw
    } finally {
        if ($null -ne $writer) { $writer.Dispose() }
        if ($null -ne $reader) { $reader.Dispose() }
    }
}

function Replace-VerifiedPatchFile {
    param([string] $Source, [string] $Target, [string] $SourceHash, [string] $TargetHash)
    $temporary = $Target + '.chinese-search.tmp.' + [Guid]::NewGuid().ToString('N')
    try {
        Copy-VerifiedPatchFile $Source $temporary $SourceHash
        Assert-TelegramStopped
        Assert-PatchHash $Target $TargetHash
        # Same-directory, atomic replacement. Never fall back to delete-then-copy.
        # NullString is necessary for Windows PowerShell 5.1 File.Replace binding.
        [System.IO.File]::Replace($temporary, $Target, [NullString]::Value)
        Assert-PatchHash $Target $SourceHash
    } finally {
        if ([System.IO.File]::Exists($temporary)) { [System.IO.File]::Delete($temporary) }
    }
}
