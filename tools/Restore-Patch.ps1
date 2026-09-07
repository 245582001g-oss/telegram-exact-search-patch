#Requires -Version 5.1
<#
.SYNOPSIS
Restore the supported original Telegram.exe from its verified local backup.
.DESCRIPTION
Requires the exact supported patched executable and original backup hashes.
Exit Telegram yourself first. The script never stops or starts a process.
The original backup must be Telegram.exe.before-chinese-search.bak beside the
explicitly selected Telegram.exe. Only the executable is replaced atomically;
the backup, chats, tdata, and blacklist are retained. Keep Patch.Common.ps1 beside this script.
.EXAMPLE
.\Restore-Patch.ps1 -TelegramExe 'D:\Telegram\Telegram.exe'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $TelegramExe
)

try {
    . (Join-Path $PSScriptRoot 'Patch.Common.ps1')
    $target = Resolve-PatchFilePath $TelegramExe 'Telegram.exe'
    $backup = Resolve-PatchFilePath ($target + '.before-chinese-search.bak')
    Assert-PatchHash $target $PatchedSha256
    Assert-PatchHash $backup $OriginalSha256
    Assert-TelegramStopped
    $lockHandle = $null
    try {
        $lockHandle = Open-PatchLock $target
        Assert-PatchHash $target $PatchedSha256
        Assert-PatchHash $backup $OriginalSha256
        Replace-VerifiedPatchFile $backup $target $OriginalSha256 $PatchedSha256
        Write-Output ('Original restored and SHA256 verified: {0}' -f $target)
        Write-Output 'Backup and local data retained. Start Telegram manually when ready.'
    } finally {
        if ($null -ne $lockHandle) { $lockHandle.Dispose() }
    }
} catch {
    Write-Error -Message ('Restore failed: {0}' -f $_.Exception.Message) -ErrorAction Continue
    exit 1
}
