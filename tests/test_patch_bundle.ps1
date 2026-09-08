#Requires -Version 5.1
# All test inputs and outputs are synthetic and remain under repository work/.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
. (Join-Path $repository 'tools\Patch.Bundle.ps1')
$fixtures = Join-Path $repository ('work\bundle-tests\' + [Guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $fixtures -Force)
$checks = New-Object 'System.Collections.Generic.List[string]'

function Assert-Check {
    param([bool] $Condition, [string] $Name)
    if (-not $Condition) { throw ('FAIL: ' + $Name) }
    $checks.Add($Name)
}

function Get-BytesHash {
    param([byte[]] $Bytes)
    $stream = New-Object IO.MemoryStream(,$Bytes)
    try { return Get-PatchBundleHash $stream } finally { $stream.Dispose() }
}

function New-BundleFixture {
    param($Manifest = $script:manifest, [byte[]] $Literal = $script:literalBytes,
        [string] $ExtraEntry = '')
    $path = Join-Path $fixtures ([Guid]::NewGuid().ToString('N') + '.tgpatch')
    $file = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $zip = New-Object IO.Compression.ZipArchive($file, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        $entries = [ordered]@{
            'manifest.json' = [Text.Encoding]::UTF8.GetBytes(($Manifest | ConvertTo-Json -Depth 20 -Compress))
            'literal.bin' = $Literal
        }
        if ($ExtraEntry) { $entries.Add($ExtraEntry, [byte[]] @(1)) }
        foreach ($name in $entries.Keys) {
            $entry = $zip.CreateEntry($name, [IO.Compression.CompressionLevel]::Optimal)
            $writer = $entry.Open()
            try { $writer.Write($entries[$name], 0, $entries[$name].Length) } finally { $writer.Dispose() }
        }
    } finally { $zip.Dispose(); $file.Dispose() }
    return $path
}

function Copy-Manifest {
    return $manifest | ConvertTo-Json -Depth 20 | ConvertFrom-Json
}

function Assert-Refusal {
    param([string] $Bundle, [string] $Name, [string] $Message,
        [string] $Source = $script:sourcePath, [string] $BundleHash = '')
    if (-not $BundleHash) { $BundleHash = (Get-FileHash -LiteralPath $Bundle -Algorithm SHA256).Hash }
    $output = Join-Path $fixtures ([Guid]::NewGuid().ToString('N') + '.out')
    $refused = $false
    try {
        $null = Expand-TelegramPatchBundle -BundlePath $Bundle -SourcePath $Source -OutputPath $output -ExpectedBundleSha256 $BundleHash
    } catch { $refused = $_.Exception.Message -match $Message }
    Assert-Check ($refused -and -not (Test-Path -LiteralPath $output)) $Name
}

Assert-Check ($PSVersionTable.PSVersion.Major -eq 5) 'Actual Windows PowerShell 5.1 runtime'
$sourceBytes = [Text.Encoding]::ASCII.GetBytes('0123456789')
$literalBytes = [Text.Encoding]::ASCII.GetBytes('XY')
[byte[]] $expectedBytes = @(50, 51, 52, 88, 89, 0, 0, 0, 56, 57)
$sourcePath = Join-Path $fixtures 'original.fixture'
[IO.File]::WriteAllBytes($sourcePath, $sourceBytes)
$manifest = [ordered]@{
    schema = 1
    algorithm = 'telegram-exact-copy-data-zero-v1'
    telegram_version = '7.2.7'
    patch_revision = 'r4'
    input_sha256 = Get-BytesHash $sourceBytes
    output_sha256 = Get-BytesHash $expectedBytes
    input_length = $sourceBytes.Length
    output_length = $expectedBytes.Length
    literal_sha256 = Get-BytesHash $literalBytes
    literal_length = $literalBytes.Length
    operations = @(
        @{ op = 'copy'; offset = 2; length = 3 },
        @{ op = 'data'; offset = 0; length = 2 },
        @{ op = 'zero'; length = 3 },
        @{ op = 'copy'; offset = 8; length = 2 }
    )
}
$bundle = New-BundleFixture
$bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash
$output = Join-Path $fixtures 'valid.out'
$result = Expand-TelegramPatchBundle -BundlePath $bundle -SourcePath $sourcePath -OutputPath $output -ExpectedBundleSha256 $bundleHash
Assert-Check ((Get-FileHash -LiteralPath $output).Hash -ieq $manifest.output_sha256 -and
    $result.Sha256 -ceq $manifest.output_sha256 -and $result.Length -eq $expectedBytes.Length -and
    $result.TelegramVersion -ceq '7.2.7' -and $result.PatchRevision -ceq 'r4') 'COPY DATA ZERO reconstruct exact verified bytes and return profile metadata'

$beforeOutput = (Get-FileHash -LiteralPath $output).Hash
$refused = $false
try {
    $null = Expand-TelegramPatchBundle -BundlePath $bundle -SourcePath $sourcePath -OutputPath $output -ExpectedBundleSha256 $bundleHash
} catch { $refused = $_.Exception.Message -match 'Output already exists' }
Assert-Check ($refused -and (Get-FileHash -LiteralPath $output).Hash -eq $beforeOutput) 'Existing output is never overwritten'

Assert-Refusal $bundle 'Untrusted package hash is refused without a final output' 'Bundle SHA256 mismatch' -BundleHash ('0' * 64)
$unknown = Join-Path $fixtures 'unknown.fixture'
[IO.File]::WriteAllBytes($unknown, [Text.Encoding]::ASCII.GetBytes('9876543210'))
Assert-Refusal $bundle 'Same-length unknown source is refused' 'Input SHA256 mismatch' -Source $unknown
[IO.File]::WriteAllBytes($unknown, [byte[]] @(1))
Assert-Refusal $bundle 'Wrong source length is refused' 'Input length mismatch' -Source $unknown

$bad = Copy-Manifest
$bad.operations[0].offset = 9
Assert-Refusal (New-BundleFixture $bad) 'COPY source overrun is refused' 'source bounds'
$bad = Copy-Manifest
$bad.operations[1].offset = 1
Assert-Refusal (New-BundleFixture $bad) 'DATA literal overrun is refused' 'source bounds'
$bad = Copy-Manifest
$bad.operations[0].offset = -1
Assert-Refusal (New-BundleFixture $bad) 'Negative source offset is refused' 'integer or bounds'
$bad = Copy-Manifest
$bad.operations[0].length = 0
Assert-Refusal (New-BundleFixture $bad) 'Zero-length operation is refused' 'integer or bounds'
$bad = Copy-Manifest
$bad.operations[0].length = 2.5
Assert-Refusal (New-BundleFixture $bad) 'Fractional operation length is refused' 'integer or bounds'
$bad = Copy-Manifest
$bad.operations[0].op = 'execute'
Assert-Refusal (New-BundleFixture $bad) 'Unknown operation is refused instead of executed' 'Unsupported bundle operation'
$bad = Copy-Manifest
$bad.operations[0].op = @('copy', 'data')
Assert-Refusal (New-BundleFixture $bad) 'An operation name must be a single string' 'Invalid operation name'
$bad = Copy-Manifest
$bad.operations[0] | Add-Member -NotePropertyName command -NotePropertyValue 'never execute'
Assert-Refusal (New-BundleFixture $bad) 'Unexpected operation fields are refused' 'fields'
$bad = Copy-Manifest
$bad.output_length = 11
Assert-Refusal (New-BundleFixture $bad) 'Output operation sum mismatch is refused' 'output length mismatch'
$bad = Copy-Manifest
$bad.input_length = 1GB + 1
Assert-Refusal (New-BundleFixture $bad) 'Input size above the one GiB limit is refused' 'integer or bounds'
$bad = Copy-Manifest
$bad.literal_length = 16MB + 1
Assert-Refusal (New-BundleFixture $bad) 'Literal size above the sixteen MiB limit is refused' 'integer or bounds'
$bad = Copy-Manifest
$bad.literal_sha256 = '0' * 64
Assert-Refusal (New-BundleFixture $bad) 'Corrupt literal bytes are refused' 'Literal SHA256 mismatch'
$bad = Copy-Manifest
$bad.output_sha256 = '0' * 64
Assert-Refusal (New-BundleFixture $bad) 'Wrong reconstructed output hash cleans up the temporary output' 'Output length or SHA256 mismatch'
Assert-Refusal (New-BundleFixture -ExtraEntry '../unexpected.txt') 'Unexpected ZIP paths are refused without extraction' 'exactly manifest.json and literal.bin'
$invalidZip = Join-Path $fixtures 'invalid.tgpatch'
[IO.File]::WriteAllText($invalidZip, 'not a ZIP archive')
Assert-Refusal $invalidZip 'Malformed ZIP archive is refused without output' '.'

Assert-Check ((Get-FileHash -LiteralPath $sourcePath).Hash -ieq $manifest.input_sha256) 'Original source remains byte-identical across successful and failed applications'
Assert-Check (@(Get-ChildItem -LiteralPath $fixtures -Filter '*.tgpatch.tmp.*').Count -eq 0) 'No failed reconstruction temporary files remain'
$exclusive = [IO.File]::Open($sourcePath, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$exclusive.Dispose()
$exclusive = [IO.File]::Open($bundle, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$exclusive.Dispose()
Assert-Check $true 'Source and bundle handles are released after completion and refusal'
$checks | ForEach-Object { Write-Output ('PASS ' + $_) }
Write-Output ('TOTAL {0} checks passed. Synthetic fixtures retained: {1}' -f $checks.Count, $fixtures)
