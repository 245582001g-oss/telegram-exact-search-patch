#Requires -Version 5.1
<#
.SYNOPSIS
Verify the supported exact-search patch, repair a known original, and start Telegram.
.DESCRIPTION
Keep this launcher, Install-Patch.ps1, Patch.Common.ps1, compatibility.json, and the
verified patched artifact outside Telegram's installation directory. Use an explicit
shortcut to this script for each launch. A Telegram update is repaired only when its
exact original SHA256 is supported by compatibility.json; unknown versions require
adaptation and are neither changed nor started. No process is stopped by this script.
-NoLaunch performs the same verification and supported repair without starting Telegram.
.EXAMPLE
.\Start-PatchedTelegram.ps1 -TelegramExe 'D:\Telegram\Telegram.exe' -PatchedExe 'D:\Patch\build\Telegram.exe'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $TelegramExe,
    [Parameter(Mandatory = $true)]
    [string] $PatchedExe,
    [switch] $NoLaunch
)

try {
    . (Join-Path $PSScriptRoot 'Patch.Common.ps1')
    $target = Resolve-PatchFilePath $TelegramExe 'Telegram.exe'
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actual -ieq $OriginalSha256) {
        Write-Output ('Supported Telegram {0} original detected; applying the verified patch.' -f $TelegramVersion)
        $LASTEXITCODE = 0
        & (Join-Path $PSScriptRoot 'Install-Patch.ps1') -TelegramExe $target -PatchedExe $PatchedExe
        if ($LASTEXITCODE -ne 0) {
            throw 'Patch installation failed; Telegram was not started.'
        }
    } elseif ($actual -ine $PatchedSha256) {
        throw ('Unsupported Telegram executable (SHA256 {0}); adaptation required. ' -f $actual) +
            'The executable was left unchanged and Telegram was not started.'
    }
    $lockHandle = $null
    $imageHandle = $null
    try {
        $lockHandle = Open-PatchLock $target
        $imageHandle = Open-VerifiedPatchReadHandle $target $PatchedSha256
        Write-Output ('Exact-search patch verified for Telegram {0}: {1}' -f $TelegramVersion, $target)
        if (-not $NoLaunch) {
            Start-Process -FilePath $target -WorkingDirectory (Split-Path -Parent $target)
        }
    } finally {
        if ($null -ne $imageHandle) { $imageHandle.Dispose() }
        if ($null -ne $lockHandle) { $lockHandle.Dispose() }
    }
} catch {
    Write-Error -Message ('Launch failed: {0}' -f $_.Exception.Message) -ErrorAction Continue
    exit 1
}
