#Requires -Version 5.1
# External manager. Remote inputs are data-only catalogs and COPY/DATA/ZERO bundles.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:ManagerRepository = '245582001g-oss/telegram-exact-search-patch'
$script:ManagerCatalogUrl = 'https://raw.githubusercontent.com/' + $script:ManagerRepository + '/main/catalog.json'
. (Join-Path $PSScriptRoot 'Patch.Bundle.ps1')

function Get-ManagerSha256([string] $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-ManagerJson([string] $Path, $Value) {
    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
        if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary, $Path, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $Path) }
    } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
}

function Read-ManagerCatalog([string] $Path) {
    if ((Get-Item -LiteralPath $Path).Length -gt 1048576) { throw 'Catalog exceeds 1 MiB.' }
    $value = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($value.schema -ne 1 -or $value.repository -cne $script:ManagerRepository) { throw 'Unsupported catalog.' }
    $profiles = @($value.profiles)
    if ($profiles.Count -lt 1 -or $profiles.Count -gt 256) { throw 'Invalid profile count.' }
    $seenOutputs = @{}
    foreach ($p in $profiles) {
        foreach ($name in @('input_sha256','output_sha256','bundle_sha256')) {
            if ([string]$p.$name -cnotmatch '\A[0-9a-f]{64}\z') { throw ('Invalid profile hash: '+$name) }
        }
        foreach ($name in @('telegram_version','patch_version')) {
            if ([string]$p.$name -notmatch '\A[0-9]+\.[0-9]+\.[0-9]+\z') { throw ('Invalid version: '+$name) }
        }
        if ($p.release_tag -cne ('v'+$p.patch_version) -or
            $p.asset_name -cnotmatch '\A[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.tgpatch\z' -or
            $p.patch_revision -cnotmatch '\Ar[0-9]+\z' -or
            $p.input_sha256 -ceq $p.output_sha256) { throw 'Invalid release profile.' }
        foreach ($name in @('input_size','output_size','bundle_size')) {
            $number = [long]$p.$name
            if ($number -lt 1 -or $number -gt 1073741824 -or [double]$p.$name -ne $number) { throw 'Invalid file size.' }
        }
        if ($p.bundle_size -gt 33554432 -or $seenOutputs.ContainsKey($p.output_sha256)) { throw 'Invalid/duplicate output profile.' }
        $seenOutputs[$p.output_sha256] = $true
    }
    foreach ($p in $profiles) {
        if ($seenOutputs.ContainsKey($p.input_sha256)) { throw 'An output hash cannot be used as an official input.' }
    }
    return $value
}

function Receive-ManagerFile([string] $Url, [string] $Destination, [long] $MaximumBytes) {
    if (-not $Url.StartsWith('https://', [StringComparison]::Ordinal)) { throw 'HTTPS required.' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $request = [Net.HttpWebRequest]::Create($Url)
    $request.UserAgent = 'TelegramExactSearchPatch/1.2'
    $request.Timeout = 15000; $request.ReadWriteTimeout = 15000
    $request.UseDefaultCredentials = $false
    $response = $null; $inputStream = $null; $outputStream = $null
    try {
        $response = $request.GetResponse()
        if ($response.ResponseUri.Scheme -cne 'https' -or $response.ContentLength -gt $MaximumBytes) { throw 'Invalid download response.' }
        $inputStream = $response.GetResponseStream()
        $outputStream = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $buffer = New-Object byte[] 65536; $total = 0L
        while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $total += $count
            if ($total -gt $MaximumBytes) { throw 'Download exceeds limit.' }
            $outputStream.Write($buffer, 0, $count)
        }
        $outputStream.Flush($true)
    } finally {
        if ($null -ne $outputStream) { $outputStream.Dispose() }
        if ($null -ne $inputStream) { $inputStream.Dispose() }
        if ($null -ne $response) { $response.Dispose() }
    }
}

function Read-ManagerConfig([string] $Root) {
    $Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $config = Get-Content -LiteralPath (Join-Path $Root 'manager.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($config.schema -ne 1 -or $config.product -cne 'TelegramExactSearchPatch' -or
        $config.install_directory -ine $Root -or -not [IO.Path]::IsPathRooted($config.telegram_exe) -or
        [IO.Path]::GetFileName($config.telegram_exe) -ine 'Telegram.exe') { throw 'Invalid manager configuration.' }
    return $config
}

