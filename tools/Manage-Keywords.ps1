#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('UI','List','Add','Remove')][string]$Action='UI',
    [ValidateSet('Body','Name')][string]$Scope='Body',
    [string]$Text,
    [string]$Path=(Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Telegram\blacklists\exact-search-keywords.v1.bin')
)
$ErrorActionPreference='Stop'
$Path=[IO.Path]::GetFullPath($Path)
$keywordEncoding=New-Object Text.UnicodeEncoding($false,$false,$true)
function Read-KeywordRules {
    if(-not [IO.File]::Exists($Path)){ return }
    if((Get-Item -LiteralPath $Path).Length -gt 67600){throw 'Keyword file exceeds size limit.'}
    $bytes=[IO.File]::ReadAllBytes($Path)
    if($bytes.Length -lt 16 -or $bytes.Length -gt 67600 -or
       [Text.Encoding]::ASCII.GetString($bytes,0,8) -cne "TGEXKW1`0" -or
       [BitConverter]::ToUInt32($bytes,8) -ne 1){ throw 'Invalid keyword file; original file was preserved.' }
    $count=[BitConverter]::ToUInt32($bytes,12)
    if($count -gt 256 -or $bytes.Length -ne 16+264*$count){ throw 'Invalid keyword record count.' }
    for($i=0;$i -lt $count;$i++){
        $offset=16+264*$i
        $kind=[BitConverter]::ToUInt32($bytes,$offset)
        $length=[BitConverter]::ToUInt32($bytes,$offset+4)
        if($kind -notin @(1,2) -or $length -lt 1 -or $length -gt 128){ throw 'Invalid keyword record.' }
        $value=$keywordEncoding.GetString($bytes,$offset+8,$length*2)
        Assert-Keyword $value
        for($j=$offset+8+$length*2;$j -lt $offset+264;$j++){ if($bytes[$j] -ne 0){ throw 'Invalid keyword padding.' } }
        [pscustomobject]@{Scope=$(if($kind -eq 1){'Body'}else{'Name'});Text=$value}
    }
}
function Assert-Keyword([string]$Value){
    if($Value.Length -lt 1 -or $Value.Length -gt 128 -or $Value -match '[\x00-\x1f\x7f]' -or
       $Value -match '^[ \u3000\u200b\ufeff]*$'){ throw 'Enter 1-128 valid characters, not only whitespace.' }
    $null=$keywordEncoding.GetBytes($Value)
}
function Change-Keyword([bool]$Remove,[string]$Kind,[string]$Value){
    Assert-Keyword $Value
    $directory=[IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path))
    $null=[IO.Directory]::CreateDirectory($directory)
    $lock=$null;$temporary=$null
    try {
        $lock=[IO.File]::Open($Path+'.lock',[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        $rules=@(Read-KeywordRules)
        $exists=@($rules | Where-Object {$_.Scope -eq $Kind -and $_.Text -ceq $Value}).Count -gt 0
        if(($Remove -and -not $exists) -or (-not $Remove -and $exists)){return}
        if($Remove){$rules=@($rules | Where-Object {-not ($_.Scope -eq $Kind -and $_.Text -ceq $Value)})}
        else {
            if($rules.Count -ge 256){throw 'Keyword limit reached (256).'}
            $rules+= [pscustomobject]@{Scope=$Kind;Text=$Value}
        }
        $bytes=New-Object byte[] (16+264*$rules.Count)
        [Text.Encoding]::ASCII.GetBytes("TGEXKW1`0").CopyTo($bytes,0)
        [BitConverter]::GetBytes([uint32]1).CopyTo($bytes,8)
        [BitConverter]::GetBytes([uint32]$rules.Count).CopyTo($bytes,12)
        for($i=0;$i -lt $rules.Count;$i++){
            $offset=16+264*$i;$rule=$rules[$i]
            $kindNumber=if($rule.Scope -eq 'Body'){1}else{2}
            [BitConverter]::GetBytes([uint32]$kindNumber).CopyTo($bytes,$offset)
            [BitConverter]::GetBytes([uint32]$rule.Text.Length).CopyTo($bytes,$offset+4)
            $keywordEncoding.GetBytes($rule.Text).CopyTo($bytes,$offset+8)
        }
        $temporary=$Path+'.tmp.'+[Guid]::NewGuid().ToString('N')
        $stream=[IO.File]::Open($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
        if(-not ('TelegramKeywordFiles' -as [type])){
            Add-Type @'
using System.Runtime.InteropServices;
public static class TelegramKeywordFiles {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool MoveFileEx(string source, string target, uint flags);
}
'@
        }
        if(-not [TelegramKeywordFiles]::MoveFileEx($temporary,$Path,9)){
            throw ('Atomic replacement failed: '+[Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        $temporary=$null
    } finally {
        if($temporary -and [IO.File]::Exists($temporary)){[IO.File]::Delete($temporary)}
        if($lock){$lock.Dispose()}
    }
}
try {
    if($Action -eq 'List'){Read-KeywordRules;return}
    if($Action -ne 'UI'){Change-Keyword ($Action -eq 'Remove') $Scope $Text;return}
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [Windows.Forms.Application]::EnableVisualStyles()
    $form=New-Object Windows.Forms.Form
    $form.Text='管理关键词屏蔽';$form.Size=New-Object Drawing.Size(660,450)
    $form.StartPosition='CenterScreen';$form.MinimumSize=$form.Size
    $form.Font=New-Object Drawing.Font('Microsoft YaHei UI',10)
    $label=New-Object Windows.Forms.Label
    $label.Text='规则仅过滤广播频道搜索结果。修改后重新搜索生效。';$label.SetBounds(16,14,620,25)
    $list=New-Object Windows.Forms.ListBox;$list.SetBounds(16,44,610,205);$list.DisplayMember='Display'
    $scopeBox=New-Object Windows.Forms.ComboBox;$scopeBox.SetBounds(16,262,170,28)
    $scopeBox.DropDownStyle='DropDownList';$null=$scopeBox.Items.AddRange(@('消息正文包含','频道名称包含'));$scopeBox.SelectedIndex=0
    $inputBox=New-Object Windows.Forms.TextBox;$inputBox.SetBounds(194,262,430,28);$inputBox.MaxLength=4096
    $hint=New-Object Windows.Forms.Label;$hint.SetBounds(16,300,610,30)
    $hint.Text='连续文字匹配，英文区分大小写；最多 128 个字。'
    $add=New-Object Windows.Forms.Button;$add.Text='添加规则';$add.SetBounds(400,348,105,34)
    $remove=New-Object Windows.Forms.Button;$remove.Text='删除所选';$remove.SetBounds(16,348,105,34)
    $close=New-Object Windows.Forms.Button;$close.Text='关闭';$close.SetBounds(518,348,105,34)
    $refresh={
        $list.Items.Clear()
        foreach($r in @(Read-KeywordRules)){
            $prefix=if($r.Scope -eq 'Body'){'正文：'}else{'频道名：'}
            $null=$list.Items.Add([pscustomobject]@{Scope=$r.Scope;Text=$r.Text;Display=$prefix+$r.Text})
        }
    }
    $showError={param($message) [void][Windows.Forms.MessageBox]::Show($form,$message,'规则未保存','OK','Error')}
    $add.Add_Click({
        try{
            Assert-Keyword $inputBox.Text
            if($inputBox.Text.Length -lt 4 -and [Windows.Forms.MessageBox]::Show($form,'关键词很短，可能隐藏正常内容。仍要添加吗？','确认关键词','YesNo','Warning','Button2') -ne 'Yes'){return}
            $kind=if($scopeBox.SelectedIndex -eq 0){'Body'}else{'Name'}
            Change-Keyword $false $kind $inputBox.Text
            & $refresh;$inputBox.Clear()
        }catch{& $showError $_.Exception.Message}
    })
    $remove.Add_Click({try{if($list.SelectedItem){$r=$list.SelectedItem;Change-Keyword $true $r.Scope $r.Text;& $refresh}}catch{& $showError $_.Exception.Message}})
    $close.Add_Click({$form.Close()})
    $form.Controls.AddRange(@($label,$list,$scopeBox,$inputBox,$hint,$add,$remove,$close))
    $form.CancelButton=$close
    try{& $refresh;[void]$form.ShowDialog()}finally{$form.Dispose()}
}catch{
    if($Action -eq 'UI'){
        Add-Type -AssemblyName System.Windows.Forms
        [void][Windows.Forms.MessageBox]::Show($_.Exception.Message,'关键词管理未完成','OK','Error')
    }else{Write-Error $_.Exception.Message}
    exit 1
}
