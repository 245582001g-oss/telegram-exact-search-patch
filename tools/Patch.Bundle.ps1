#Requires -Version 5.1
# Data-only .tgpatch reader. Does not install, launch, download, or execute a bundle.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression

function Get-PatchBundleHash {
    param([IO.Stream] $Stream)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $Stream.Position = 0
        return [BitConverter]::ToString($sha.ComputeHash($Stream)).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Assert-PatchBundleKeys {
    param($Value, [string[]] $Keys, [string] $Label)
    if ($null -eq $Value -or $Value -isnot [pscustomobject]) { throw ('Invalid ' + $Label + ' object.') }
    $actualKeys = @($Value.PSObject.Properties.Name)
    if ($actualKeys.Count -ne $Keys.Count) { throw ('Invalid ' + $Label + ' fields.') }
    foreach ($key in $Keys) {
        if ($actualKeys -cnotcontains $key) { throw ('Missing ' + $Label + ' field: ' + $key) }
    }
}

function Assert-PatchBundleInteger {
    param($Value, [long] $Maximum, [string] $Label, [long] $Minimum = 0)
    if (($Value -isnot [int] -and $Value -isnot [long]) -or
        $Value -lt $Minimum -or $Value -gt $Maximum) {
        throw ('Invalid ' + $Label + ' integer or bounds.')
    }
}

function Read-PatchBundleEntry {
    param([IO.Compression.ZipArchiveEntry] $Entry, [long] $Maximum)
    if ($Entry.Length -lt 0 -or $Entry.Length -gt $Maximum) { throw ('ZIP entry is too large: ' + $Entry.FullName) }
    $bytes = New-Object byte[] ([int] $Entry.Length)
    $stream = $Entry.Open()
    try {
        $offset = 0
        while ($offset -lt $bytes.Length) {
            $count = $stream.Read($bytes, $offset, $bytes.Length - $offset)
            if ($count -le 0) { throw ('Truncated ZIP entry: ' + $Entry.FullName) }
            $offset += $count
        }
        if ($stream.ReadByte() -ne -1) { throw ('ZIP entry length mismatch: ' + $Entry.FullName) }
        return ,$bytes
    } finally { $stream.Dispose() }
}

function Resolve-PatchBundlePath {
    param([string] $Path, [switch] $NewFile)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        ($Path -notmatch '^[A-Za-z]:[\\/]' -and $Path -notmatch '^\\\\[^\\]+\\[^\\]+[\\/]')) {
        throw 'A fully qualified Windows file path is required.'
    }
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ($NewFile) {
        if (Test-Path -LiteralPath $fullPath) { throw ('Output already exists; refusing to overwrite: ' + $fullPath) }
        if (-not [IO.Directory]::Exists([IO.Path]::GetDirectoryName($fullPath))) { throw 'Output directory must already exist.' }
    } else {
        $item = Get-Item -LiteralPath $fullPath -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw ('Expected a regular file: ' + $fullPath)
        }
    }
    return $fullPath
}

