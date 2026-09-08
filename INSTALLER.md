# Telegram 精确搜索补丁安装器 v1.2.0

适用于指定官方 Telegram Desktop 7.2.7 Windows x64，精确搜索程序为 r4。

1. 解压整个 ZIP。
2. 双击 `Install.cmd`，选择自己使用的 `Telegram.exe`。
3. 安装器会在 `%LOCALAPPDATA%\TelegramExactSearchPatch` 保存管理器，并启用当前用户登录后自动检测。
4. 从托盘正常退出 Telegram，等待最多一个检查周期（默认 60 秒）及下载、重建时间，然后照常启动。

不需要管理员权限、Python 或编译器。当前 7.2.7 差分包已随包附带；其他版本需等待本项目发布对应适配。升级会覆盖 Telegram.exe，但外置管理器会保留，在有适配且 Telegram 退出时恢复。它不会强制关闭客户端，不保证未知新版立即兼容。

搜索 `好人` 时，消息必须包含连续的 `好人`，`好天气`、`好的人`、`好 人` 不通过。输入 `好人 重庆` 时同一条消息必须同时包含两个词。全局名称采用整个输入连续匹配；聊天内搜索保留原生关键词规则。补丁只在本地筛选 Telegram 返回的候选，不保证服务器召回所有匹配消息，也不是离线历史搜索。

安装后在 PowerShell 查看状态或操作（自定义安装目录请替换路径）：

```powershell
$manager = Join-Path $env:LOCALAPPDATA 'TelegramExactSearchPatch\tools\Manage-Patch.ps1'
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Check
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Repair
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Launch
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Stop
powershell -NoProfile -ExecutionPolicy Bypass -File $manager -Mode Uninstall
```

卸载管理器会停用监控并移除自己的登录快捷方式，保留 Telegram 和数据。恢复官方程序前务必先停止管理器，再使用本包 `tools\Restore-Patch.ps1 -TelegramExe '实际路径\Telegram.exe'`；它只接受对应的已验证原版备份。管理器文件留在原目录，可在监控退出后自行删除。重新启用时运行原解压目录中的 `Install.cmd`。

管理器只从 [本项目](https://github.com/245582001g-oss/telegram-exact-search-patch) 下载版本清单和数据差分包，不在线更新执行脚本。`state.json` 显示最近状态，`last-error.json` 记录需处理的错误。完整说明见 [源码与文档](https://github.com/245582001g-oss/telegram-exact-search-patch#readme)。

补丁和管理器不读取账号凭据或聊天数据文件。包内不包含 Telegram 完整程序或个人黑名单。修改后的 EXE 不再具有官方签名，原创贡献及上游许可说明见 `LICENSE`、`NOTICE.md`。
