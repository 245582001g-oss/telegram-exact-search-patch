# telegram 重庆好人版 7.2.8 + 精确搜索

基于 **Telegram Desktop 7.2.8 · Windows x64** 的社区修改版。补丁版本 **v1.4.0 / r6**，与 Telegram 官方无隶属关系。

[下载完整便携版](https://github.com/245582001g-oss/telegram-exact-search-patch/releases/tag/v1.4.0) · [搜索示例](docs/search-guide.md) · [验证说明](docs/verification.md) · [构建与许可](NOTICE.md)

## 直接使用

下载 Release 中的 `telegram-chongqing-haoren-7.2.8-exact-search.zip`，完整解压后运行 `Telegram/Telegram.exe`，首次使用自行登录。无需安装 Python、编译器或补丁管理器。请放在可以写入的文件夹中。

整包由官方便携版文件重新组装，不含发布者的 `tdata`、登录凭据、聊天记录、缓存、日志、配置或个人黑名单。登录后 Telegram 会在本机创建自己的数据。

## 功能

- **精确搜索**：搜 `好人`，要求连续出现 `好人`；`好天气`、`好的人`、`好 人` 不通过。
- **多词组合**：搜 `好人 重庆`，同一条消息必须同时包含两项，顺序和所在行不限。支持中文、英文和混合文字，区分大小写，不自动翻译。
- **屏蔽相同内容**：在消息搜索结果上右键，屏蔽全文相同的重复信息，支持撤销。
- **屏蔽整个频道**：在频道的消息搜索结果上右键 → **屏蔽整个频道**。以固定频道 ID 识别，改文案、频道名称或用户名不会绕过。当前消息结果立即清理，后续消息页及全局频道名称结果也会过滤。
- **关键词屏蔽**：屏蔽整个频道后，可以跳过提示，也可以修改建议片段后保存。正文规则跨频道隐藏包含指定片段的消息；频道名称规则隐藏名称包含片段的广播频道搜索结果。规则用于后续加载的结果，不要求全文相同。
- **管理关键词**：搜索结果右键 → 管理关键词屏蔽，可添加和删除；结果全部被隐藏时，双击解压根目录的 `Manage-Keywords.cmd`。
- **撤销上次频道屏蔽**：在仍可见的消息搜索结果上右键撤销。内容规则和频道规则分别记录、分别撤销。
- 搜索输入防抖为 300 ms。已屏蔽频道在读取和匹配消息文字之前过滤。
- **新配置默认关闭自动更新**。可以在 Telegram 的设置 → 高级 → 版本和更新中重新开启。已有用户的已保存设置优先；开启后官方更新可能覆盖修改版。

频道操作只对广播频道显示，不对普通用户或群组显示。过滤针对消息所在频道，不依据转发署名。它隐藏本机搜索结果，不是退订、举报或 Telegram 账号级封禁；频道正常聊天页面不受影响。

补丁处理 Telegram 已返回的候选结果，不能改变服务器索引、召回量或服务器负载。搜索结果为空时可调整关键词继续搜索。全局消息支持空白分隔的 AND 组合；全局名称按整个输入连续匹配；聊天内关键词保持原生行为，但屏蔽规则仍生效。

## 黑名单存放位置

首次启动自动创建 **Windows“我的文档”\Telegram\blacklists**：

- `exact-search-blacklist.v1.bin`：全文长度和 SHA-256 摘要，不保存消息原文。
- `exact-search-channels.v1.bin`：固定频道 ID，不保存频道名称、用户名或消息内容。
- `exact-search-keywords.v1.bin`：你确认保存的关键词原文和作用范围。最多 256 条，每条最多 128 个 UTF-16 单元；连续匹配、区分大小写，多条规则为 OR。不使用正则表达式、分词或自动语义分类。

使用 Windows 系统目录定位，支持更换盘符、中文路径及 OneDrive 重定向。若旧版规则在 Telegram.exe 旁边，且新位置尚无规则，首次启动会校验并复制迁移，原文件保留。已存在的新规则不会被清空或覆盖。规则读写失败或损坏不会阻止客户端启动；保存失败会明确提示，损坏文件不会被静默重置。

关键词可能误伤正常内容。建议选择固定广告片段，避免泛词；建议词只是从所选消息摘取的片段，不代表自动识别出了垃圾。仅广播频道参与关键词匹配，普通用户和群组不受关键词规则影响。新增正文规则不自动将所有命中频道加入 ID 黑名单。

如果所有搜索结果都被屏蔽，关键词规则可用 `Manage-Keywords.cmd` 删除；频道规则可在解压目录的 PowerShell 中撤销最后一条：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Manage-Blacklist.ps1 -Kind Channel -Action Undo
```

`-Action Status` 查看数量，`-Action Clear` 清空所选类别；`-Kind Content` 操作内容规则。修改后重新搜索。规则目录是当前 Windows 用户共享的；若“我的文档”由 OneDrive 管理，目录也遵循该系统同步配置。

## 已有客户端与后续更新

已有 7.2.8 客户端可下载独立安装器 ZIP 并运行 `Install.cmd`，选择自己的 Telegram.exe。管理器安装到 Telegram 文件夹之外，等待客户端正常退出后应用匹配的差分包。原版备份保留，账号目录不复制也不改写。7.2.7 的旧适配包继续可用。

未知版本会拒绝打补丁，必须重新适配。默认关闭自动更新不代表以后无需更新；升级前请查看本项目是否已有对应版本。管理器详情见 [更新恢复说明](docs/update-persistence.md)。

## 构建与验证

需要 Python 3、`requirements-dev.txt` 中依赖及 MinGW-w64 GCC。输入必须是 SHA-256 精确匹配的官方 7.2.8 x64 EXE。

```powershell
python -m pip install -r requirements-dev.txt
python src/build_patch.py --input C:\TelegramOriginal\Telegram.exe --output-dir build --gcc C:\mingw64\bin\gcc.exe
python tests/test_menu_payload.py --build-dir build --original C:\TelegramOriginal\Telegram.exe
python tests/test_channel_payload.py --build-dir build --original C:\TelegramOriginal\Telegram.exe
python tests/test_keyword_payload.py --build-dir build
python tests/test_language_examples.py --build-dir build
```

构建检查原始节内容、入口桥接、异常展开表、ASLR/NX、重定位、PE 校验和及 Windows SEC_IMAGE 装载。测试运行实际编译的 x64 代码；Qt/WinAPI 使用合成对象，不能据此声称真实账号的菜单点击已验收。具体边界见 [验证说明](docs/verification.md)。

修改后的 EXE 不具有 Telegram 官方 Authenticode 签名。下载后可用 Release 的 `SHA256SUMS.txt` 校验文件完整性。

## 许可与源码

Telegram 及组合客户端遵循上游 GPLv3 或更高版本及相关例外；本项目原创补丁代码为 MIT。第三方组件保留其各自许可。Release 提供本项目源码、构建脚本和差分包，并链接同版本的[上游完整源码](https://github.com/245582001g-oss/telegram-exact-search-patch/releases/download/v1.3.0/tdesktop-7.2.8-full.tar.gz)。见 [NOTICE.md](NOTICE.md)、[上游许可](licenses/Telegram-LICENSE.txt) 及完整源码中的依赖许可。