function Expand-TelegramPatchBundle {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string] $BundlePath,
        [Parameter(Mandatory = $true)][string] $SourcePath,
        [Parameter(Mandatory = $true)][string] $OutputPath,
        [Parameter(Mandatory = $true)][string] $ExpectedBundleSha256
    )
    if ($ExpectedBundleSha256 -notmatch '\A[0-9a-fA-F]{64}\z') { throw 'Invalid expected bundle SHA256.' }
    $bundleFile = Resolve-PatchBundlePath $BundlePath
    $sourceFile = Resolve-PatchBundlePath $SourcePath
    $outputFile = Resolve-PatchBundlePath $OutputPath -NewFile
    $temporary = $outputFile + '.tgpatch.tmp.' + [Guid]::NewGuid().ToString('N')
    $bundle = $null
    $archive = $null
    $source = $null
    $writer = $null
    $temporaryCreated = $false
    try {
        # Pin the exact package whose hash the caller obtained from a trusted catalog.
        $bundle = [IO.File]::Open($bundleFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        if ($bundle.Length -gt 64MB) { throw 'Bundle exceeds the 64 MiB limit.' }
        if ((Get-PatchBundleHash $bundle) -ine $ExpectedBundleSha256) { throw 'Bundle SHA256 mismatch.' }
        $bundle.Position = 0
        $archive = New-Object IO.Compression.ZipArchive($bundle, [IO.Compression.ZipArchiveMode]::Read, $true)
        if ($archive.Entries.Count -ne 2 -or
            @($archive.Entries | Where-Object { $_.FullName -ceq 'manifest.json' }).Count -ne 1 -or
            @($archive.Entries | Where-Object { $_.FullName -ceq 'literal.bin' }).Count -ne 1) {
            throw 'Bundle must contain exactly manifest.json and literal.bin.'
        }
        $manifestBytes = Read-PatchBundleEntry ($archive.GetEntry('manifest.json')) 1MB
        $utf8 = New-Object Text.UTF8Encoding($false, $true)
        $manifest = $utf8.GetString($manifestBytes) | ConvertFrom-Json
        Assert-PatchBundleKeys $manifest @('schema', 'algorithm', 'telegram_version', 'patch_revision',
            'input_sha256', 'output_sha256', 'input_length', 'output_length',
            'literal_sha256', 'literal_length', 'operations') 'manifest'
        Assert-PatchBundleInteger $manifest.schema 1 'schema' 1
        if ($manifest.algorithm -isnot [string] -or $manifest.algorithm -cne 'telegram-exact-copy-data-zero-v1') {
            throw 'Unsupported bundle algorithm.'
        }
        if ($manifest.telegram_version -isnot [string] -or
            $manifest.telegram_version -notmatch '\A[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?\z' -or
            $manifest.patch_revision -isnot [string] -or
            $manifest.patch_revision -notmatch '\Ar[0-9]+\z') {
            throw 'Invalid bundle version or revision.'
        }
        foreach ($field in @('input_sha256', 'output_sha256', 'literal_sha256')) {
            if ($manifest.$field -isnot [string] -or $manifest.$field -cnotmatch '\A[0-9a-f]{64}\z') {
                throw ('Invalid bundle SHA256: ' + $field)
            }
        }
        Assert-PatchBundleInteger $manifest.input_length 1GB 'input_length' 1
        Assert-PatchBundleInteger $manifest.output_length 1GB 'output_length' 1
        Assert-PatchBundleInteger $manifest.literal_length 16MB 'literal_length'
        if ($manifest.operations -isnot [Array] -or $manifest.operations.Count -lt 1 -or
            $manifest.operations.Count -gt 4096) { throw 'Invalid operation list.' }
        [long] $outputLength = 0
        foreach ($operation in $manifest.operations) {
            if ($operation -isnot [pscustomobject] -or $null -eq $operation.PSObject.Properties['op']) {
                throw 'Invalid operation object.'
            }
            if ($operation.op -isnot [string]) { throw 'Invalid operation name.' }
            switch -CaseSensitive ($operation.op) {
                'copy' { $limit = [long] $manifest.input_length }
                'data' { $limit = [long] $manifest.literal_length }
                'zero' { $limit = 0 }
                default { throw 'Unsupported bundle operation.' }
            }
            if ($operation.op -ceq 'zero') {
                Assert-PatchBundleKeys $operation @('op', 'length') 'zero operation'
            } else {
                Assert-PatchBundleKeys $operation @('op', 'offset', 'length') ($operation.op + ' operation')
                Assert-PatchBundleInteger $operation.offset $limit 'operation offset'
            }
            Assert-PatchBundleInteger $operation.length 1GB 'operation length' 1
            if ($operation.op -cne 'zero' -and $operation.length -gt ($limit - $operation.offset)) {
                throw 'Operation source bounds exceeded.'
            }
            $outputLength += [long] $operation.length
            if ($outputLength -gt $manifest.output_length) { throw 'Operation output bounds exceeded.' }
        }
        if ($outputLength -ne $manifest.output_length) { throw 'Operation output length mismatch.' }
        $literal = Read-PatchBundleEntry ($archive.GetEntry('literal.bin')) 16MB
        if ($literal.Length -ne $manifest.literal_length) { throw 'Literal length mismatch.' }
        $literalStream = New-Object IO.MemoryStream(,$literal)
        try {
            if ((Get-PatchBundleHash $literalStream) -cne $manifest.literal_sha256) { throw 'Literal SHA256 mismatch.' }
        } finally { $literalStream.Dispose() }

        # Hash and copy from the same handle while external writes/replacements are denied.
        $source = [IO.File]::Open($sourceFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        if ($source.Length -ne $manifest.input_length) { throw 'Input length mismatch; unsupported source.' }
        if ((Get-PatchBundleHash $source) -cne $manifest.input_sha256) { throw 'Input SHA256 mismatch; unsupported source.' }
        $writer = New-Object IO.FileStream($temporary, [IO.FileMode]::CreateNew,
            [IO.FileAccess]::ReadWrite, [IO.FileShare]::None, 65536, [IO.FileOptions]::WriteThrough)
        $temporaryCreated = $true
        $buffer = New-Object byte[] 65536
        $zeroes = New-Object byte[] 65536
        foreach ($operation in $manifest.operations) {
            [long] $remaining = $operation.length
            [long] $position = 0
            if ($operation.op -ceq 'copy') { $source.Position = $operation.offset }
            while ($remaining -gt 0) {
                $count = [int] [Math]::Min([long] $buffer.Length, $remaining)
                switch -CaseSensitive ($operation.op) {
                    'copy' {
                        $count = $source.Read($buffer, 0, $count)
                        if ($count -le 0) { throw 'Unexpected end of source.' }
                        $writer.Write($buffer, 0, $count)
                    }
                    'data' { $writer.Write($literal, [int] ($operation.offset + $position), $count) }
                    'zero' { $writer.Write($zeroes, 0, $count) }
                }
                $position += $count
                $remaining -= $count
            }
        }
        $writer.Flush($true)
        if ($writer.Length -ne $manifest.output_length -or
            (Get-PatchBundleHash $writer) -cne $manifest.output_sha256) { throw 'Output length or SHA256 mismatch.' }
        $writer.Dispose()
        $writer = $null
        # Same-directory publication is atomic and never overwrites an existing file.
        [IO.File]::Move($temporary, $outputFile)
        $temporaryCreated = $false
        return [pscustomobject]@{
            OutputPath = $outputFile
            Sha256 = $manifest.output_sha256
            Length = [long] $manifest.output_length
            TelegramVersion = $manifest.telegram_version
            PatchRevision = $manifest.patch_revision
        }
    } finally {
        if ($null -ne $writer) { $writer.Dispose() }
        if ($null -ne $source) { $source.Dispose() }
        if ($null -ne $archive) { $archive.Dispose() }
        if ($null -ne $bundle) { $bundle.Dispose() }
        if ($temporaryCreated -and [IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}
