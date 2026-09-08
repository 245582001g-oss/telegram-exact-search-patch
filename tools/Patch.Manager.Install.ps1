#Requires -Version 5.1
# Explicit, local-only manager installation helpers. No Telegram file is changed here.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Patch.Manager.ps1')

function Get-ManagerStartupDirectory {
    return [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
}

function Get-ManagerShortcut {
    param([string] $Path)
    if (-not [IO.File]::Exists($Path)) { return $null }
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $null
    try {
        $shortcut = $shell.CreateShortcut($Path)
        return [pscustomobject]@{ TargetPath = $shortcut.TargetPath; Arguments = $shortcut.Arguments;
            WorkingDirectory = $shortcut.WorkingDirectory }
    } finally {
        if ($null -ne $shortcut) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
    }
}

function New-ManagerShortcut {
    param([string] $Path, [string] $TargetPath, [string] $Arguments, [string] $WorkingDirectory)
    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $null
    try {
        $shortcut = $shell.CreateShortcut($temporary)
        $shortcut.TargetPath = $TargetPath
        $shortcut.Arguments = $Arguments
        $shortcut.WorkingDirectory = $WorkingDirectory
        $shortcut.WindowStyle = 7
        $shortcut.Description = 'Telegram Exact Search Patch: check supported updates while Telegram is closed.'
        $shortcut.Save()
        if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary, $Path, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $Path) }
    } finally {
        if ($null -ne $shortcut) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}

function Get-ManagerMonitorCommand {
    param([string] $Root)
    if ($Root.Contains('"')) { throw 'A manager path cannot contain a quote.' }
    return [pscustomobject]@{
        TargetPath = (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
        Arguments = ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Mode Watch -Root "{1}"' -f
            (Join-Path $Root 'tools\Manage-Patch.ps1'), $Root)
        WorkingDirectory = $Root
    }
}

function Start-ManagerMonitor {
    param([string] $Root)
    $command = Get-ManagerMonitorCommand $Root
    Start-Process -FilePath $command.TargetPath -ArgumentList $command.Arguments -WorkingDirectory $Root -WindowStyle Hidden
}

