#Requires -Version 5.1
<#
.SYNOPSIS
Exercise the external patch manager with synthetic clients and mocked OS/network actions.
.DESCRIPTION
All files live beneath work/patch-manager-tests. No real Telegram is opened, patched,
or stopped. Downloads, process launches, process termination, and startup shortcuts
are replaced by fixture-only test doubles.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$fixtureRoot = Join-Path $repository ('work\patch-manager-tests\' + [Guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $fixtureRoot -Force)
$checks = New-Object 'System.Collections.Generic.List[string]'
Add-Type -AssemblyName System.IO.Compression

function Assert-ManagerCheck {
    param([bool] $Condition, [string] $Name)
    if (-not $Condition) { throw ('FAIL: ' + $Name) }
    $checks.Add($Name)
}

function Get-FixtureHash {
    param([string] $Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-FixtureByteHash {
    param([byte[]] $Bytes)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose() }
}

function New-ManagerFixture {
    param([string] $Name, [string] $Content = 'synthetic Telegram 7.2.7 original')
    $root = Join-Path $fixtureRoot $Name
    [void](New-Item -ItemType Directory -Path $root -Force)
    $app = Join-Path $root 'app'
    $runtime = Join-Path $root 'manager'
    [void](New-Item -ItemType Directory -Path $app -Force)
    [void](New-Item -ItemType Directory -Path $runtime -Force)
    $exe = Join-Path $app 'Telegram.exe'
    [IO.File]::WriteAllText($exe, $Content)
    $tdata = Join-Path $app 'tdata'
    [void](New-Item -ItemType Directory -Path $tdata -Force)
    $marker = Join-Path $tdata 'untouched.fixture'
    [IO.File]::WriteAllText($marker, 'synthetic account data marker; never read by manager')
    return [pscustomobject]@{Root=$root; App=$app; Runtime=$runtime; Exe=$exe; Marker=$marker}
}

function Write-FixtureBundle {
    param([string] $Path, [byte[]] $Source, [byte[]] $Literal)
    $output = New-Object byte[] ($Source.Length + $Literal.Length)
    [Array]::Copy($Source, 0, $output, 0, $Source.Length)
    [Array]::Copy($Literal, 0, $output, $Source.Length, $Literal.Length)
    $manifest = [ordered]@{
        schema=1; algorithm='telegram-exact-copy-data-zero-v1'
        telegram_version='7.2.7'; patch_revision='r4'
        input_sha256=(Get-FixtureByteHash $Source); output_sha256=(Get-FixtureByteHash $output)
        input_length=$Source.Length; output_length=$output.Length
        literal_sha256=(Get-FixtureByteHash $Literal); literal_length=$Literal.Length
        operations=@(
            [ordered]@{op='copy'; offset=0; length=$Source.Length},
            [ordered]@{op='data'; offset=0; length=$Literal.Length}
        )
    }
    $json = [Text.Encoding]::UTF8.GetBytes(($manifest | ConvertTo-Json -Depth 8 -Compress))
    $file = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $zip = New-Object IO.Compression.ZipArchive($file, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($entry in @(@{Name='manifest.json'; Bytes=$json}, @{Name='literal.bin'; Bytes=$Literal})) {
            $item = $zip.CreateEntry($entry.Name, [IO.Compression.CompressionLevel]::Optimal)
            $stream = $item.Open()
            try { $stream.Write($entry.Bytes, 0, $entry.Bytes.Length) } finally { $stream.Dispose() }
        }
    } finally { $zip.Dispose(); $file.Dispose() }
    return [pscustomobject]@{Manifest=$manifest; Hash=(Get-FixtureHash $Path); Bytes=$output}
}

Assert-ManagerCheck ($PSVersionTable.PSVersion.Major -eq 5) 'Uses real Windows PowerShell 5.1'

$managerPath = Join-Path $repository 'tools\Patch.Manager.ps1'
foreach ($name in @('Patch.Manager.ps1', 'Patch.Bundle.ps1')) {
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $repository ('tools\'+$name)), [ref]$tokens, [ref]$errors)
    Assert-ManagerCheck ($errors.Count -eq 0) ('PowerShell 5.1 syntax: '+$name)
}
. $managerPath

# Replace external effects after importing the real helper. Unexpected endpoints
# throw immediately; there is deliberately no network-capable fallback.
$script:NetworkMode = 'Normal'
$script:CatalogDownload = ''
$script:BundleDownloads = @{}
$script:Downloads = New-Object 'System.Collections.Generic.List[string]'
$script:ProcessNames = @()
$script:ProcessChecks = 0
$script:BusyAfterCheck = 0
$script:AlterTargetOnCheck = 0
$script:AlterTarget = ''
$script:Launches = New-Object 'System.Collections.Generic.List[string]'
$script:TestLaunchPin = $false
$script:LaunchWriteBlocked = $false
$script:LaunchReplaceBlocked = $false

function Receive-ManagerFile {
    param([string] $Url, [string] $Destination, [long] $MaximumBytes)
    $script:Downloads.Add($Url)
    if ($script:NetworkMode -eq 'Offline') { throw 'Synthetic offline network.' }
    if ($Url -ceq 'https://raw.githubusercontent.com/245582001g-oss/telegram-exact-search-patch/main/catalog.json') {
        $source = $script:CatalogDownload
    } elseif ($script:BundleDownloads.ContainsKey($Url)) {
        $source = $script:BundleDownloads[$Url]
    } else { throw ('Forbidden test network endpoint: '+$Url) }
    $bytes = [IO.File]::ReadAllBytes($source)
    if ($script:NetworkMode -eq 'CorruptBundle' -and $Url.EndsWith('.tgpatch')) { $bytes[0] = $bytes[0] -bxor 1 }
    if ($bytes.Length -gt $MaximumBytes) { throw 'Synthetic download exceeds bound.' }
    $stream = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
}

function Get-Process {
    [CmdletBinding()]
    param([string[]] $Name, [int[]] $Id)
    ++$script:ProcessChecks
    if ($script:AlterTargetOnCheck -eq $script:ProcessChecks) { [IO.File]::WriteAllText($script:AlterTarget,'concurrently replaced official executable') }
    $names = @($script:ProcessNames)
    if ($script:BusyAfterCheck -gt 0 -and $script:ProcessChecks -ge $script:BusyAfterCheck) { $names += 'Telegram' }
    foreach ($processName in $names) {
        if ($Name -contains $processName) {
            [pscustomobject]@{ProcessName=$processName; Name=$processName; Id=456789; Path=(Join-Path $fixtureRoot ($processName+'.exe'))}
        }
    }
}

function Start-Process {
    [CmdletBinding()]
    param([string] $FilePath, [string] $WorkingDirectory, [string[]] $ArgumentList,
        [string] $WindowStyle, [switch] $PassThru)
    $script:Launches.Add($FilePath)
    if ($script:TestLaunchPin) {
        try { [IO.File]::WriteAllText($FilePath,'unexpected launch-time write') } catch { $script:LaunchWriteBlocked=$true }
        $replacement=Join-Path $fixtureRoot ('launch-race-'+[Guid]::NewGuid().ToString('N')+'.fixture')
        [IO.File]::WriteAllText($replacement,'unexpected launch-time replacement')
        try { [IO.File]::Replace($replacement,$FilePath,[NullString]::Value) } catch { $script:LaunchReplaceBlocked=$true }
        finally { if ([IO.File]::Exists($replacement)) { [IO.File]::Delete($replacement) } }
    }
    if ($PassThru) { return [pscustomobject]@{Id=456788; StartTime=[datetime]'2026-01-01'; HasExited=$false} }
}

function Stop-Process {
    [CmdletBinding()]
    param([int[]] $Id, [string[]] $Name, [switch] $Force)
    throw 'No real process termination is permitted in this test.'
}

function New-Catalog {
    param($Profiles)
    return [pscustomobject]@{schema=1;repository='245582001g-oss/telegram-exact-search-patch';profiles=@($Profiles)}
}

function Save-FixtureJson {
    param([string] $Path, $Value)
    [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 16),[Text.UTF8Encoding]::new($false))
}

function Clone-FixtureObject($Value) { return ($Value | ConvertTo-Json -Depth 16 | ConvertFrom-Json) }

function Expect-ManagerFailure {
    param([scriptblock] $Action, [string] $Name)
    $failed = $false
    try { & $Action | Out-Null } catch { $failed = $true }
    Assert-ManagerCheck $failed $Name
}

$sourceBytes = [Text.Encoding]::UTF8.GetBytes('synthetic Telegram 7.2.7 original')
$bundlePath = Join-Path $fixtureRoot 'verified.tgpatch'
$bundleFixture = Write-FixtureBundle $bundlePath $sourceBytes ([Text.Encoding]::UTF8.GetBytes(' + exact search r4'))
$profile = [pscustomobject]@{
    telegram_version='7.2.7';patch_version='1.2.0';patch_revision='r4';release_tag='v1.2.0'
    input_sha256=$bundleFixture.Manifest.input_sha256;output_sha256=$bundleFixture.Manifest.output_sha256
    input_size=$sourceBytes.Length;output_size=$bundleFixture.Bytes.Length
    bundle_sha256=$bundleFixture.Hash;bundle_size=(Get-Item -LiteralPath $bundlePath).Length
    asset_name='telegram-exact-search-7.2.7-r4.tgpatch'
}
$catalog = New-Catalog @($profile)
$catalogPath = Join-Path $fixtureRoot 'download-catalog.json'
Save-FixtureJson $catalogPath $catalog
$script:CatalogDownload = $catalogPath
$bundleUrl = 'https://github.com/245582001g-oss/telegram-exact-search-patch/releases/download/v1.2.0/'+$profile.asset_name
$script:BundleDownloads[$bundleUrl] = $bundlePath

function Initialize-ManagerFixture {
    param([string] $Name, [string] $Content = 'synthetic Telegram 7.2.7 original')
    $fixture = New-ManagerFixture $Name $Content
    [void](New-Item -ItemType Directory -Path (Join-Path $fixture.Runtime 'cache') -Force)
    Save-FixtureJson (Join-Path $fixture.Runtime 'manager.json') ([pscustomobject]@{
        schema=1;product='TelegramExactSearchPatch';install_directory=$fixture.Runtime;telegram_exe=$fixture.Exe
    })
    Save-FixtureJson (Join-Path $fixture.Runtime 'catalog.json') $catalog
    $script:NetworkMode='Normal'; $script:ProcessNames=@(); $script:ProcessChecks=0; $script:BusyAfterCheck=0
    $script:AlterTargetOnCheck=0; $script:AlterTarget=''
    $script:TestLaunchPin=$false; $script:LaunchWriteBlocked=$false; $script:LaunchReplaceBlocked=$false
    $script:Downloads.Clear(); $script:Launches.Clear()
    return $fixture
}

Assert-ManagerCheck ((Read-ManagerCatalog $catalogPath).profiles.Count -eq 1) 'Accepts a hash-bound data-only catalog'
$badPath = Join-Path $fixtureRoot 'invalid-catalog.json'
foreach ($case in @(
    @{Name='Foreign repository'; Mutate={param($c) $c.repository='somebody/else'}},
    @{Name='Path traversal asset'; Mutate={param($c) $c.profiles[0].asset_name='../foreign.tgpatch'}},
    @{Name='Encoded asset path'; Mutate={param($c) $c.profiles[0].asset_name='%2e%2e%2fforeign.tgpatch'}},
    @{Name='URL-bearing asset'; Mutate={param($c) $c.profiles[0].asset_name='https://invalid.example/a.tgpatch'}},
    @{Name='Release/tag mismatch'; Mutate={param($c) $c.profiles[0].release_tag='v9.9.9'}},
    @{Name='Malformed bundle hash'; Mutate={param($c) $c.profiles[0].bundle_sha256='bad'}},
    @{Name='Overlarge bundle'; Mutate={param($c) $c.profiles[0].bundle_size=33554433}},
    @{Name='Duplicate output hash'; Mutate={param($c) $c.profiles=@($c.profiles[0],$c.profiles[0])}},
    @{Name='Output reused as official input'; Mutate={param($c) $c.profiles[0].input_sha256=$c.profiles[0].output_sha256}}
)) {
    $bad = Clone-FixtureObject $catalog
    & $case.Mutate $bad
    Save-FixtureJson $badPath $bad
    Expect-ManagerFailure { Read-ManagerCatalog $badPath } ('Rejects catalog: '+$case.Name)
}

$fixture = Initialize-ManagerFixture 'known-original'
$markerHash = Get-FixtureHash $fixture.Marker
$state = Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash
Assert-ManagerCheck ($state.status -ceq 'Repaired' -and (Get-FixtureHash $fixture.Exe) -ceq $profile.output_sha256) 'Known official input reconstructs and installs verified output'
$backup = $fixture.Exe+'.before-chinese-search.7.2.7.bak'
Assert-ManagerCheck ((Get-FixtureHash $backup) -ceq $profile.input_sha256) 'Repair preserves verified version-specific official backup'
Assert-ManagerCheck ((Get-FixtureHash $fixture.Marker) -ceq $markerHash -and $script:Launches.Count -eq 0) 'Background repair preserves synthetic tdata and never launches Telegram'
Assert-ManagerCheck ($script:Downloads.Count -eq 2 -and $script:Downloads[1] -ceq $bundleUrl) 'Downloads only fixed repository catalog and matching release asset'
$downloadsBefore=$script:Downloads.Count
$state = Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($state.status -ceq 'Patched' -and -not $state.changed -and $script:Downloads.Count -eq $downloadsBefore) 'Already-patched second cycle is quiet and does not download again'

$fixture = Initialize-ManagerFixture 'unknown-input' 'unknown future official executable'
$unknownHash = Get-FixtureHash $fixture.Exe
$state = Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash
Assert-ManagerCheck ($state.status -ceq 'WaitingForAdapter' -and (Get-FixtureHash $fixture.Exe) -ceq $unknownHash) 'Unknown version remains byte-for-byte unchanged'
Assert-ManagerCheck ($script:Downloads.Count -eq 1 -and -not (Test-Path -LiteralPath ($fixture.Exe+'.chinese-search.lock')) -and $script:Launches.Count -eq 0) 'Unknown version downloads no bundle, touches no application lock, and is not launched'

foreach ($processName in @('Telegram','Updater')) {
    $fixture = Initialize-ManagerFixture ('busy-'+$processName)
    $script:ProcessNames=@($processName)
    $state = Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
    Assert-ManagerCheck ($state.status -ceq 'PendingExit' -and (Get-FixtureHash $fixture.Exe) -ceq $profile.input_sha256 -and
        -not (Test-Path -LiteralPath ($fixture.Exe+'.before-chinese-search.7.2.7.bak'))) ('Defers repair while any '+$processName+' process is running')
    $script:ProcessNames=@()
    $state = Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
    Assert-ManagerCheck ($state.status -ceq 'Repaired') ('Repairs after simulated '+$processName+' exits normally')
}

$fixture = Initialize-ManagerFixture 'process-race'
$script:BusyAfterCheck=3
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($state.status -ceq 'PendingExit' -and (Get-FixtureHash $fixture.Exe) -ceq $profile.input_sha256) 'Final process recheck prevents repair after Telegram starts during preparation'
Assert-ManagerCheck (@(Get-ChildItem -LiteralPath $fixture.App -Filter '*.tmp.*').Count -eq 0) 'Deferred replacement removes its temporary app file'

$fixture=Initialize-ManagerFixture 'backup-conflict'
$backup=$fixture.Exe+'.before-chinese-search.7.2.7.bak'
[IO.File]::WriteAllText($backup,'foreign original backup')
$badBackupHash=Get-FixtureHash $backup
Expect-ManagerFailure { Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash } 'Refuses a conflicting original backup'
Assert-ManagerCheck ((Get-FixtureHash $fixture.Exe) -ceq $profile.input_sha256 -and (Get-FixtureHash $backup) -ceq $badBackupHash) 'Backup conflict preserves both app and existing backup'

$fixture=Initialize-ManagerFixture 'bundle-corruption'
$script:NetworkMode='CorruptBundle'
Expect-ManagerFailure { Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash } 'Corrupt downloaded bundle is rejected before installation'
Assert-ManagerCheck ((Get-FixtureHash $fixture.Exe) -ceq $profile.input_sha256 -and
    -not (Test-Path -LiteralPath ($fixture.Exe+'.before-chinese-search.7.2.7.bak'))) 'Corrupt bundle does not create app backup or replace target'

$fixture=Initialize-ManagerFixture 'offline-bundled'
[void](New-Item -ItemType Directory -Path (Join-Path $fixture.Runtime 'bundles'))
Copy-Item -LiteralPath $bundlePath -Destination (Join-Path $fixture.Runtime ('bundles\'+$profile.asset_name))
$script:NetworkMode='Offline'
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash
Assert-ManagerCheck ($state.status -ceq 'Repaired') 'Offline repair uses included validated catalog and bundle'

$fixture=Initialize-ManagerFixture 'offline-tampered-cache'
$cachedBundle=Join-Path $fixture.Runtime ('cache\'+$profile.bundle_sha256+'.tgpatch')
[IO.File]::WriteAllText($cachedBundle,'corrupt cached bundle')
$script:NetworkMode='Offline'
Expect-ManagerFailure { Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash } 'Offline corrupted cache is refused'
Assert-ManagerCheck ((Get-FixtureHash $fixture.Exe) -ceq $profile.input_sha256) 'Offline cache failure leaves app unchanged'

$fixture=Initialize-ManagerFixture 'manager-lock'
$lock=[IO.File]::Open((Join-Path $fixture.Runtime 'manager.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try { $state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash } finally { $lock.Dispose() }
Assert-ManagerCheck ($state.status -ceq 'ManagerBusy' -and $script:Downloads.Count -eq 0) 'A competing manager prevents duplicate cycles and downloads'

$fixture=Initialize-ManagerFixture 'disabled-manager'
[IO.File]::WriteAllText((Join-Path $fixture.Runtime 'disabled'),'1')
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($state.status -ceq 'Disabled' -and $script:Downloads.Count -eq 0) 'Disabled manager performs no network or application repair'

$fixture=Initialize-ManagerFixture 'changed-target-race'
$script:AlterTarget=$fixture.Exe; $script:AlterTargetOnCheck=3
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($state.status -ceq 'TargetChanged' -and [IO.File]::ReadAllText($fixture.Exe) -ceq 'concurrently replaced official executable') 'Final hash recheck preserves a concurrently replaced application'
Assert-ManagerCheck (@(Get-ChildItem -LiteralPath $fixture.App -Filter '*.tmp.*').Count -eq 0) 'Target race removes only the manager temporary replacement'

$fixture=Initialize-ManagerFixture 'offline-cached-catalog'
$state=Invoke-ManagerCycle $fixture.Runtime -ForceCatalog -ForceHash
$script:NetworkMode='Offline'
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash
Assert-ManagerCheck ($state.status -ceq 'Repaired') 'Offline refresh failure retains validated catalog and bundle cache'

$fixture=Initialize-ManagerFixture 'tampered-output-cache'
$cachedOutput=Join-Path $fixture.Runtime ('cache\'+$profile.output_sha256+'.exe')
[IO.File]::WriteAllText($cachedOutput,'untrusted cached executable')
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($state.status -ceq 'Repaired' -and (Get-FixtureHash $fixture.Exe) -ceq $profile.output_sha256) 'A tampered reconstructed EXE cache is rebuilt from the verified bundle'

$fixture=Initialize-ManagerFixture 'catalog-rejected-refresh'
$state=Invoke-ManagerCycle $fixture.Runtime -ForceCatalog -ForceHash
$validCacheHash=Get-FixtureHash (Join-Path $fixture.Runtime 'cache\catalog.json')
$script:CatalogDownload=$badPath
try { $state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash }
finally { $script:CatalogDownload=$catalogPath }
Assert-ManagerCheck ($state.status -ceq 'Repaired' -and (Get-FixtureHash (Join-Path $fixture.Runtime 'cache\catalog.json')) -ceq $validCacheHash) 'Invalid catalog refresh preserves the validated cache'

# A new patch revision for the same official binary must reconstruct from the
# official backup, never use an older patched executable as COPY input.
$oldOutput=[Text.Encoding]::UTF8.GetBytes('synthetic Telegram 7.2.7 old exact patch')
$oldProfile=Clone-FixtureObject $profile
$oldProfile.patch_version='1.1.0';$oldProfile.release_tag='v1.1.0';$oldProfile.patch_revision='r3'
$oldProfile.output_sha256=Get-FixtureByteHash $oldOutput;$oldProfile.output_size=$oldOutput.Length
$upgradeCatalog=New-Catalog @($oldProfile,$profile)
Save-FixtureJson $catalogPath $upgradeCatalog
try {
    Assert-ManagerCheck ((Get-ManagerProfile $upgradeCatalog $oldProfile.output_sha256).output_sha256 -ceq $profile.output_sha256) 'Existing older patched output selects latest profile for its original input'
    $fixture=Initialize-ManagerFixture 'patched-upgrade-with-backup'
    [IO.File]::WriteAllBytes($fixture.Exe,$oldOutput)
    $backup=$fixture.Exe+'.before-chinese-search.7.2.7.bak'
    [IO.File]::WriteAllBytes($backup,$sourceBytes)
    $state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash
    Assert-ManagerCheck ($state.status -ceq 'Repaired' -and (Get-FixtureHash $fixture.Exe) -ceq $profile.output_sha256 -and
        (Get-FixtureHash $backup) -ceq $profile.input_sha256) 'Upgrades old patch using verified official backup and preserves that backup'
    $fixture=Initialize-ManagerFixture 'patched-upgrade-no-backup'
    [IO.File]::WriteAllBytes($fixture.Exe,$oldOutput)
    $state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash
    Assert-ManagerCheck ($state.status -ceq 'NeedsOriginalBackup' -and (Get-FixtureHash $fixture.Exe) -ceq $oldProfile.output_sha256) 'Missing official backup leaves an older installed patch intact'
} finally { Save-FixtureJson $catalogPath $catalog }

$fixture=Initialize-ManagerFixture 'wrong-config-root'
$badConfig=Get-Content -LiteralPath (Join-Path $fixture.Runtime 'manager.json') -Raw | ConvertFrom-Json
$badConfig.install_directory=$fixture.App
Save-FixtureJson (Join-Path $fixture.Runtime 'manager.json') $badConfig
Expect-ManagerFailure { Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash } 'Configuration cannot claim another installation directory'
Assert-ManagerCheck ((Get-FixtureHash $fixture.Exe) -ceq $profile.input_sha256 -and $script:Downloads.Count -eq 0) 'Invalid manager config leaves app and network untouched'

$fixture=Initialize-ManagerFixture 'malformed-valid-json-state'
[IO.File]::WriteAllText((Join-Path $fixture.Runtime 'state.json'),'{}')
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($state.status -ceq 'Repaired' -and (Get-FixtureHash $fixture.Exe) -ceq $profile.output_sha256) 'Recovers a valid-JSON state file missing required fields'
foreach ($json in @('null','[]','{"schema":1,"hash":"invalid"}','{"schema":1}')) {
    [IO.File]::WriteAllText((Join-Path $fixture.Runtime 'state.json'),$json)
    $state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
    Assert-ManagerCheck ($state.status -ceq 'Patched') ('Recovers incomplete state '+$json)
}

$fixture=Initialize-ManagerFixture 'offline-catalog-backoff' 'unknown future official executable'
$script:NetworkMode='Offline'
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
$firstAttempts=$script:Downloads.Count
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($firstAttempts -eq 1 -and $script:Downloads.Count -eq 1 -and $state.status -ceq 'WaitingForAdapter') 'Repeated offline monitor checks throttle failed catalog requests'
$attempt=Join-Path $fixture.Runtime 'cache\catalog-attempt.txt'
[IO.File]::SetLastWriteTimeUtc($attempt,[datetime]::UtcNow.AddMinutes(-61))
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($script:Downloads.Count -eq 2) 'Catalog retry resumes after the backoff interval'
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceCatalog -ForceHash
Assert-ManagerCheck ($script:Downloads.Count -eq 3) 'Explicit catalog refresh can bypass the offline monitor backoff'

$fixture=Initialize-ManagerFixture 'verified-launch-pin'
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
$script:TestLaunchPin=$true
Start-ManagerVerifiedTelegram -Root $fixture.Runtime -State $state
Assert-ManagerCheck ($script:Launches.Count -eq 1 -and $script:Launches[0] -ceq $fixture.Exe -and
    $script:LaunchWriteBlocked -and $script:LaunchReplaceBlocked -and (Get-FixtureHash $fixture.Exe) -ceq $profile.output_sha256) 'Launch keeps the verified image pinned against writes and replacement during process creation'
$script:TestLaunchPin=$false
[IO.File]::WriteAllText($fixture.Exe,'new executable after status verification')
Expect-ManagerFailure { Start-ManagerVerifiedTelegram -Root $fixture.Runtime -State $state } 'Launch refuses an image changed after its status check'
Assert-ManagerCheck ($script:Launches.Count -eq 1 -and [IO.File]::ReadAllText($fixture.Exe) -ceq 'new executable after status verification') 'Rejected launch neither starts nor overwrites the changed image'

$fixture=Initialize-ManagerFixture 'unknown-launch-preserved' 'unknown future official executable'
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
$unknownHash=Get-FixtureHash $fixture.Exe
Start-ManagerVerifiedTelegram -Root $fixture.Runtime -State $state
Assert-ManagerCheck ($script:Launches.Count -eq 1 -and (Get-FixtureHash $fixture.Exe) -ceq $unknownHash) 'Explicit managed launch can start an unchanged unknown version without applying a patch'
foreach ($status in @('Disabled','ManagerBusy','TargetChanged','ReadyToRepair')) {
    $refused=[pscustomobject]@{status=$status;hash=$unknownHash}
    Expect-ManagerFailure { Start-ManagerVerifiedTelegram -Root $fixture.Runtime -State $refused } ('Launch refuses unresolved status '+$status)
}

$fixture=Initialize-ManagerFixture 'corrupt-catalog-cache-fallback'
[IO.File]::WriteAllText((Join-Path $fixture.Runtime 'cache\catalog.json'),'{"schema":1}')
[void](New-Item -ItemType Directory -Path (Join-Path $fixture.Runtime 'bundles'))
Copy-Item -LiteralPath $bundlePath -Destination (Join-Path $fixture.Runtime ('bundles\'+$profile.asset_name))
$script:NetworkMode='Offline'
$state=Invoke-ManagerCycle $fixture.Runtime -Repair -ForceHash
Assert-ManagerCheck ($state.status -ceq 'Repaired') 'A corrupt catalog cache falls back to validated included metadata while offline'

# Installer helper functions are exercised directly so the optional native file
# picker is never opened. Startup and monitor wrappers remain fixture-only.
$networkMock=${function:Receive-ManagerFile}
. (Join-Path $repository 'tools\Patch.Manager.Install.ps1')
Set-Item -LiteralPath Function:\Receive-ManagerFile -Value $networkMock
foreach ($name in @('Manage-Patch.ps1','Patch.Manager.Install.ps1','Install-Manager.ps1')) {
    $tokens=$null; $errors=$null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $repository ('tools\'+$name)),[ref]$tokens,[ref]$errors)
    Assert-ManagerCheck ($errors.Count -eq 0) ('PowerShell 5.1 syntax: '+$name)
}
$script:StartupFixture=Join-Path $fixtureRoot 'mock Startup'
[void](New-Item -ItemType Directory -Path $script:StartupFixture)
$script:MonitorStarts=New-Object 'System.Collections.Generic.List[string]'
function Get-ManagerStartupDirectory { return $script:StartupFixture }
function Get-ManagerShortcut {
    param([string] $Path)
    if (-not $Path.StartsWith($fixtureRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Test refused a real shortcut path.' }
    if ([IO.File]::Exists($Path)) { return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json) }
    return $null
}
function New-ManagerShortcut {
    param([string] $Path,[string] $TargetPath,[string] $Arguments,[string] $WorkingDirectory)
    if (-not $Path.StartsWith($fixtureRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Test refused a real shortcut path.' }
    Save-FixtureJson $Path ([pscustomobject]@{TargetPath=$TargetPath;Arguments=$Arguments;WorkingDirectory=$WorkingDirectory})
}
function Start-ManagerMonitor {
    param([string] $Root)
    $script:MonitorStarts.Add($Root)
}

$installSource=Join-Path $fixtureRoot 'installer package'
[void](New-Item -ItemType Directory -Path (Join-Path $installSource 'tools') -Force)
[void](New-Item -ItemType Directory -Path (Join-Path $installSource 'bundles') -Force)
foreach ($name in @('Manage-Patch.ps1','Install-Manager.ps1','Patch.Manager.ps1','Patch.Manager.Install.ps1','Patch.Bundle.ps1')) {
    Copy-Item -LiteralPath (Join-Path $repository ('tools\'+$name)) -Destination (Join-Path $installSource ('tools\'+$name))
}
Save-FixtureJson (Join-Path $installSource 'catalog.json') $catalog
Copy-Item -LiteralPath $bundlePath -Destination (Join-Path $installSource ('bundles\'+$profile.asset_name))
[IO.File]::WriteAllText((Join-Path $installSource 'private.fixture'),'not on runtime whitelist')
[IO.File]::WriteAllText((Join-Path $installSource 'bundles\foreign.fixture'),'not a listed release bundle')
$shortcutPath=Join-Path $script:StartupFixture 'Telegram Exact Search Patch.lnk'

$fixture=New-ManagerFixture 'install without startup'
$targetBefore=Get-FixtureHash $fixture.Exe
$markerBefore=Get-FixtureHash $fixture.Marker
$result=Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $fixture.Exe -InstallDirectory $fixture.Runtime
Assert-ManagerCheck (-not $result.StartupEnabled -and -not $result.MonitorStarted -and
    -not (Test-Path -LiteralPath $shortcutPath) -and $script:MonitorStarts.Count -eq 0) 'Installation requires separate opt-in for startup and immediate monitor launch'
Assert-ManagerCheck ((Get-FixtureHash $fixture.Exe) -ceq $targetBefore -and (Get-FixtureHash $fixture.Marker) -ceq $markerBefore) 'Manager installation leaves Telegram and synthetic account marker untouched'
Assert-ManagerCheck (@(Get-ChildItem -LiteralPath (Join-Path $fixture.Runtime 'tools') -File).Count -eq 5 -and
    -not (Test-Path -LiteralPath (Join-Path $fixture.Runtime 'private.fixture')) -and
    -not (Test-Path -LiteralPath (Join-Path $fixture.Runtime 'bundles\foreign.fixture'))) 'Runtime installation copies only required local tools and listed bundles'
Assert-ManagerCheck ((Read-ManagerConfig $fixture.Runtime).telegram_exe -ceq $fixture.Exe -and
    (Get-FixtureHash (Join-Path $fixture.Runtime ('bundles\'+$profile.asset_name))) -ceq $profile.bundle_sha256) 'Installed config and bundled data remain tied to the selected application'

$result=Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $fixture.Exe -InstallDirectory $fixture.Runtime -EnableStartup -StartMonitor
$shortcut=Get-ManagerShortcut $shortcutPath
$command=Get-ManagerMonitorCommand $fixture.Runtime
Assert-ManagerCheck ($result.StartupEnabled -and $result.MonitorStarted -and $script:MonitorStarts.Count -eq 1 -and
    (Test-ManagerShortcutOwned $shortcut $command)) 'Explicit startup and monitor options use the owned hidden watcher command'
Assert-ManagerCheck ($command.Arguments.Contains('-WindowStyle Hidden') -and
    $command.Arguments.Contains('"'+(Join-Path $fixture.Runtime 'tools\Manage-Patch.ps1')+'"') -and
    $command.Arguments.Contains('-Root "'+$fixture.Runtime+'"')) 'Watcher command quotes paths containing spaces and requests hidden execution'
$shortcutHash=Get-FixtureHash $shortcutPath
$result=Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $fixture.Exe -InstallDirectory $fixture.Runtime
Assert-ManagerCheck ($result.StartupEnabled -and -not $result.MonitorStarted -and
    (Get-FixtureHash $shortcutPath) -ceq $shortcutHash -and $script:MonitorStarts.Count -eq 1) 'Reinstall preserves an existing owned startup registration without starting another monitor'

$oldRuntimeHash=Get-FixtureHash (Join-Path $fixture.Runtime 'tools\Patch.Manager.ps1')
$watchLock=[IO.File]::Open((Join-Path $fixture.Runtime 'watch.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
    Expect-ManagerFailure { Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $fixture.Exe -InstallDirectory $fixture.Runtime -StartMonitor } 'Reinstall defers while the prior watcher owns its lifetime lock'
} finally { $watchLock.Dispose() }
Assert-ManagerCheck ((Test-Path -LiteralPath (Join-Path $fixture.Runtime 'disabled')) -and
    (Get-FixtureHash (Join-Path $fixture.Runtime 'tools\Patch.Manager.ps1')) -ceq $oldRuntimeHash -and
    $script:MonitorStarts.Count -eq 1) 'Deferred reinstall retains disabled marker and existing runtime without launching a replacement watcher'
$result=Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $fixture.Exe -InstallDirectory $fixture.Runtime
Assert-ManagerCheck (-not (Test-Path -LiteralPath (Join-Path $fixture.Runtime 'disabled'))) 'Reinstall succeeds and reenables after old watcher releases its lock'

$backup=$fixture.Exe+'.before-chinese-search.7.2.7.bak'
[IO.File]::WriteAllBytes($backup,$sourceBytes)
$rule=Join-Path $fixture.App 'exact-search-blacklist.v1.bin'
[IO.File]::WriteAllText($rule,'synthetic rule file marker')
$ruleHash=Get-FixtureHash $rule
$userRuntimeFile=Join-Path $fixture.Runtime 'user-note.fixture'
[IO.File]::WriteAllText($userRuntimeFile,'unrelated retained user file')
$result=Uninstall-ManagerRuntime -InstallDirectory $fixture.Runtime
Assert-ManagerCheck ($result.Status -ceq 'Disabled' -and $result.StartupRemoved -and $result.FilesRetained -and
    -not (Test-Path -LiteralPath $shortcutPath) -and (Test-Path -LiteralPath (Join-Path $fixture.Runtime 'disabled'))) 'Uninstall cooperatively disables the watcher and removes only its verified startup entry'
Assert-ManagerCheck ((Get-FixtureHash $fixture.Exe) -ceq $targetBefore -and (Get-FixtureHash $backup) -ceq $profile.input_sha256 -and
    (Get-FixtureHash $rule) -ceq $ruleHash -and (Get-FixtureHash $fixture.Marker) -ceq $markerBefore -and
    (Test-Path -LiteralPath $userRuntimeFile) -and (Test-Path -LiteralPath (Join-Path $fixture.Runtime 'tools\Patch.Manager.ps1'))) 'Uninstall retains runtime, application, official backup, rule file and account marker'

$foreignShortcut=[pscustomobject]@{TargetPath=$command.TargetPath;Arguments='-File "foreign manager.ps1"';WorkingDirectory=$fixture.Runtime}
Save-FixtureJson $shortcutPath $foreignShortcut
$foreignHash=Get-FixtureHash $shortcutPath
$result=Uninstall-ManagerRuntime -InstallDirectory $fixture.Runtime
Assert-ManagerCheck (-not $result.StartupRemoved -and (Get-FixtureHash $shortcutPath) -ceq $foreignHash) 'Uninstall preserves a same-name startup shortcut with foreign arguments'
Expect-ManagerFailure { Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $fixture.Exe -InstallDirectory $fixture.Runtime -EnableStartup } 'Install refuses to overwrite another startup registration'
Assert-ManagerCheck ((Get-FixtureHash $shortcutPath) -ceq $foreignHash) 'Startup collision leaves the foreign shortcut byte-for-byte unchanged'

$boundary=New-ManagerFixture 'install-boundaries'
Expect-ManagerFailure { Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $boundary.Exe -InstallDirectory $boundary.App } 'Installer refuses a manager runtime inside the application directory'
Expect-ManagerFailure { Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $boundary.Exe -InstallDirectory $boundary.Root } 'Installer refuses a manager runtime containing the application directory'
Expect-ManagerFailure { Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $boundary.Exe -InstallDirectory (Join-Path $installSource 'runtime') } 'Installer refuses a runtime nested inside its source package'
[IO.File]::WriteAllText((Join-Path $boundary.Runtime 'unowned.fixture'),'foreign directory content')
Expect-ManagerFailure { Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $boundary.Exe -InstallDirectory $boundary.Runtime } 'Installer refuses an unowned nonempty destination'
Assert-ManagerCheck (-not (Test-Path -LiteralPath (Join-Path $boundary.Runtime 'manager.json')) -and
    (Test-Path -LiteralPath (Join-Path $boundary.Runtime 'unowned.fixture'))) 'Destination refusal does not take ownership or erase existing files'
Expect-ManagerFailure { Uninstall-ManagerRuntime -InstallDirectory $boundary.Runtime } 'Uninstall refuses an unowned runtime'

$alias=Join-Path $boundary.Root 'app alias'
[void](New-Item -ItemType Junction -Path $alias -Target $boundary.App)
Expect-ManagerFailure { Install-ManagerRuntime -SourceRoot $installSource -TelegramExe $boundary.Exe -InstallDirectory (Join-Path $alias 'nested-manager') } 'Directory aliases cannot bypass the application/runtime boundary'
Assert-ManagerCheck (-not (Test-Path -LiteralPath (Join-Path $boundary.App 'nested-manager'))) 'Rejected alias does not create a runtime in the real application directory'

$report=[ordered]@{checks_passed=$checks.Count;checks=@($checks);uses_real_account_data=$false;
    real_telegram_started=$false;real_processes_stopped=$false;real_network_used=$false;
    real_startup_modified=$false;scope='Synthetic app/catalog/bundle files and mocked external effects.'}
Save-FixtureJson (Join-Path $fixtureRoot 'test-report.json') $report
Write-Output ('PASS: {0} external manager checks; no real Telegram, network, process termination, or startup changes.' -f $checks.Count)
