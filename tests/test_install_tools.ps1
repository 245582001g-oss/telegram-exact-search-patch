#Requires -Version 5.1
<#
.SYNOPSIS
Exercise installation and restore against isolated synthetic files under work/.
.DESCRIPTION
Runs the real scripts in Windows PowerShell 5.1 with a synthetic compatibility.json.
The child runner mocks process discovery; it never opens or changes a real Telegram.
.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tests\test_install_tools.ps1
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$toolDirectory = Join-Path $repository 'tools'
$fixtureRoot = Join-Path $repository ('work\install-tools-tests\' + [Guid]::NewGuid().ToString('N'))
$fixtureTools = Join-Path $fixtureRoot 'tools'
[void](New-Item -ItemType Directory -Path $fixtureTools -Force)
$shell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$checks = New-Object 'System.Collections.Generic.List[string]'

function Assert-Check {
    param([bool] $Condition, [string] $Name)
    if (-not $Condition) { throw ('FAIL: ' + $Name) }
    $checks.Add($Name)
}

function Get-Sha256 {
    param([string] $Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function New-Case {
    param([string] $Name, [string] $TargetContent = 'synthetic Telegram 7.2.7 original')
    $directory = Join-Path $fixtureRoot $Name
    [void](New-Item -ItemType Directory -Path $directory)
    $target = Join-Path $directory 'Telegram.exe'
    [IO.File]::WriteAllText($target, $TargetContent)
    return $target
}

function Run-Tool {
    param([string] $Name, [string] $Target, [int] $ExpectedExit, [bool] $Running = $false,
        [string] $Artifact = $script:patchedArtifact, [bool] $NoLaunch = $true,
        [bool] $UpdaterRunning = $false, [bool] $OtherUpdater = $false, [bool] $LaunchRace = $false)
    $arguments = @('-ToolPath', (Join-Path $fixtureTools $Name), '-TargetPath', $Target)
    if ($Name -in @('Install-Patch.ps1', 'Start-PatchedTelegram.ps1')) {
        $arguments += @('-PatchedPath', $Artifact)
    }
    if ($Name -eq 'Start-PatchedTelegram.ps1' -and $NoLaunch) { $arguments += '-SuppressLaunch' }
    if ($Running) { $arguments += '-SimulateRunning' }
    if ($UpdaterRunning) { $arguments += '-SimulateUpdater' }
    if ($OtherUpdater) { $arguments += '-SimulateOtherUpdater' }
    if ($LaunchRace) { $arguments += '-SimulateLaunchRace' }
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = (& $shell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $runner @arguments 2>&1 | Out-String)
        $status = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    if ($status -ne $ExpectedExit) {
        throw ('Unexpected {0} exit code {1} (expected {2}): {3}' -f $Name, $status, $ExpectedExit, $output)
    }
    return $output
}

Assert-Check ($PSVersionTable.PSVersion.Major -eq 5) 'Tests use actual Windows PowerShell 5.1'
foreach ($name in @('Install-Patch.ps1', 'Restore-Patch.ps1', 'Patch.Common.ps1', 'Start-PatchedTelegram.ps1')) {
    $path = Join-Path $toolDirectory $name
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($path, [ref] $tokens, [ref] $errors)
    Assert-Check ($errors.Count -eq 0) ('Windows PowerShell 5.1 syntax: ' + $name)
    Copy-Item -LiteralPath $path -Destination $fixtureTools
}

# Verify that the production helpers consume the repository manifest unchanged.
. (Join-Path $toolDirectory 'Patch.Common.ps1')
$release = Get-Content -LiteralPath (Join-Path $repository 'compatibility.json') -Raw | ConvertFrom-Json
Assert-Check ($OriginalSha256 -ceq $release.input_sha256 -and
    $PatchedSha256 -ceq $release.verified_output_sha256 -and
    $TelegramVersion -ceq $release.telegram_version) 'Production hashes and version come from compatibility.json'

$runner = Join-Path $fixtureRoot 'Run-FixtureTool.ps1'
[IO.File]::WriteAllText($runner, @'
param([string] $ToolPath, [string] $TargetPath, [string] $PatchedPath,
    [switch] $SimulateRunning, [switch] $SuppressLaunch, [switch] $SimulateUpdater,
    [switch] $SimulateOtherUpdater, [switch] $SimulateLaunchRace)
$ErrorActionPreference = 'Stop'
function Get-Process {
    param([string] $Name)
    if ($Name -eq 'Telegram' -and $SimulateRunning) {
        [pscustomobject]@{ ProcessName = 'Telegram'; Path = $TargetPath }
    }
    if ($Name -eq 'Updater' -and $SimulateUpdater) {
        [pscustomobject]@{ ProcessName = 'Updater'; Path = (Join-Path (Split-Path -Parent $TargetPath) 'Updater.exe') }
    }
    if ($Name -eq 'Updater' -and $SimulateOtherUpdater) {
        [pscustomobject]@{ ProcessName = 'Updater'; Path = (Join-Path $PSScriptRoot 'unrelated-app\Updater.exe') }
    }
}
function Start-Process {
    param([string] $FilePath, [string] $WorkingDirectory)
    $writeBlocked = $false
    $replaceBlocked = $false
    if ($SimulateLaunchRace) {
        try { [IO.File]::WriteAllText($FilePath, 'unexpected concurrent write') } catch { $writeBlocked = $true }
        $replacement = $FilePath + '.race.fixture'
        [IO.File]::WriteAllText($replacement, 'unexpected concurrent replacement')
        try { [IO.File]::Replace($replacement, $FilePath, [NullString]::Value) } catch { $replaceBlocked = $true }
    }
    [IO.File]::WriteAllText($TargetPath + '.launch.json', (@{
        FilePath = $FilePath; WorkingDirectory = $WorkingDirectory
        WriteBlocked = $writeBlocked; ReplaceBlocked = $replaceBlocked
    } | ConvertTo-Json))
}
$arguments = @{ TelegramExe = $TargetPath }
if ($PatchedPath) { $arguments.PatchedExe = $PatchedPath }
if ($SuppressLaunch) { $arguments.NoLaunch = $true }
$global:LASTEXITCODE = 0
& $ToolPath @arguments
exit $LASTEXITCODE
'@)

$originalArtifact = Join-Path $fixtureRoot 'original.fixture'
$patchedArtifact = Join-Path $fixtureRoot 'patched.fixture'
$oldArtifact = Join-Path $fixtureRoot 'old.fixture'
[IO.File]::WriteAllText($originalArtifact, 'synthetic Telegram 7.2.7 original')
[IO.File]::WriteAllText($patchedArtifact, 'synthetic Telegram 7.2.7 patched')
[IO.File]::WriteAllText($oldArtifact, 'synthetic Telegram 7.2.5 original')
$originalHash = Get-Sha256 $originalArtifact
$patchedHash = Get-Sha256 $patchedArtifact
$oldHash = Get-Sha256 $oldArtifact
$manifestPath = Join-Path $fixtureRoot 'compatibility.json'
$manifest = [ordered]@{
    telegram_version = '7.2.7'
    platform = 'windows-x64'
    input_filename = 'Telegram.exe'
    input_sha256 = $originalHash
    verified_output_sha256 = $patchedHash
}
$manifestJson = $manifest | ConvertTo-Json
[IO.File]::WriteAllText($manifestPath, $manifestJson)

# An upgrade must coexist with the legacy first-release backup and a named older backup.
$target = New-Case 'upgrade'
$backup = $target + '.before-chinese-search.7.2.7.bak'
$legacyBackup = $target + '.before-chinese-search.bak'
$oldBackup = $target + '.before-chinese-search.7.2.5.bak'
Copy-Item -LiteralPath $oldArtifact -Destination $legacyBackup
Copy-Item -LiteralPath $oldArtifact -Destination $oldBackup
$dataDirectory = Join-Path (Split-Path -Parent $target) 'tdata'
[void](New-Item -ItemType Directory -Path $dataDirectory)
$dataMarker = Join-Path $dataDirectory 'untouched.fixture'
[IO.File]::WriteAllText($dataMarker, 'synthetic account data marker')
$dataHash = Get-Sha256 $dataMarker
$result = Run-Tool 'Install-Patch.ps1' $target 0
Assert-Check ($result -match 'Installed and SHA256 verified') 'Upgrade installation succeeds with older backups present'
Assert-Check ((Get-Sha256 $target) -eq $patchedHash -and (Get-Sha256 $backup) -eq $originalHash) 'Upgrade retains the current original in a version-specific backup'
Assert-Check ((Get-Sha256 $legacyBackup) -eq $oldHash -and (Get-Sha256 $oldBackup) -eq $oldHash) 'Upgrade preserves both older backups byte-for-byte'
$result = Run-Tool 'Restore-Patch.ps1' $target 0
Assert-Check ($result -match 'Original restored and SHA256 verified' -and (Get-Sha256 $target) -eq $originalHash) 'Restore selects the current-version original despite older backups'
$result = Run-Tool 'Install-Patch.ps1' $target 0
Assert-Check ((Get-Sha256 $backup) -eq $originalHash) 'Reinstall verifies and reuses the current-version backup'
Assert-Check ((Get-Sha256 $dataMarker) -eq $dataHash) 'Install and restore preserve the synthetic tdata marker'

# No compatibility fallback may select an old backup, even if its bytes happen to match.
$target = New-Case 'missing-current-backup' 'synthetic Telegram 7.2.7 patched'
Copy-Item -LiteralPath $originalArtifact -Destination ($target + '.before-chinese-search.bak')
Copy-Item -LiteralPath $oldArtifact -Destination ($target + '.before-chinese-search.7.2.5.bak')
$result = Run-Tool 'Restore-Patch.ps1' $target 1
Assert-Check ((Get-Sha256 $target) -eq $patchedHash) 'Restore refuses legacy-only backups and preserves patched target'
Assert-Check (-not (Test-Path -LiteralPath ($target + '.chinese-search.lock'))) 'Missing current backup is refused before locking'

$target = New-Case 'conflicting-current-backup'
$backup = $target + '.before-chinese-search.7.2.7.bak'
Copy-Item -LiteralPath $oldArtifact -Destination $backup
$result = Run-Tool 'Install-Patch.ps1' $target 1
Assert-Check ($result -match 'SHA256 mismatch' -and (Get-Sha256 $target) -eq $originalHash -and
    (Get-Sha256 $backup) -eq $oldHash) 'Installer refuses a current-version backup containing old-version bytes'
Copy-Item -LiteralPath $patchedArtifact -Destination $target
$result = Run-Tool 'Restore-Patch.ps1' $target 1
Assert-Check ($result -match 'SHA256 mismatch' -and (Get-Sha256 $target) -eq $patchedHash -and
    (Get-Sha256 $backup) -eq $oldHash) 'Restore refuses an old original renamed as the current backup'

$target = New-Case 'unknown-original' 'unknown executable'
$unknownHash = Get-Sha256 $target
$result = Run-Tool 'Install-Patch.ps1' $target 1
Assert-Check ($result -match 'SHA256 mismatch' -and (Get-Sha256 $target) -eq $unknownHash) 'Installer refuses unknown input bytes'
Assert-Check (-not (Test-Path -LiteralPath ($target + '.chinese-search.lock'))) 'Unknown input is refused before file mutation'

$target = New-Case 'unknown-patch'
$result = Run-Tool 'Install-Patch.ps1' $target 1 -Artifact $oldArtifact
Assert-Check ($result -match 'SHA256 mismatch' -and (Get-Sha256 $target) -eq $originalHash) 'Installer refuses unknown output bytes'
Assert-Check (-not (Test-Path -LiteralPath ($target + '.before-chinese-search.7.2.7.bak'))) 'Unknown patch creates no backup'

$target = New-Case 'running-process'
$result = Run-Tool 'Install-Patch.ps1' $target 1 -Running $true
Assert-Check ($result -match 'Exit Telegram completely' -and (Get-Sha256 $target) -eq $originalHash) 'Installer refuses a simulated running Telegram'
Assert-Check (-not (Test-Path -LiteralPath ($target + '.chinese-search.lock'))) 'Running Telegram refusal creates no lock'

$target = New-Case 'running-updater'
$result = Run-Tool 'Install-Patch.ps1' $target 1 -UpdaterRunning $true
Assert-Check ($result -match 'Telegram updater' -and (Get-Sha256 $target) -eq $originalHash -and
    -not (Test-Path -LiteralPath ($target + '.chinese-search.lock'))) 'Installer refuses the selected Telegram updater before modifying files'
$result = Run-Tool 'Install-Patch.ps1' $target 1 -OtherUpdater $true
Assert-Check ($result -match 'path alias' -and (Get-Sha256 $target) -eq $originalHash -and
    -not (Test-Path -LiteralPath ($target + '.chinese-search.lock'))) 'Updater from a different or aliased path is conservatively refused before modifying files'
$result = Run-Tool 'Install-Patch.ps1' $target 0
$result = Run-Tool 'Restore-Patch.ps1' $target 1 -UpdaterRunning $true
Assert-Check ($result -match 'Telegram updater' -and (Get-Sha256 $target) -eq $patchedHash) 'Restore refuses the selected Telegram updater'

$target = New-Case 'competing-lock'
$lock = [IO.File]::Open($target + '.chinese-search.lock', [IO.FileMode]::OpenOrCreate,
    [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try { $result = Run-Tool 'Install-Patch.ps1' $target 1 } finally { $lock.Dispose() }
Assert-Check ($result -match 'Another install or restore' -and (Get-Sha256 $target) -eq $originalHash) 'Installer refuses a competing lock without replacing the target'

$target = New-Case 'invalid-manifest'
foreach ($invalid in @(
    @{ telegram_version = '..\7.2.7'; input_sha256 = $originalHash; verified_output_sha256 = $patchedHash },
    @{ telegram_version = '7.2.7'; input_sha256 = ''; verified_output_sha256 = $patchedHash },
    @{ telegram_version = '7.2.7'; input_sha256 = $originalHash; verified_output_sha256 = $originalHash },
    @{ telegram_version = '7.2.7'; input_sha256 = $originalHash; verified_output_sha256 = ($patchedHash + "`n") }
)) {
    $invalid.platform = 'windows-x64'
    $invalid.input_filename = 'Telegram.exe'
    [IO.File]::WriteAllText($manifestPath, ($invalid | ConvertTo-Json))
    $result = Run-Tool 'Install-Patch.ps1' $target 1
    Assert-Check ($result -match 'Invalid compatibility.json' -and (Get-Sha256 $target) -eq $originalHash) 'Malformed release metadata is refused before modifying the target'
}
[IO.File]::WriteAllText($manifestPath, $manifestJson)

$target = New-Case 'launcher-repair'
Copy-Item -LiteralPath $oldArtifact -Destination ($target + '.before-chinese-search.bak')
$result = Run-Tool 'Start-PatchedTelegram.ps1' $target 0
Assert-Check ($result -match 'Exact-search patch verified' -and (Get-Sha256 $target) -eq $patchedHash -and
    (Get-Sha256 ($target + '.before-chinese-search.7.2.7.bak')) -eq $originalHash) 'Launcher reapplies the exact supported patch after an update'
Assert-Check (-not (Test-Path -LiteralPath ($target + '.launch.json'))) 'Launcher NoLaunch repairs and verifies without starting a process'
$result = Run-Tool 'Start-PatchedTelegram.ps1' $target 0 -NoLaunch $false
$launch = Get-Content -LiteralPath ($target + '.launch.json') -Raw | ConvertFrom-Json
Assert-Check ($launch.FilePath -ceq $target -and $launch.WorkingDirectory -ceq (Split-Path -Parent $target)) 'Verified launcher starts only the explicitly selected Telegram (mocked)'
$result = Run-Tool 'Start-PatchedTelegram.ps1' $target 0 -NoLaunch $false -LaunchRace $true
$launch = Get-Content -LiteralPath ($target + '.launch.json') -Raw | ConvertFrom-Json
Assert-Check ($launch.WriteBlocked -and $launch.ReplaceBlocked -and (Get-Sha256 $target) -eq $patchedHash) 'A pinned verified image prevents writing or replacing the executable during process creation'

$target = New-Case 'launcher-already-patched' 'synthetic Telegram 7.2.7 patched'
$result = Run-Tool 'Start-PatchedTelegram.ps1' $target 0
Assert-Check ((Get-Sha256 $target) -eq $patchedHash -and
    -not (Test-Path -LiteralPath ($target + '.before-chinese-search.7.2.7.bak'))) 'Already-patched launcher is idempotent and creates no replacement backup'

$target = New-Case 'launcher-unknown-update' 'synthetic unsupported future version'
$unknownHash = Get-Sha256 $target
$result = Run-Tool 'Start-PatchedTelegram.ps1' $target 1 -NoLaunch $false
Assert-Check ($result -match 'adaptation required' -and (Get-Sha256 $target) -eq $unknownHash -and
    -not (Test-Path -LiteralPath ($target + '.launch.json'))) 'Launcher refuses an unknown update without modification or launch'

$target = New-Case 'launcher-running-original'
$result = Run-Tool 'Start-PatchedTelegram.ps1' $target 1 -Running $true -NoLaunch $false
Assert-Check ($result -match 'Exit Telegram completely' -and (Get-Sha256 $target) -eq $originalHash -and
    -not (Test-Path -LiteralPath ($target + '.launch.json'))) 'Launcher never starts Telegram after its installer refuses a running process'

$target = New-Case 'launcher-wrong-artifact'
$result = Run-Tool 'Start-PatchedTelegram.ps1' $target 1 -Artifact $oldArtifact -NoLaunch $false
Assert-Check ($result -match 'SHA256 mismatch' -and (Get-Sha256 $target) -eq $originalHash -and
    -not (Test-Path -LiteralPath ($target + '.launch.json'))) 'Launcher never starts Telegram after an invalid patch artifact is refused'

$target = New-Case 'failed-image-verification'
$refused = $false
try {
    $unexpectedHandle = Open-VerifiedPatchReadHandle $target $patchedHash
    $unexpectedHandle.Dispose()
} catch { $refused = $_.Exception.Message -match 'SHA256 mismatch' }
$exclusive = [IO.File]::Open($target, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$exclusive.Dispose()
Assert-Check $refused 'Failed image verification disposes its read handle so exclusive access remains possible'

Assert-Check (@(Get-ChildItem -LiteralPath $fixtureRoot -Recurse -File -Filter '*.tmp.*').Count -eq 0) 'No atomic replacement temporary files remain'

$checks | ForEach-Object { Write-Output ('PASS ' + $_) }
Write-Output ('TOTAL {0} checks passed. Synthetic fixtures retained: {1}' -f $checks.Count, $fixtureRoot)
