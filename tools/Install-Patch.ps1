#Requires -Version 5.1
<#
.SYNOPSIS
Install the exact supported Chinese search build into an explicitly selected Telegram.
.DESCRIPTION
Requires the supported original Telegram.exe and the exact patched build hashes.
Exit Telegram yourself first. The script never stops or starts a process.
Creates or verifies Telegram.exe.before-chinese-search.bak beside Telegram.exe,
then replaces only the executable atomically. Chats, tdata, and blacklists are untouched.
Keep Patch.Common.ps1 beside this script. Backups are never overwritten.
.EXAMPLE
.\Install-Patch.ps1 -TelegramExe 'D:\Telegram\Telegram.exe' -PatchedExe 'D:\Build\Telegram.exe'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $TelegramExe,
    [Parameter(Mandatory = $true)]
    [string] $PatchedExe
)

try {
    . (Join-Path $PSScriptRoot 'Patch.Common.ps1')
    $target = Resolve-PatchFilePath $TelegramExe 'Telegram.exe'
    $patched = Resolve-PatchFilePath $PatchedExe
    Assert-PatchHash $target $OriginalSha256
    Assert-PatchHash $patched $PatchedSha256
    Assert-TelegramStopped
    $lockHandle = $null
    try {
        $lockHandle = Open-PatchLock $target
        Assert-PatchHash $target $OriginalSha256
        $backup = $target + '.before-chinese-search.bak'
        if (Test-Path -LiteralPath $backup) {
            $backup = Resolve-PatchFilePath $backup
            Assert-PatchHash $backup $OriginalSha256
        } else {
            Copy-VerifiedPatchFile $target $backup $OriginalSha256
        }
        Replace-VerifiedPatchFile $patched $target $PatchedSha256 $OriginalSha256
        Write-Output ('Installed and SHA256 verified: {0}' -f $target)
        Write-Output ('Original backup retained: {0}' -f $backup)
        Write-Output 'Start Telegram manually when ready.'
    } finally {
        if ($null -ne $lockHandle) { $lockHandle.Dispose() }
    }
} catch {
    Write-Error -Message ('Installation failed: {0}' -f $_.Exception.Message) -ErrorAction Continue
    exit 1
}
