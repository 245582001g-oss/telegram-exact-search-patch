#Requires -Version 5.1
<#
.SYNOPSIS
Install the external patch manager without changing or restarting Telegram.
.DESCRIPTION
Select Telegram.exe when no path is supplied. -EnableStartup adds this manager's
current-user login shortcut; -StartMonitor starts its hidden watcher now.
The runtime is copied from this local package. No manager code is downloaded.
#>
[CmdletBinding()]
param(
    [string] $TelegramExe,
    [string] $InstallDirectory = (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) 'TelegramExactSearchPatch'),
    [switch] $EnableStartup,
    [switch] $StartMonitor
)

try {
    . (Join-Path $PSScriptRoot 'Patch.Manager.Install.ps1')
    if ([string]::IsNullOrWhiteSpace($TelegramExe)) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object Windows.Forms.OpenFileDialog
        try {
            $dialog.Title = 'Select your Telegram.exe'
            $dialog.Filter = 'Telegram executable (Telegram.exe)|Telegram.exe'
            $dialog.CheckFileExists = $true
            $dialog.Multiselect = $false
            $initial = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData)) 'Telegram Desktop'
            if ([IO.Directory]::Exists($initial)) { $dialog.InitialDirectory = $initial }
            if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) {
                Write-Output 'Installation cancelled. Nothing was installed.'
                return
            }
            $TelegramExe = $dialog.FileName
        } finally { $dialog.Dispose() }
    }
    $result = Install-ManagerRuntime -SourceRoot (Split-Path -Parent $PSScriptRoot) -TelegramExe $TelegramExe `
        -InstallDirectory $InstallDirectory -EnableStartup:$EnableStartup -StartMonitor:$StartMonitor
    Write-Output ('Manager installed: {0}' -f $result.InstallDirectory)
    Write-Output ('Telegram selected: {0}' -f $result.TelegramExe)
    Write-Output ('Start at login: {0}; monitor started now: {1}' -f $result.StartupEnabled, $result.MonitorStarted)
    Write-Output 'Telegram and its local data were left unchanged. Supported updates are repaired while Telegram is closed.'
} catch {
    Write-Error -Message ('Manager installation failed: {0}' -f $_.Exception.Message) -ErrorAction Continue
    exit 1
}