function Resolve-ManagerInstallPath {
    param([string] $Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        ($Path -notmatch '^[A-Za-z]:[\\/]' -and $Path -notmatch '^\\\\[^\\]+\\[^\\]+[\\/]')) {
        throw 'A fully qualified Windows path is required.'
    }
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ($fullPath -ieq [IO.Path]::GetPathRoot($fullPath)) { return $fullPath }
    return $fullPath.TrimEnd('\')
}

function Resolve-ManagerDirectoryIdentity {
    param([string] $Path, [int] $Depth = 0)
    if ($Depth -gt 32) { throw 'Too many directory links; cannot verify installation boundaries.' }
    $fullPath = [IO.Path]::GetFullPath($Path)
    $pathRoot = [IO.Path]::GetPathRoot($fullPath)
    $parts = @($fullPath.Substring($pathRoot.Length).Split('\', [StringSplitOptions]::RemoveEmptyEntries))
    $current = $pathRoot
    for ($index = 0; $index -lt $parts.Count; $index++) {
        $current = Join-Path $current $parts[$index]
        if (-not (Test-Path -LiteralPath $current)) { continue }
        $item = Get-Item -LiteralPath $current -Force
        if (-not $item.PSIsContainer) { throw ('Expected a directory: ' + $current) }
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            $targets = @($item.Target)
            if ($targets.Count -ne 1 -or [string]::IsNullOrWhiteSpace($targets[0])) {
                throw ('Cannot resolve directory link safely: ' + $current)
            }
            $redirect = [string] $targets[0]
            if ($redirect.StartsWith('\??\') -or $redirect.StartsWith('\\?\')) {
                $redirect = $redirect.Substring(4)
                if ($redirect.StartsWith('UNC\', [StringComparison]::OrdinalIgnoreCase)) {
                    $redirect = '\\' + $redirect.Substring(4)
                }
            }
            if (-not [IO.Path]::IsPathRooted($redirect)) { $redirect = Join-Path (Split-Path -Parent $current) $redirect }
            for ($tail = $index + 1; $tail -lt $parts.Count; $tail++) { $redirect = Join-Path $redirect $parts[$tail] }
            return Resolve-ManagerDirectoryIdentity $redirect ($Depth + 1)
        }
    }
    return $current.TrimEnd('\')
}

function Test-ManagerDirectoriesOverlap {
    param([string] $First, [string] $Second)
    $left = Resolve-ManagerDirectoryIdentity $First
    $right = Resolve-ManagerDirectoryIdentity $Second
    return $left.Equals($right, [StringComparison]::OrdinalIgnoreCase) -or
        $left.StartsWith($right + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $right.StartsWith($left + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-ManagerRegularFile {
    param([string] $Path)
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw ('Expected a regular file: ' + $Path)
    }
}

function Test-ManagerShortcutOwned {
    param($Shortcut, $Command)
    return $null -ne $Shortcut -and $Shortcut.TargetPath -ieq $Command.TargetPath -and
        $Shortcut.Arguments -ceq $Command.Arguments -and $Shortcut.WorkingDirectory -ieq $Command.WorkingDirectory
}

function Install-ManagerRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string] $SourceRoot,
        [Parameter(Mandatory = $true)][string] $TelegramExe,
        [string] $InstallDirectory = (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) 'TelegramExactSearchPatch'),
        [switch] $EnableStartup,
        [switch] $StartMonitor
    )
    $sourceRootPath = Resolve-ManagerInstallPath $SourceRoot
    $target = Resolve-ManagerInstallPath $TelegramExe
    $root = Resolve-ManagerInstallPath $InstallDirectory
    if ($root -ieq [IO.Path]::GetPathRoot($root)) { throw 'The manager cannot be installed at a filesystem root.' }
    if ([IO.Path]::GetFileName($target) -ine 'Telegram.exe') { throw 'Select the intended Telegram.exe.' }
    Assert-ManagerRegularFile $target
    if (Test-ManagerDirectoriesOverlap $root (Split-Path -Parent $target)) {
        throw 'The manager directory must be outside, and must not contain, the Telegram installation directory.'
    }
    if (Test-ManagerDirectoriesOverlap $root $sourceRootPath) {
        throw 'Install the manager into an independent directory outside the source package.'
    }
    $whitelist = @('tools\Manage-Patch.ps1', 'tools\Install-Manager.ps1', 'tools\Patch.Manager.ps1',
        'tools\Patch.Manager.Install.ps1', 'tools\Patch.Bundle.ps1')
    $catalogPath = Join-Path $sourceRootPath 'catalog.json'
    Assert-ManagerRegularFile $catalogPath
    $catalogHandle = [IO.File]::Open($catalogPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $installLock = $null
    $watchLock = $null
    try {
        $catalog = Read-ManagerCatalog $catalogPath
        $copies = New-Object 'System.Collections.Generic.List[object]'
        foreach ($relative in $whitelist) {
            $source = Join-Path $sourceRootPath $relative
            Assert-ManagerRegularFile $source
            $copies.Add([pscustomobject]@{ Source = $source; Relative = $relative; Hash = (Get-ManagerSha256 $source) })
        }
        $copies.Add([pscustomobject]@{ Source = $catalogPath; Relative = 'catalog.json'; Hash = (Get-ManagerSha256 $catalogPath) })
        $seenBundles = @{}
        foreach ($profile in @($catalog.profiles)) {
            $source = Join-Path $sourceRootPath ('bundles\' + $profile.asset_name)
            if (-not [IO.File]::Exists($source)) { continue }
            Assert-ManagerRegularFile $source
            if ((Get-Item -LiteralPath $source).Length -ne $profile.bundle_size -or
                (Get-ManagerSha256 $source) -cne $profile.bundle_sha256) { throw 'Bundled profile hash or size mismatch.' }
            if (-not $seenBundles.ContainsKey($profile.asset_name)) {
                $copies.Add([pscustomobject]@{ Source = $source; Relative = ('bundles\' + $profile.asset_name); Hash = $profile.bundle_sha256 })
                $seenBundles[$profile.asset_name] = $true
            }
        }
        if ([IO.Directory]::Exists($root)) {
            $existingConfig = Join-Path $root 'manager.json'
            if ([IO.File]::Exists($existingConfig)) {
                Assert-ManagerRegularFile $existingConfig
                $null = Read-ManagerConfig $root
            } elseif (@(Get-ChildItem -LiteralPath $root -Force).Count -gt 0) {
                throw 'The destination is not an owned manager directory and is not empty.'
            }
        }
        $startup = $null
        $command = Get-ManagerMonitorCommand $root
        $startupEnabled = $false
        $startupDirectory = Get-ManagerStartupDirectory
        if ($EnableStartup) {
            if (-not [IO.Directory]::Exists($startupDirectory)) { throw 'The current user Startup directory is unavailable.' }
            $startup = Join-Path $startupDirectory 'Telegram Exact Search Patch.lnk'
            $existing = Get-ManagerShortcut $startup
            if ($null -ne $existing -and -not (Test-ManagerShortcutOwned $existing $command)) {
                throw 'A different startup registration uses the manager shortcut name; it was left unchanged.'
            }
            $startupEnabled = $true
        } elseif ([IO.Directory]::Exists($startupDirectory)) {
            $startup = Join-Path $startupDirectory 'Telegram Exact Search Patch.lnk'
            if ([IO.File]::Exists($startup)) {
                $startupEnabled = Test-ManagerShortcutOwned (Get-ManagerShortcut $startup) $command
            }
        }
        [void][IO.Directory]::CreateDirectory($root)
        foreach ($child in @('tools', 'bundles', 'cache')) {
            $directory = Join-Path $root $child
            if (Test-Path -LiteralPath $directory) {
                $item = Get-Item -LiteralPath $directory -Force
                if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                    throw ('Runtime subdirectory must be a regular directory: ' + $directory)
                }
            } else { [void][IO.Directory]::CreateDirectory($directory) }
        }
        # Existing watchers observe this marker and leave cooperatively. Never kill a process.
        $disabled = Join-Path $root 'disabled'
        if (Test-Path -LiteralPath $disabled) { Assert-ManagerRegularFile $disabled }
        [IO.File]::WriteAllText($disabled, 'Manager installation in progress.')
        try {
            $watchPath = Join-Path $root 'watch.lock'
            if (Test-Path -LiteralPath $watchPath) { Assert-ManagerRegularFile $watchPath }
            $watchLock = [IO.File]::Open($watchPath, [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            $lockPath = Join-Path $root 'manager.lock'
            if (Test-Path -LiteralPath $lockPath) { Assert-ManagerRegularFile $lockPath }
            $installLock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch { throw 'The manager is completing a cycle. It has been asked to stop; retry installation shortly.' }
        foreach ($copy in $copies) {
            $destination = Join-Path $root $copy.Relative
            if (Test-Path -LiteralPath $destination) { Assert-ManagerRegularFile $destination }
            $temporary = $destination + '.install.' + [Guid]::NewGuid().ToString('N') + '.tmp'
            try {
                Copy-ManagerVerified $copy.Source $temporary $copy.Hash
                if ([IO.File]::Exists($destination)) { [IO.File]::Replace($temporary, $destination, [NullString]::Value) }
                else { [IO.File]::Move($temporary, $destination) }
            } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
        }
        $config = [pscustomobject]@{ schema = 1; product = 'TelegramExactSearchPatch';
            install_directory = $root; telegram_exe = $target }
        Write-ManagerJson (Join-Path $root 'manager.json') $config
        if ($EnableStartup) {
            New-ManagerShortcut -Path $startup -TargetPath $command.TargetPath -Arguments $command.Arguments -WorkingDirectory $root
        }
        [IO.File]::Delete($disabled)
        $installLock.Dispose()
        $installLock = $null
        $watchLock.Dispose()
        $watchLock = $null
        if ($StartMonitor) { Start-ManagerMonitor -Root $root }
        return [pscustomobject]@{ InstallDirectory = $root; TelegramExe = $target;
            StartupEnabled = [bool] $startupEnabled; MonitorStarted = [bool] $StartMonitor }
    } finally {
        if ($null -ne $installLock) { $installLock.Dispose() }
        if ($null -ne $watchLock) { $watchLock.Dispose() }
        $catalogHandle.Dispose()
    }
}

function Uninstall-ManagerRuntime {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][Alias('Root')][string] $InstallDirectory)
    $root = Resolve-ManagerInstallPath $InstallDirectory
    Assert-ManagerRegularFile (Join-Path $root 'manager.json')
    $null = Read-ManagerConfig $root
    $disabled = Join-Path $root 'disabled'
    if (Test-Path -LiteralPath $disabled) { Assert-ManagerRegularFile $disabled }
    [IO.File]::WriteAllText($disabled, 'Manager disabled by its uninstall command.')
    $startup = Join-Path (Get-ManagerStartupDirectory) 'Telegram Exact Search Patch.lnk'
    $command = Get-ManagerMonitorCommand $root
    $shortcut = Get-ManagerShortcut $startup
    $removed = $false
    if (Test-ManagerShortcutOwned $shortcut $command) {
        Assert-ManagerRegularFile $startup
        [IO.File]::Delete($startup)
        $removed = $true
    }
    return [pscustomobject]@{ InstallDirectory = $root; Status = 'Disabled'; StartupRemoved = $removed;
        FilesRetained = $true }
}
