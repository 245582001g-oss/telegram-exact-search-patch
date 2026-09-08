#Requires -Version 5.1
# Shared helpers for the explicit-path install and restore scripts.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Use the same release manifest as the builder; refuse missing or malformed data.
$CompatibilityPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'compatibility.json'
$Compatibility = Get-Content -LiteralPath $CompatibilityPath -Raw | ConvertFrom-Json
$TelegramVersion = [string] $Compatibility.telegram_version
$OriginalSha256 = [string] $Compatibility.input_sha256
$PatchedSha256 = [string] $Compatibility.verified_output_sha256
if ($Compatibility.platform -cne 'windows-x64' -or
    $Compatibility.input_filename -cne 'Telegram.exe' -or
    $TelegramVersion -notmatch '\A[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?\z' -or
    $OriginalSha256 -notmatch '\A[0-9a-fA-F]{64}\z' -or
    $PatchedSha256 -notmatch '\A[0-9a-fA-F]{64}\z' -or
    $OriginalSha256 -ieq $PatchedSha256) {
    throw 'Invalid compatibility.json: expected one exact Windows x64 release and distinct SHA256 hashes.'
}

function Get-PatchBackupPath {
    param([string] $TargetPath)
    # Never reuse the unversioned backup or a backup from another Telegram release.
    return $TargetPath + '.before-chinese-search.' + $TelegramVersion + '.bak'
}

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
    # A junction or other path alias can make the Telegram updater appear elsewhere.
    # Conservatively refuse every Updater.exe; never infer safety from unequal paths.
    if (@(Get-Process -Name Updater -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'A running Updater process may be the Telegram updater (including a path alias); wait for it to finish or exit it, then retry.'
    }
}

function Open-VerifiedPatchReadHandle {
    param([string] $FilePath, [string] $Expected)
    $reader = $null
    $sha256 = $null
    try {
        # Hold through process creation so the checked image cannot be rewritten or replaced.
        $reader = [IO.File]::Open($FilePath, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $sha256 = [Security.Cryptography.SHA256]::Create()
        $actual = [BitConverter]::ToString($sha256.ComputeHash($reader)).Replace('-', '')
        if ($actual -ine $Expected) {
            throw ('SHA256 mismatch; refusing this file: {0}. Expected {1}; got {2}.' -f
                $FilePath, $Expected, $actual)
        }
        $reader.Position = 0
        return $reader
    } catch {
        if ($null -ne $reader) { $reader.Dispose() }
        throw
    } finally {
        if ($null -ne $sha256) { $sha256.Dispose() }
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
