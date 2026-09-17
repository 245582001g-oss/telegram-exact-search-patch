# 精确搜索补丁安装器 v1.3.0

完整便携版直接运行 Telegram.exe，无需安装器。已有 Telegram 的用户可解压独立安装器 ZIP，双击 Install.cmd 并选择自己的 Telegram.exe。支持精确校验的 Windows x64 7.2.8（r5）及旧 7.2.7（r4）。

管理器安装在 %LOCALAPPDATA%\TelegramExactSearchPatch，并启用当前用户登录后的隐藏监控。正常退出 Telegram 后，管理器才会应用匹配差分包；不会强制结束进程。账号数据不复制、不上传，原版 EXE 备份保留。未知版本等待适配。

v1.3.0 的 7.2.8 补丁增加频道 ID 屏蔽，规则保存在“我的文档”\Telegram\blacklists。新的客户端配置默认关闭自动更新；已有设置不被覆盖。首次启动校验迁移旧规则。使用与撤销方式见 README.md。

管理器手动操作：

```powershell
$manager = Join-Path $env:LOCALAPPDATA 'TelegramExactSearchPatch\tools\Manage-Patch.ps1'
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Check
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Repair
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Stop
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Uninstall
```

恢复官方 EXE 前先停止管理器，再使用 tools\Restore-Patch.ps1 -TelegramExe '实际路径\Telegram.exe'，需要对应已校验备份。卸载管理器仅停用监控并移除其快捷方式，不删除 Telegram 或规则。详细行为见 docs/update-persistence.md。
