#Requires -Version 5.1
<#
.SYNOPSIS
Inspect, undo, or clear local content or channel search rules.
.DESCRIPTION
Defaults to the current user's Documents\Telegram\blacklists directory.
Use -Kind Channel for channel rules; -Path optionally selects an absolute file.
Status reports the count; Undo removes the last entry; Clear removes all entries.
The database stores text lengths and digests, not message text. Search again in
Telegram after Undo or Clear. This script does not control Telegram processes
or modify chats. Missing databases are treated as empty and are not created.
.EXAMPLE
.\Manage-Blacklist.ps1 -Path 'D:\Telegram\exact-search-blacklist.v1.bin'
.EXAMPLE
.\Manage-Blacklist.ps1 -Action Undo -Path 'D:\Telegram\exact-search-blacklist.v1.bin'
.EXAMPLE
.\Manage-Blacklist.ps1 -Action Clear -Path 'D:\Telegram\exact-search-blacklist.v1.bin'
#>
[CmdletBinding()]
param(
    [ValidateSet('Status', 'Undo', 'Clear')]
    [string] $Action = 'Status',

    [ValidateSet('Content', 'Channel')]
    [string] $Kind = 'Content',

    [string] $Path = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$databaseName = if ($Kind -eq 'Channel') { 'exact-search-channels.v1.bin' } else { 'exact-search-blacklist.v1.bin' }
if ([string]::IsNullOrWhiteSpace($Path)) {
    $documents = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
    if ([string]::IsNullOrWhiteSpace($documents)) { throw 'Cannot locate the Windows Documents folder.' }
    $Path = Join-Path (Join-Path $documents 'Telegram\blacklists') $databaseName
}

function Get-AbsoluteFilePath {
    param([string] $Value)
    if ([string]::IsNullOrWhiteSpace($Value) -or
        ($Value -notmatch '^[A-Za-z]:[\\/]' -and $Value -notmatch '^\\\\[^\\]+\\[^\\]+[\\/]')) {
        throw 'A fully qualified Windows file path is required.'
    }
    return [System.IO.Path]::GetFullPath($Value)
}

function Read-Blacklist {
    param([string] $DatabasePath)
    $reader = $null
    try {
        try {
            # Allow atomic replacement while this handle reads a consistent snapshot.
            $reader = [System.IO.File]::Open($DatabasePath,
                [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
                ([System.IO.FileShare]::Read -bor [System.IO.FileShare]::Delete))
        } catch [System.IO.FileNotFoundException] {
            return $null
        } catch [System.IO.DirectoryNotFoundException] {
            return $null
        }
        $length = $reader.Length
        if ($length -lt 16 -or $length -gt (16 + 50000 * 36)) {
            throw 'Invalid blacklist size; refusing to modify it.'
        }
        $bytes = New-Object byte[] ([int] $length)
        $offset = 0
        while ($offset -lt $bytes.Length) {
            $read = $reader.Read($bytes, $offset, $bytes.Length - $offset)
            if ($read -le 0) { throw 'Incomplete blacklist; refusing to modify it.' }
            $offset += $read
        }
        if ($reader.ReadByte() -ne -1) {
            throw 'Blacklist size changed during the read; refusing to modify it.'
        }
        [byte[]] $magic = if ($Kind -eq 'Channel') { @(84, 71, 69, 88, 67, 72, 49, 0) } else { @(84, 71, 69, 88, 66, 76, 49, 0) }
        for ($i = 0; $i -lt $magic.Length; $i++) {
            if ($bytes[$i] -ne $magic[$i]) {
                throw 'Invalid blacklist signature; refusing to modify it.'
            }
        }
        $version = [System.BitConverter]::ToUInt32($bytes, 8)
        $count = [System.BitConverter]::ToUInt32($bytes, 12)
        if ($version -ne 1 -or $count -gt 50000 -or $length -ne (16L + 36L * $count)) {
            throw 'Invalid blacklist version, count, or size; refusing to modify it.'
        }
        for ($i = 0; $i -lt $count; $i++) {
            if ($Kind -eq 'Channel') {
                $at = 16 + $i * 36
                $id = [System.BitConverter]::ToUInt64($bytes, $at + 4)
                if ([System.BitConverter]::ToUInt32($bytes, $at) -ne 8 -or
                    ($id -shr 48) -ne 2 -or ($id -band 281474976710655L) -eq 0) {
                    throw 'Invalid channel ID; refusing to modify it.'
                }
                for ($j = 12; $j -lt 36; $j++) {
                    if ($bytes[$at + $j] -ne 0) { throw 'Invalid channel record; refusing to modify it.' }
                }
            }
            if ([System.BitConverter]::ToUInt32($bytes, 16 + $i * 36) -gt 2147483647) {
                throw 'Invalid text length in blacklist; refusing to modify it.'
            }
        }
        return [pscustomobject] @{ Bytes = $bytes; Count = [int] $count }
    } finally {
        if ($null -ne $reader) { $reader.Dispose() }
    }
}

function Save-BlacklistAtomically {
    param([string] $DatabasePath, [byte[]] $Bytes)
    $temporary = $DatabasePath + '.tmp.manager.' + [Guid]::NewGuid().ToString('N')
    $writer = $null
    $created = $false
    try {
        $writer = New-Object System.IO.FileStream($temporary,
            [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None, 4096, [System.IO.FileOptions]::WriteThrough)
        $created = $true
        $writer.Write($Bytes, 0, $Bytes.Length)
        $writer.Flush($true)
        $writer.Dispose()
        $writer = $null
        # Windows PowerShell 5.1 converts ordinary $null to an empty string; use NullString.
        # No delete-then-move fallback: a failed replacement keeps the original file.
        [System.IO.File]::Replace($temporary, $DatabasePath, [NullString]::Value)
        $created = $false
    } finally {
        if ($null -ne $writer) { $writer.Dispose() }
        if ($created) { [System.IO.File]::Delete($temporary) }
    }
}

try {
    $databasePath = Get-AbsoluteFilePath $Path
    if ([System.IO.Path]::GetFileName($databasePath) -ine $databaseName) {
        throw ('Path must name your own ' + $databaseName + ' file.')
    }
    $database = Read-Blacklist $databasePath
    $count = if ($null -eq $database) { 0 } else { $database.Count }
    if ($Action -eq 'Status') {
        Write-Output ('Blacklist entries: {0}' -f $count)
        return
    }
    # Do not create a database, lock, or directory when the database is absent.
    if ($null -eq $database) {
        Write-Output 'Blacklist entries: 0. Nothing to change.'
        return
    }

    $lockHandle = $null
    try {
        try {
            # Use the same lock file as the patch CreateFileW(OPEN_ALWAYS, share=0).
            $lockHandle = [System.IO.File]::Open($databasePath + '.lock',
                [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None)
        } catch [System.IO.IOException] {
            throw 'Blacklist is busy or its lock file cannot be opened. Retry later; the database was not changed.'
        }
        # Read again under the lock to preserve entries just added by Telegram.
        $database = Read-Blacklist $databasePath
        if ($null -eq $database -or $database.Count -eq 0) {
            Write-Output 'Blacklist entries: 0. Nothing to change.'
            return
        }
        $newCount = if ($Action -eq 'Undo') { $database.Count - 1 } else { 0 }
        $resultBytes = New-Object byte[] (16 + 36 * $newCount)
        [System.Buffer]::BlockCopy($database.Bytes, 0, $resultBytes, 0, $resultBytes.Length)
        [System.Buffer]::BlockCopy([System.BitConverter]::GetBytes([uint32] $newCount), 0,
            $resultBytes, 12, 4)
        Save-BlacklistAtomically $databasePath $resultBytes
        if ($Action -eq 'Undo') {
            Write-Output ('Last entry removed. Blacklist entries: {0}. Search again in Telegram to refresh results.' -f $newCount)
        } else {
            Write-Output 'Blacklist cleared. Blacklist entries: 0. Search again in Telegram to refresh results.'
        }
    } finally {
        if ($null -ne $lockHandle) { $lockHandle.Dispose() }
    }
} catch {
    Write-Error -Message ('Operation failed: {0}' -f $_.Exception.Message) -ErrorAction Continue
    exit 1
}
