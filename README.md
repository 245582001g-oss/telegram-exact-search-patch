# Telegram 简体中文搜索优化补丁

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

为 **Telegram Desktop 7.2.5 · Windows x64** 提供连续中文匹配、多关键词筛选、同文广告屏蔽与搜索响应优化。当前版本：**v1.0.0（r3）**。

这是社区补丁项目，与 Telegram 官方无隶属关系。仓库发布补丁源码和工具；用户在本机对经过哈希校验的官方程序生成补丁版。**不包含 Telegram 完整客户端、账号数据或个人黑名单。**

## 功能

- **完整连续匹配**：搜索 `美丽`，消息原文必须包含连续的 `美丽`，仅包含 `美` 不再满足条件。
- **消息多关键词 AND 匹配**：搜索 `好人 重庆`，同一条消息必须同时包含 `好人` 和 `重庆`；词组顺序不限，可以分布在不同行。
- **同文广告屏蔽**：右键左侧消息搜索结果，选择 **屏蔽相同内容**，立即隐藏已加载的同文结果，并过滤后续结果。
- **撤销**：右键仍可见的消息搜索结果，选择 **撤销上次屏蔽**。全部结果被隐藏时，也可使用管理脚本撤销。
- **响应优化**：搜索输入防抖从 900 ms 调整为 300 ms；黑名单先做长度排除，达到 256 条后使用辅助哈希索引。
- **迁移目录支持**：保存黑名单前解析程序的真实路径，处理 Windows 目录链接场景。

| 搜索词 | 消息原文 | 是否通过本地筛选 |
| --- | --- | --- |
| `美丽` | `美丽的城市` | 是 |
| `美丽` | `美好的城市` | 否 |
| `好人 重庆` | `重庆有很多好人` | 是 |
| `好人 重庆` | `好的人在重庆` | 否 |
| `好人 重庆` | `这里有好人` | 否 |

空格、全角空格等空白字符用于分隔消息搜索词组；每个词组自身必须连续。匹配保留大小写和繁简体，不做繁简转换、拼音扩展或模糊匹配。联系人、群、频道名称及用户名使用整个查询的字面匹配。

## 支持范围

- 仅支持 **Windows x64，Telegram Desktop 7.2.5** 的指定可执行文件；同版本号但哈希不同也会拒绝构建。
- 精确匹配作用于左上角全局搜索；内容黑名单也过滤聊天内消息搜索。
- 沿用 Telegram 的异步网络请求、取消、缓存与分页机制。补丁只过滤 Telegram 返回的候选，不能保证找到服务器未返回的内容，也没有建立完整历史索引。
- 自动更新可能覆盖补丁。遇到新版必须重新适配；工具会拒绝未知版本，不会将新版降级。
- 生成的修改版 EXE 不再具有官方 Authenticode 签名。

适用原版 `Telegram.exe` 的 SHA-256：

```text
24b0715d9b74374c1d70c9f9537f631d45c51d08a520f3a9a8b9e5df92ad169b
```

r3 已验证补丁版 SHA-256：

```text
894b04982521932a159397872604e0c96c9bd0bd8d48643f4a245899ea0a29c0
```

上游版本、源代码基线与下载入口见 [兼容性清单](compatibility.json) 和 [Telegram 官方 v7.2.5 发布页](https://github.com/telegramdesktop/tdesktop/releases/tag/v7.2.5)。以实际 EXE 哈希为准。不要为了本补丁覆盖正在使用的更高版本。

## 本地构建

需要 Windows x64、Python 3.10 或以上、支持 Windows x64 的 MinGW-w64 GCC，以及一份匹配上述哈希的官方 `Telegram.exe`。构建器只读取输入文件，在输出目录生成新文件，不会安装或启动 Telegram。

在仓库根目录运行 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\build_patch.py --input 'C:\TelegramPortable\Telegram.exe' --gcc 'C:\mingw64\bin\gcc.exe' --output-dir build
```

将示例路径替换为自己的实际路径。产物为 `build\Telegram.exact.exe`，构建报告为 `build\build-report.json`。同一源代码用不同编译器版本可能生成不同哈希；安装工具只接受本项目已验证的 r3 哈希。复现工具链与验证详情见 [验证说明](docs/verification.md)。

这条构建路线直接修改用户提供的官方二进制，不需要填写 `api_id` 或 `api_hash`。它不是 Telegram 完整客户端的源码构建流程。

## 安装与恢复

完全退出 Telegram 后运行：

```powershell
$patchedExe = (Resolve-Path 'build\Telegram.exact.exe').Path
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Install-Patch.ps1 -TelegramExe 'C:\TelegramPortable\Telegram.exe' -PatchedExe $patchedExe
```

安装工具校验原版和补丁版哈希，在目标程序旁保留 `Telegram.exe.before-chinese-search.bak`，再替换程序。检测到 Telegram 仍在运行或遇到未知文件时会拒绝操作。安装后自行启动 Telegram 验证搜索与右键菜单。

恢复官方原版：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Restore-Patch.ps1 -TelegramExe 'C:\TelegramPortable\Telegram.exe'
```

恢复时也要完全退出 Telegram。工具不启动或关闭 Telegram，不读取或修改 `tdata`，不启用后台维护。黑名单独立保存，恢复程序不会清空规则。

## 黑名单

“相同内容”以**整条消息完整原文**的 UTF-16 长度及 SHA-256 摘要判断，跨群同文消息也会被过滤。不同空格、换行或多一个字，属于不同内容。屏蔽不会删除聊天记录、退出群或拉黑发送者。

文件位于程序真实目录旁：`exact-search-blacklist.v1.bin`，最多 50,000 条规则，只记录长度和摘要。它仍属于个人数据，摘要也不等于加密；不要提交或分享自己的规则文件。

```powershell
# 查看规则数量
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Manage-Blacklist.ps1 -Action Status -Path 'C:\TelegramPortable\exact-search-blacklist.v1.bin'
# 撤销最后一条屏蔽
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Manage-Blacklist.ps1 -Action Undo -Path 'C:\TelegramPortable\exact-search-blacklist.v1.bin'
# 清空全部规则
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Manage-Blacklist.ps1 -Action Clear -Path 'C:\TelegramPortable\exact-search-blacklist.v1.bin'
```

脚本操作后，清空并重新输入搜索词以刷新结果。目录链接或迁移安装请传入真实目录。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tests\test_menu_payload.py --build-dir build --original 'C:\TelegramPortable\Telegram.exe'
```

回归测试在 Unicorn 模拟器中执行编译后的补丁，使用合成 Qt/WinAPI 对象及内存文件系统，不访问真实账号或聊天数据。它不等同于完整 Telegram UI 测试。详细覆盖与限制见 [验证说明](docs/verification.md)。

## 许可证

本项目原创补丁代码、脚本和文档采用 [MIT License](LICENSE)。Telegram Desktop 本体采用 [GPL-3.0 及上游附加条款](https://github.com/telegramdesktop/tdesktop/tree/v7.2.5)，本项目的 MIT 许可不改变 Telegram 及其依赖的许可。组合后的客户端不能作为纯 MIT 软件分发，详见 [NOTICE](NOTICE.md)。
