#Requires -Version 5.1
<#
.SYNOPSIS
Inspect, undo, or clear the Chinese search patch local content blacklist.
.DESCRIPTION
Specify the absolute path to your own exact-search-blacklist.v1.bin.
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

    [Parameter(Mandatory = $true)]
    [string] $Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

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
        [byte[]] $magic = @(84, 71, 69, 88, 66, 76, 49, 0)
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
    if ([System.IO.Path]::GetFileName($databasePath) -ine 'exact-search-blacklist.v1.bin') {
        throw 'Path must name your own exact-search-blacklist.v1.bin file.'
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
