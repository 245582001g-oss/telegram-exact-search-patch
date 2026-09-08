#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Check','Repair','Launch','Watch','Stop','Uninstall')]
    [string] $Mode = 'Check',
    [string] $Root = (Split-Path -Parent $PSScriptRoot),
    [ValidateRange(10,3600)] [int] $IntervalSeconds = 60
)

try {
    . (Join-Path $PSScriptRoot 'Patch.Manager.ps1')
    $Root=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    $null=Read-ManagerConfig $Root
    if ($Mode -eq 'Stop') {
        [IO.File]::WriteAllText((Join-Path $Root 'disabled'),'Stopped by user.')
        Write-Output 'Monitor will stop after its current check. Rerun the installer to enable it again.'
    } elseif ($Mode -eq 'Uninstall') {
        . (Join-Path $PSScriptRoot 'Patch.Manager.Install.ps1')
        Uninstall-ManagerRuntime -InstallDirectory $Root
    } elseif ($Mode -eq 'Watch') {
        $watchLock=$null
        try {
            try { $watchLock=[IO.File]::Open((Join-Path $Root 'watch.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
            catch { exit 0 }
            while (-not [IO.File]::Exists((Join-Path $Root 'disabled'))) {
                try {
                    $state=Invoke-ManagerCycle -Root $Root -Repair
                    Show-ManagerNotice $state
                    $errorPath=Join-Path $Root 'last-error.json'
                    if ([IO.File]::Exists($errorPath)) { [IO.File]::Delete($errorPath) }
                } catch {
                    $message=$_.Exception.Message
                    $errorPath=Join-Path $Root 'last-error.json'; $lastMessage=''
                    if ([IO.File]::Exists($errorPath)) {
                        try { $lastMessage=(Get-Content -LiteralPath $errorPath -Raw -Encoding UTF8 | ConvertFrom-Json).message } catch { }
                    }
                    Write-ManagerJson $errorPath ([pscustomobject]@{
                        checked_utc=(Get-Date).ToUniversalTime().ToString('o');message=$message
                    })
                    try { Show-ManagerNotice ([pscustomobject]@{status='Error';changed=($lastMessage -cne $message)}) } catch { }
                }
                for ($seconds=0; $seconds -lt $IntervalSeconds; $seconds+=2) {
                    if ([IO.File]::Exists((Join-Path $Root 'disabled'))) { break }
                    Start-Sleep -Seconds 2
                }
            }
        } finally { if ($null -ne $watchLock) { $watchLock.Dispose() } }
    } else {
        $state=Invoke-ManagerCycle -Root $Root -Repair:($Mode -ne 'Check') -ForceCatalog -ForceHash
        $state | ConvertTo-Json -Depth 4
        if ($Mode -eq 'Launch') {
            if ($state.status -notin @('Patched','Repaired')) {
                Write-Warning 'The exact-search patch is not active for this executable. Telegram will use its current search behavior.'
            }
            Start-ManagerVerifiedTelegram -Root $Root -State $state
        }
    }
} catch {
    Write-Error -Message ('Patch manager failed: '+$_.Exception.Message) -ErrorAction Continue
    exit 1
}