function Test-ManagerBusy {
    return @(Get-Process -Name Telegram,Updater -ErrorAction SilentlyContinue).Count -gt 0
}

function Copy-ManagerVerified([string] $Source, [string] $Destination, [string] $Hash) {
    $reader = $null; $writer = $null; $created = $false
    try {
        $reader = [IO.File]::Open($Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $writer = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $created = $true; $reader.CopyTo($writer); $writer.Flush($true)
        $writer.Dispose(); $writer = $null
        if ((Get-ManagerSha256 $Destination) -cne $Hash) { throw 'Copy hash mismatch.' }
    } catch {
        if ($null -ne $writer) { $writer.Dispose(); $writer = $null }
        if ($created -and [IO.File]::Exists($Destination)) { [IO.File]::Delete($Destination) }
        throw
    } finally {
        if ($null -ne $writer) { $writer.Dispose() }
        if ($null -ne $reader) { $reader.Dispose() }
    }
}

function Get-ManagerProfile($Catalog, [string] $CurrentHash) {
    $known = @($Catalog.profiles | Where-Object { $_.input_sha256 -ceq $CurrentHash -or $_.output_sha256 -ceq $CurrentHash })
    if (-not $known.Count) { return $null }
    $inputs = @($known | ForEach-Object { $_.input_sha256 } | Select-Object -Unique)
    if ($inputs.Count -ne 1) { throw 'Ambiguous input profile.' }
    $candidates = @($Catalog.profiles | Where-Object { $_.input_sha256 -ceq $inputs[0] } |
        Sort-Object -Property @{Expression={ [version]$_.patch_version }; Descending=$true})
    return $candidates[0]
}

function Update-ManagerCatalog([string] $Root, [bool] $Force = $false) {
    $cache = Join-Path $Root 'cache\catalog.json'
    $attempt = Join-Path $Root 'cache\catalog-attempt.txt'
    if (-not $Force -and [IO.File]::Exists($cache) -and
        ((Get-Date).ToUniversalTime() - (Get-Item -LiteralPath $cache).LastWriteTimeUtc).TotalMinutes -lt 60) {
        try { return Read-ManagerCatalog $cache } catch { }
    }
    if (-not $Force -and [IO.File]::Exists($attempt) -and
        ((Get-Date).ToUniversalTime() - (Get-Item -LiteralPath $attempt).LastWriteTimeUtc).TotalMinutes -lt 60) {
        if ([IO.File]::Exists($cache)) { try { return Read-ManagerCatalog $cache } catch { } }
        return Read-ManagerCatalog (Join-Path $Root 'catalog.json')
    }
    $temporary = Join-Path $Root ('cache\catalog.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($attempt, (Get-Date).ToUniversalTime().ToString('o'))
        Receive-ManagerFile $script:ManagerCatalogUrl $temporary 1048576
        $catalog = Read-ManagerCatalog $temporary
        if ([IO.File]::Exists($cache)) { [IO.File]::Replace($temporary, $cache, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $cache) }
        return $catalog
    } catch {
        if ([IO.File]::Exists($cache)) { try { return Read-ManagerCatalog $cache } catch { } }
        return Read-ManagerCatalog (Join-Path $Root 'catalog.json')
    } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
}

function Get-ManagerBundle([string] $Root, $Profile) {
    $name = $Profile.bundle_sha256 + '.tgpatch'
    foreach ($path in @((Join-Path $Root ('cache\'+$name)), (Join-Path $Root ('bundles\'+$Profile.asset_name)))) {
        if ([IO.File]::Exists($path) -and (Get-Item -LiteralPath $path).Length -eq $Profile.bundle_size -and
            (Get-ManagerSha256 $path) -ceq $Profile.bundle_sha256) { return $path }
    }
    $destination = Join-Path $Root ('cache\'+$name)
    $temporary = $destination + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $url = 'https://github.com/' + $script:ManagerRepository + '/releases/download/' + $Profile.release_tag + '/' + $Profile.asset_name
    try {
        Receive-ManagerFile $url $temporary ([long]$Profile.bundle_size)
        if ((Get-Item -LiteralPath $temporary).Length -ne $Profile.bundle_size -or
            (Get-ManagerSha256 $temporary) -cne $Profile.bundle_sha256) { throw 'Downloaded bundle hash/size mismatch.' }
        if ([IO.File]::Exists($destination)) { [IO.File]::Replace($temporary, $destination, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $destination) }
        return $destination
    } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
}

function Install-ManagerPatch([string] $Root, [string] $Target, [string] $CurrentHash, $Profile, [string] $Bundle) {
    if (Test-ManagerBusy) { return 'PendingExit' }
    $targetLock = $null; $temporary = $null
    try {
        $targetLock = [IO.File]::Open($Target+'.chinese-search.lock', [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        if (Test-ManagerBusy) { return 'PendingExit' }
        if ((Get-ManagerSha256 $Target) -cne $CurrentHash) { return 'TargetChanged' }
        $backup = $Target + '.before-chinese-search.' + $Profile.telegram_version + '.bak'
        $source = $Target
        if ($CurrentHash -cne $Profile.input_sha256) {
            if (-not [IO.File]::Exists($backup) -or (Get-ManagerSha256 $backup) -cne $Profile.input_sha256) { return 'NeedsOriginalBackup' }
            $source = $backup
        }
        if ([IO.File]::Exists($backup)) {
            if ((Get-ManagerSha256 $backup) -cne $Profile.input_sha256) { throw 'Original backup hash mismatch; not overwritten.' }
        } else { Copy-ManagerVerified $source $backup $Profile.input_sha256 }
        $cachedOutput = Join-Path $Root ('cache\'+$Profile.output_sha256+'.exe')
        if ([IO.File]::Exists($cachedOutput) -and (Get-ManagerSha256 $cachedOutput) -cne $Profile.output_sha256) {
            [IO.File]::Delete($cachedOutput)
        }
        if (-not [IO.File]::Exists($cachedOutput)) {
            $result = Expand-TelegramPatchBundle -BundlePath $Bundle -SourcePath $source -OutputPath $cachedOutput -ExpectedBundleSha256 $Profile.bundle_sha256
            if ($result.Sha256 -cne $Profile.output_sha256 -or $result.Length -ne $Profile.output_size -or
                $result.TelegramVersion -cne $Profile.telegram_version -or $result.PatchRevision -cne $Profile.patch_revision) { throw 'Bundle/catalog output mismatch.' }
        }
        $temporary = $Target + '.chinese-search.tmp.' + [Guid]::NewGuid().ToString('N')
        Copy-ManagerVerified $cachedOutput $temporary $Profile.output_sha256
        if (Test-ManagerBusy) { return 'PendingExit' }
        if ((Get-ManagerSha256 $Target) -cne $CurrentHash) { return 'TargetChanged' }
        [IO.File]::Replace($temporary, $Target, [NullString]::Value)
        if ((Get-ManagerSha256 $Target) -cne $Profile.output_sha256) { throw 'Installed output verification failed.' }
        return 'Repaired'
    } finally {
        if ($temporary -and [IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
        if ($null -ne $targetLock) { $targetLock.Dispose() }
    }
}

function Invoke-ManagerCycle([string] $Root, [switch] $Repair, [switch] $ForceCatalog, [switch] $ForceHash) {
    $config = Read-ManagerConfig $Root
    if ([IO.File]::Exists((Join-Path $Root 'disabled'))) { return [pscustomobject]@{status='Disabled'; hash=''; changed=$false} }
    [void][IO.Directory]::CreateDirectory((Join-Path $Root 'cache'))
    $managerLock = $null
    try { $managerLock = [IO.File]::Open((Join-Path $Root 'manager.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
    catch { return [pscustomobject]@{status='ManagerBusy'; hash=''; changed=$false} }
    try {
        $statePath = Join-Path $Root 'state.json'; $previous = $null
        if ([IO.File]::Exists($statePath)) {
            try {
                $previous = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($previous.schema -ne 1 -or $previous.hash -cnotmatch '\A[0-9a-f]{64}\z' -or
                    -not $previous.identity -or -not $previous.hash_checked_utc -or -not $previous.event_key) { $previous=$null }
            } catch { $previous=$null }
        }
        if (-not [IO.File]::Exists($config.telegram_exe)) { throw 'Configured Telegram.exe is missing; rerun installer with its current path.' }
        $file = Get-Item -LiteralPath $config.telegram_exe
        $identity = $file.Length.ToString()+':'+$file.LastWriteTimeUtc.Ticks.ToString()
        $reuse = $false
        if ($null -ne $previous -and -not $ForceHash) {
            try { $reuse = $previous.identity -ceq $identity -and $previous.hash -cmatch '\A[0-9a-f]{64}\z' -and
                ((Get-Date).ToUniversalTime()-[datetime]::Parse($previous.hash_checked_utc).ToUniversalTime()).TotalHours -lt 6 } catch { $reuse=$false }
        }
        $checked = (Get-Date).ToUniversalTime().ToString('o')
        if ($reuse) { $hash=$previous.hash; $checked=$previous.hash_checked_utc }
        else { $hash=Get-ManagerSha256 $config.telegram_exe }
        $catalog = Update-ManagerCatalog $Root ([bool]$ForceCatalog -or ($null -ne $previous -and $previous.hash -cne $hash))
        $profile = Get-ManagerProfile $catalog $hash
        $status='WaitingForAdapter'; $version=''; $bundle=''
        if ($null -ne $profile) {
            $version=$profile.telegram_version
            if ($hash -ceq $profile.output_sha256) { $status='Patched' }
            else {
                $bundle=Get-ManagerBundle $Root $profile
                $status='ReadyToRepair'
                if ($Repair) { $status=Install-ManagerPatch $Root $config.telegram_exe $hash $profile $bundle }
                if ($status -ceq 'Repaired') {
                    $hash=$profile.output_sha256; $checked=(Get-Date).ToUniversalTime().ToString('o')
                    $file=Get-Item -LiteralPath $config.telegram_exe
                    $identity=$file.Length.ToString()+':'+$file.LastWriteTimeUtc.Ticks.ToString()
                }
            }
        }
        $eventStatus = if ($status -ceq 'Repaired') { 'Patched' } else { $status }
        $eventKey=$eventStatus+':'+$hash
        $changed=$null -eq $previous -or $previous.event_key -cne $eventKey
        $state=[pscustomobject]@{schema=1;status=$status;hash=$hash;telegram_version=$version;identity=$identity;
            hash_checked_utc=$checked;checked_utc=(Get-Date).ToUniversalTime().ToString('o');event_key=$eventKey;changed=$changed}
        Write-ManagerJson $statePath $state
        return $state
    } finally { if ($null -ne $managerLock) { $managerLock.Dispose() } }
}

function Start-ManagerTelegram([string] $Target) {
    Start-Process -FilePath $Target -WorkingDirectory (Split-Path -Parent $Target)
}

function Start-ManagerVerifiedTelegram([string] $Root, $State) {
    $config = Read-ManagerConfig $Root
    if ($State.status -notin @('Patched','Repaired','WaitingForAdapter','PendingExit','NeedsOriginalBackup')) {
        throw ('Telegram was not started: '+$State.status)
    }
    $handle=$null; $hasher=$null
    try {
        $handle=[IO.File]::Open($config.telegram_exe,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        $hasher=[Security.Cryptography.SHA256]::Create()
        $actual=([BitConverter]::ToString($hasher.ComputeHash($handle))).Replace('-','').ToLowerInvariant()
        if ($actual -cne $State.hash) { throw 'Telegram changed after checking. Retry the launcher.' }
        Start-ManagerTelegram $config.telegram_exe
    } finally {
        if ($null -ne $hasher) { $hasher.Dispose() }
        if ($null -ne $handle) { $handle.Dispose() }
    }
}

function Show-ManagerNotice($State) {
    if (-not $State.changed) { return }
    $message = switch ($State.status) {
        'WaitingForAdapter' { 'Telegram updated. Waiting for a matching patch on GitHub. The official client is unchanged.' }
        'PendingExit' { 'A compatible patch is ready. Exit Telegram normally; it will be applied while Telegram is closed.' }
        'Repaired' { 'The exact-search patch has been restored. You can start Telegram normally.' }
        'NeedsOriginalBackup' { 'The verified official backup is missing. Open patch status for repair instructions.' }
        'Error' { 'The patch manager needs attention. Open last-error.json in its installation directory for details.' }
        default { '' }
    }
    if (-not $message) { return }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $icon=New-Object System.Windows.Forms.NotifyIcon
    try {
        $icon.Icon=[Drawing.SystemIcons]::Information; $icon.Visible=$true
        $icon.ShowBalloonTip(6000,'Telegram Exact Search Patch',$message,[Windows.Forms.ToolTipIcon]::Info)
        [Windows.Forms.Application]::DoEvents()
        Start-Sleep -Seconds 7
    } finally { $icon.Dispose() }
}
