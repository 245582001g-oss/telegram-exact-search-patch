# Telegram 精确搜索 Patch | Telegram Exact Search Patch

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

为 **Telegram Desktop 7.2.7 · Windows x64** 提供精确文字筛选、多关键词组合、同文广告屏蔽与搜索响应优化。**支持中文、英文及其他语言，也支持中英等多语言混合输入。** 当前工具版本：**v1.2.1**，搜索补丁仍为已验证的 **r4**。

Exact text filtering, multi-keyword AND search, and identical-content blocking for Telegram Desktop. Supports Chinese, English, and other languages through case-sensitive literal matching.

[搜索搭配](#搜索搭配速查) · [多语言规则](#英文与其他语言) · [如何安装](#如何安装) · [如何卸载](#如何卸载或恢复原版) · [常见问题](#常见问题)

这是社区补丁项目，与 Telegram 官方无隶属关系。仓库发布补丁源码、外置安装器及小型差分包；安装器在本机对经过哈希校验的官方程序生成补丁版。**不包含 Telegram 完整客户端、账号数据或个人黑名单。**

## 快速了解

- **按你输入的文字筛选**：搜 `美丽`，保留包含连续 `美丽` 的消息，排除只有 `美` 或 `美好` 的消息。
- **搜 `好人` 必须连续包含 `好人`**：保留 `他是好人`、`好人一生平安`；排除 `好天气`、`好的人`、`好 人`。7.2.7 安装后已由用户实测确认。
- **把条件组合起来搜**：搜 `Python 教程 入门`，要求**同一条消息三个词都包含**。词的顺序不限，也可以分布在消息的不同行。
- **英文、其他语言和混合文字都能参与匹配**：例如 `remote Python`、`東京 カフェ`、`Python 中文 教程`。它按原文匹配，不会自动翻译搜索词。
- **手动屏蔽反复出现的同文广告**：右键某条消息搜索结果 → **屏蔽相同内容**，当前及之后的同文结果都会被过滤；支持撤销。
- **缩短输入后的等待**：搜索输入防抖从 900 ms 调整为 300 ms，并减少本地黑名单筛选开销。实际联网耗时仍取决于 Telegram 和网络。

**已经安装补丁后，直接在 Telegram 左上角全局搜索框输入即可，不需要打开单独的搜索软件。**

> 下文的“匹配”均指通过补丁的本地文字筛选。补丁筛选的是 Telegram 已返回的候选，不是整个 Telegram 的独立搜索引擎；例子符合条件，也不保证服务器一定返回这条内容。

## 搜索搭配速查

以下组合用于**左上角全局搜索中的消息结果**。用空格把需要同时出现的文字隔开。

| 想找什么 | 可以输入 | 同一条消息必须包含 |
| --- | --- | --- |
| 某个完整中文词 | `美丽` | 连续的 `美丽` |
| 一个主题和一个地点 | `好人 重庆` | `好人`、`重庆` |
| 某城市某技术的招聘 | `上海 Python 招聘` | `上海`、`Python`、`招聘` |
| 一种语言的入门教程 | `Python 教程 入门` | `Python`、`教程`、`入门` |
| 英文远程职位信息 | `remote Python` | 小写 `remote`、大写 P 开头的 `Python` |
| 产品型号和供货状态 | `RTX 5080 现货` | `RTX`、`5080`、`现货` |
| 某个版本的特定问题 | `v1.2 登录` | `v1.2`、`登录` |
| 错误码与系统名称 | `0x80070005 Windows` | `0x80070005`、`Windows` |
| 中英混合内容 | `Python 中文 教程` | `Python`、`中文`、`教程` |
| 日文地点和主题 | `東京 カフェ` | `東京`、`カフェ` |
| 韩文地点和主题 | `서울 카페` | `서울`、`카페` |

搭配方式可以是 **主题＋地点**、**产品＋型号＋状态**、**技术＋用途＋难度**，或者 **错误码＋环境**。补丁只检查这些文字是否出现，不理解招聘条件、价格范围或产品型号的含义。

例如先搜 `Python`，再试 `Python 教程`，最后试 `Python 教程 入门`，可以逐步增加必须满足的文字条件。如果结果太少，先删去一个限定词，或把大小写改成消息实际使用的写法。

## 单词与多词组怎样匹配

### 单个词组：连续包含，不要求整条消息相等

搜索 `美丽` 时，`美丽的城市` 和 `这座城市很美丽` 都符合条件；`美好的城市`、`美 丽的城市` 都不符合。

英文采用同样规则。搜索 `cat`，`cat`、`cats`、`concatenate` 都包含连续的 `cat`，所以都符合本地条件。**“精确”指输入字符连续一致，并不表示英文整词匹配，也不要求消息全文等于搜索词。**

### 多个词组：空格表示“都要有”

搜索 `好人 重庆`，要求 `好人` 和 `重庆` 出现在**同一条消息**中。

| 输入 | 消息原文 | 本地筛选结果与原因 |
| --- | --- | --- |
| `好人 重庆` | `重庆有很多好人` | 通过：两个词都有，顺序不限 |
| `好人 重庆` | `好人在重庆生活` | 通过：两个词都有 |
| `好人 重庆` | 第一行 `重庆`，第二行 `这里有好人` | 通过：同一条消息内可以跨行分布 |
| `好人 重庆` | `这里有好人` | 排除：缺少 `重庆` |
| `好人 重庆` | `好的人在重庆` | 排除：没有连续的 `好人` |
| `Python 教程 入门` | `适合入门学习的 Python 视频教程` | 通过：三个词都有 |
| `Python 教程 入门` | `Python 高级教程` | 排除：缺少 `入门` |
| `red apple` | `apple is red` | 通过：两个词都有，不要求形成连续短语 |
| `red apple` | `a red car` | 排除：缺少 `apple` |

一条消息只有 `好人`、另一条消息只有 `重庆`，不能合在一起满足条件。每个词组自身仍必须连续，例如 `好` 和 `人` 被空格或换行隔开，就不算 `好人`。

普通空格、多个空格、全角空格、制表符和换行等空白可分隔消息搜索词组。**逗号不是分隔符**：`Python,教程` 会作为一个连续词组，要求原文也有这段逗号相连的文字。

### 引号和运算符

补丁没有额外实现引号短语、OR、排除词、正则或通配符语法。

| 输入 | 补丁本地筛选的含义 |
| --- | --- |
| `Python 教程` | 同一条消息同时包含 `Python` 和 `教程` |
| `Python OR Java` | 三个词 `Python`、`OR`、`Java` 都要有；不是二选一 |
| `Python -广告` | 同时要求 `Python` 和字面文字 `-广告`；不是排除广告 |
| `Py*` | 要求包含字面的 `Py*`；星号不代表任意文字 |
| `"red apple"` | 空格仍会分词，要求包含 `"red` 和 `apple"`；引号不会启用连续短语模式 |

想过滤同文广告，应使用右键 **屏蔽相同内容**。想尝试两个不同主题，可以分别搜索；本补丁没有 OR 合并搜索功能。

## 英文与其他语言

**支持。匹配逻辑按原文的 Unicode 字符序列比较，不限定中文，也不依赖中文分词词典。** 简体中文、繁体中文、英文、日文、韩文、俄文、阿拉伯文、西班牙文等文字都可以作为搜索条件；也可以在同一次消息搜索中混合不同语言。数字、标点和 emoji 也可以参与原样文字匹配。

| 语言或用法 | 输入示例 | 符合本地条件的原文示例 |
| --- | --- | --- |
| 英文 | `remote Python` | `Python jobs: remote work available` |
| 繁体中文 | `臺北 咖啡` | `臺北的咖啡店推薦` |
| 日文 | `東京 カフェ` | `東京でカフェ巡り` |
| 韩文 | `서울 카페` | `서울의 조용한 카페를 소개합니다` |
| 俄文 | `Москва работа` | `Москва: работа для разработчика` |
| 阿拉伯文 | `دبي عمل` | `فرص عمل في دبي` |
| 西班牙文 | `café Madrid` | `Un café en Madrid` |
| 中英混合 | `Python 中文 教程` | `这里有中文讲解的 Python 入门教程` |
| 文字与 emoji | `咖啡 ☕` | `今天喝咖啡 ☕` |

使用外语时，需要注意这些字符规则：

- **区分大小写**：`Python` 不匹配只写了 `python` 的消息，`remote` 不等同于 `Remote`。
- **不自动翻译**：`coffee` 不会自动匹配只有 `咖啡` 的消息。输入 `coffee 咖啡`，表示同一条消息两种写法都要有。
- **不做繁简转换**：`美丽` 与 `美麗`、`台北` 与 `臺北` 是不同文字。
- **不忽略重音或全半角差异**：`café` 与 `cafe`、`ＡＢＣ` 与 `ABC` 不等同。
- **不做 Unicode 归一化**：外观相同的重音字母可能由不同字符序列组成，部分 emoji 也含变体选择符、肤色或连接字符。遇到看起来相同却未命中的文字，可以复制原文中的对应词再搜索。

多语言支持指本地匹配规则适用这些文字，不代表跨语言翻译、语义搜索或绕过 Telegram 的服务端搜索范围。

## 搜消息、搜联系人和搜群，有什么区别

| 搜索位置或结果类型 | 本补丁的规则 | 示例 |
| --- | --- | --- |
| 左上角全局搜索的消息结果 | 按空白分词，各词组都必须出现 | `New York` 可匹配消息 `York is different from New` |
| 左上角全局搜索的联系人、群、频道名称 | 整个输入按连续文字匹配 | `New York` 可匹配名称 `New York Travel`，不匹配 `York New Travel` |
| 用户名 | 按输入文字匹配用户名，也支持 `@` 开头的写法 | 可尝试 `@news_daily` |
| 进入某个聊天后的聊天内消息搜索 | 保留 Telegram 原生关键词规则；内容黑名单仍会过滤结果 | 不要把上面的全局多词组 AND 规则直接套用到聊天内搜索 |

联系人、群名、频道名和用户名同样区分字符大小写。名称搜索不会把多个名称、不同用户名或不同消息的文字拼起来满足条件。

## 怎样屏蔽重复广告

1. 在左上角搜索，找到一条不想再看到的消息结果。
2. 右键该条目，选择 **屏蔽相同内容**。
3. 已加载的同文结果立即移除；后续搜索返回相同原文时，也会自动过滤。
4. 想反悔时，右键仍可见的消息结果，选择 **撤销上次屏蔽**，当前搜索会重新加载。

例如群 A、群 B 和群 C 都发送 `课程优惠，联系 @example`。屏蔽其中一条后，其余完整原文相同的消息也会被过滤。若另一条改成 `课程优惠！联系 @example`，标点不同，就不属于同一内容，需要另行屏蔽。

这里屏蔽的是**整条消息原文**，不是左栏截断后的预览文字，也不是发送者、关键词或群。两条预览看着相同，隐藏的后半段不同，仍属于不同内容。

补丁不会默认把所有重复消息折叠成一条；只有主动加入黑名单的内容才会隐藏。规则在重启后保留，适用于使用同一程序目录及规则文件的搜索，不会自动同步到手机或其他设备。保存时会解析程序真实目录，以支持 Windows 目录迁移和目录链接。

如果全部结果都隐藏了，没有可右键的条目，可用下面的[黑名单管理脚本](#黑名单)撤销最后一条或清空规则。

## 支持范围

- 仅支持 **Windows x64，Telegram Desktop 7.2.7** 的指定可执行文件；同版本号但哈希不同也会拒绝构建。
- 精确匹配作用于左上角全局搜索；内容黑名单也过滤聊天内消息搜索。
- 沿用 Telegram 的异步网络请求、取消、缓存与分页机制。补丁只过滤 Telegram 返回的候选，不能保证找到服务器未返回的内容，也没有建立完整历史索引。
- 自动更新会替换 EXE。[外置管理器](docs/update-persistence.md)可随用户登录启动，从固定 GitHub 仓库获取适配，并在 Telegram 正常退出后恢复已支持版本；未知新版等待适配，不会降级。
- 生成的修改版 EXE 不再具有官方 Authenticode 签名。

适用原版 `Telegram.exe` 的 SHA-256：

```text
16a234e303ecbafde90e0f5ee27e13a40595453f33896fa340d9cb186df60397
```

r4 已验证补丁版 SHA-256：

```text
6c41e516fafdc94a17dd4aa42df504264941f3d2c90a173211ba956fe1985301
```

上游版本、源代码基线与下载入口见 [兼容性清单](compatibility.json) 和 [Telegram 官方 v7.2.7 发布页](https://github.com/telegramdesktop/tdesktop/releases/tag/v7.2.7)。以实际 EXE 哈希为准。不要为了本补丁覆盖正在使用的更高版本。

## 如何安装

### 普通用户：安装一次外置管理器

1. 打开 [v1.2.1 发布页](https://github.com/245582001g-oss/telegram-exact-search-patch/releases/tag/v1.2.1)，下载并解压 `telegram-exact-search-patch-v1.2.1-installer.zip`。
2. 双击 `Install.cmd`，在文件选择框中选择实际使用的 `Telegram.exe`。
3. 管理器安装到 `%LOCALAPPDATA%\TelegramExactSearchPatch`，并创建当前用户的登录启动项；不需要管理员权限、Python 或编译器。
4. 若 Telegram 正在运行，请从托盘正常退出。管理器将在退出后应用已适配补丁，之后正常启动 Telegram 即可。

安装器包含当前 7.2.7 的 **7,338 字节**差分包，能够离线重建经过验证的 r4。未来适配从本仓库的版本清单和 Release 下载，传输、原版、补丁包与生成结果都进行检查。管理器本身不自动下载执行新的脚本。

每分钟检查程序是否变化，通常每小时检查远程适配清单；退出后修复可能需等待一个检查周期。Telegram 更新器可能直接重启官方原版，因此更新后第一次运行期间可能暂时仍是原生搜索。**任意未来版本都永久兼容无法保证；新内部布局需要维护者先适配。**

查看状态、立即检查修复、通过管理器启动、停止及卸载的命令见 [管理器说明](docs/update-persistence.md)。7.2.5 用户请使用历史 v1.0.0 发布包。

### 开发者：从源码构建

以下是手动构建及安装流程，普通用户使用上面的安装器即可。

### 1. 下载并解压源码

打开[发布页](https://github.com/245582001g-oss/telegram-exact-search-patch/releases/tag/v1.2.1)，下载源码 ZIP 并解压。也可以在[仓库首页](https://github.com/245582001g-oss/telegram-exact-search-patch)选择 **Code → Download ZIP**，获取含最新说明的源码。

打开包含 `README.md`、`src`、`tools` 的目录。以下示例假定该目录是 `C:\TelegramSearchPatch`；你的目录可以不同，请替换为自己的实际路径。

### 2. 准备构建环境

| 需要的内容 | 说明 |
| --- | --- |
| Windows x64 | 本补丁目前只适配此平台 |
| [Python](https://www.python.org/downloads/windows/) | 3.10 或以上；本次验证使用 3.12.10 |
| [WinLibs MinGW-w64 GCC](https://winlibs.com/) | Windows x64 编译器；已验证 GCC 16.1.0 / UCRT / POSIX / SEH r2，详细版本见[验证说明](docs/verification.md) |
| 官方 `Telegram.exe` | 必须符合前面的版本及 SHA-256；不是安装包 `tsetup` 的哈希 |

编译器版本会影响生成文件，安装工具只接受已验证的 r4 产物哈希。若换编译器后哈希不同，需要另行核验构建，不能改掉安装器的哈希检查来直接安装。

打开 PowerShell，进入源码目录，安装 Python 依赖：

```powershell
Set-Location 'C:\TelegramSearchPatch'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

若系统找不到 `python`，先确认 Python 已安装并加入 PATH，也可将命令里的 `python` 换成实际 Python 可执行文件的完整路径。上述命令直接使用虚拟环境中的 Python，无须额外激活虚拟环境。

### 3. 核对你要使用的 Telegram

通过 Telegram 快捷方式的“打开文件所在位置”，找到真正的 `Telegram.exe`，不要把快捷方式 `.lnk` 传给脚本。如果程序目录做过迁移或链接，请使用真实安装目录。

以下示例使用 `C:\TelegramPortable\Telegram.exe`：

```powershell
Get-FileHash -LiteralPath 'C:\TelegramPortable\Telegram.exe' -Algorithm SHA256
```

结果必须是：

```text
16a234e303ecbafde90e0f5ee27e13a40595453f33896fa340d9cb186df60397
```

字母大小写不影响哈希比较。哈希不同就不属于这次支持的原版文件，即使界面显示 7.2.7 也不能套用。Telegram 已升级时，不要用旧版补丁或旧版备份覆盖新版。

### 4. 构建补丁版文件

在源码目录运行，将原版和 GCC 路径替换成实际路径：

```powershell
.\.venv\Scripts\python.exe src\build_patch.py --input 'C:\TelegramPortable\Telegram.exe' --gcc 'C:\mingw64\bin\gcc.exe' --output-dir build
```

成功后会生成：

- `build\Telegram.exact.exe`：待安装的补丁版程序。
- `build\build-report.json`：构建与校验报告。

构建器只读取原版输入，不会替换正在使用的 Telegram，也不会启动客户端。这条路线不需要申请或填写 `api_id`、`api_hash`。

可先检查生成文件：

```powershell
Get-FileHash -LiteralPath 'build\Telegram.exact.exe' -Algorithm SHA256
```

已验证 r4 的结果为 `6c41e516fafdc94a17dd4aa42df504264941f3d2c90a173211ba956fe1985301`。构建失败或哈希不符时，先解决构建问题，再进入安装步骤。

### 5. 退出 Telegram 并安装

在任务栏托盘中退出 Telegram；只关聊天窗口可能仍在后台运行。多开时先退出所有 Telegram 实例。安装脚本会检查进程，但不会代替你强制关闭程序。

仍在源码目录运行：

```powershell
$patchedExe = (Resolve-Path 'build\Telegram.exact.exe').Path
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Install-Patch.ps1 -TelegramExe 'C:\TelegramPortable\Telegram.exe' -PatchedExe $patchedExe
```

看到 `Installed and SHA256 verified` 表示安装与哈希校验成功。脚本在原程序旁保存 **`Telegram.exe.before-chinese-search.7.2.7.bak`**，再原子替换程序；已有备份只校验，不覆盖。请保留备份、完整 `tools` 目录及其上一级的 `compatibility.json`，以便卸载补丁。不同 Telegram 版本分别备份，旧版备份不覆盖。

遇到进程仍运行、原版或产物哈希不同、备份异常、目录不可写等情况，脚本会报错。按错误原因处理，不要绕过版本检查。

### 6. 自行启动并体验

用原来的快捷方式启动 Telegram，在左上角全局搜索试试 `美丽`、`Python 教程` 或你知道已经存在的消息片段，再体验消息结果右键菜单。

没有结果时，先用确定存在的单个词测试，注意大小写与服务端返回范围；不能只凭一个搜索词没结果就判断补丁未安装。需要核对时，再对安装目录的 `Telegram.exe` 运行 `Get-FileHash`，应为上面的 r4 哈希。

安装脚本不修改 `tdata`，不启用后台维护，也不会自动启动程序。

### 7. 使用独立启动入口

将补丁源码和构建文件留在 Telegram 安装目录之外，以后可以运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Start-PatchedTelegram.ps1 -TelegramExe 'C:\TelegramPortable\Telegram.exe' -PatchedExe $patchedExe
```

此入口核对 EXE；已支持原版被覆盖后可重新应用补丁再启动。未知新版会保留原文件、停止启动并提示适配。它不会阻止 Telegram 更新，也不会自动安装后台服务。更新器直接重启会绕过它；完整研究结论、限制和使用说明见[升级后保留补丁](docs/update-persistence.md)。

## 如何卸载或恢复原版

如果安装了 v1.2.1 自动恢复管理器，请**先停止或卸载管理器，再恢复原版**，否则它会在下一次检查时重新应用补丁。卸载命令见[管理器说明](docs/update-persistence.md#停止或卸载)。卸载管理器会移除自己的登录启动项，保留当前 Telegram 程序；恢复官方程序是下面的独立步骤。

**卸载本补丁，就是把经过校验的官方原版 `Telegram.exe` 恢复回去；不需要卸载 Telegram。** 只删除下载的源码文件夹不会取消已经安装到程序中的补丁。

### 1. 完全退出 Telegram

从托盘退出所有 Telegram 实例，然后进入保留的源码目录。确保完整 `tools` 目录及其上一级的 `compatibility.json` 都在，目标程序旁还保留 `Telegram.exe.before-chinese-search.7.2.7.bak`。

### 2. 运行恢复脚本

```powershell
Set-Location 'C:\TelegramSearchPatch'
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Restore-Patch.ps1 -TelegramExe 'C:\TelegramPortable\Telegram.exe'
```

看到 `Original restored and SHA256 verified` 表示恢复成功。脚本会先核对当前程序为已知 r4 补丁版、备份为支持的官方原版，再恢复；聊天数据和黑名单规则不参与替换。

### 3. 核对并启动

```powershell
Get-FileHash -LiteralPath 'C:\TelegramPortable\Telegram.exe' -Algorithm SHA256
```

恢复后的哈希应为 `16a234e303ecbafde90e0f5ee27e13a40595453f33896fa340d9cb186df60397`。之后自行启动 Telegram，即恢复原版搜索行为。

### 4. 按需清理补丁文件

恢复成功后，原版 Telegram 不会加载本补丁的黑名单。想保留以后重新使用的规则，可以保留文件；想移除规则，可以在 Telegram 及管理脚本均退出时，删除程序旁的 `exact-search-blacklist.v1.bin` 及其 `.lock` 文件。

不再需要构建和恢复工具时，可删除本补丁的源码/构建目录。确认官方原版已恢复后，也可按需移除 `Telegram.exe.before-chinese-search.7.2.7.bak` 和空的 `Telegram.exe.chinese-search.lock`。恢复备份名自 v1.1.0 起包含 Telegram 版本号，旧版备份保持原样。

**`tdata` 是 Telegram 的账号与本地数据目录，不属于补丁清理项，不要在卸载补丁时删除。**

### 备份丢失、已经更新或恢复报错

- **缺少或损坏原版备份**：恢复脚本会拒绝操作。需要从 [Telegram 官方下载页](https://desktop.telegram.org/)取得适合自己的官方客户端，按实际安装方式恢复官方程序，并保留原有数据。
- **Telegram 已自动更新**：当前 EXE 的版本与哈希可能已经不同。不要强行恢复不同版本的备份；新版程序是否还有补丁，应以其实际文件哈希和适配情况判断。
- **只丢失了源码/工具目录**：请下载与已安装补丁匹配的发布版本，保留完整 `tools` 目录和 `compatibility.json` 后重试恢复。原版备份仍须存在于 Telegram 程序旁。
- **文件被占用或没有写权限**：先退出 Telegram 和正在运行的补丁管理脚本，确认目录及权限后再试。

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

## 常见问题

| 问题 | 说明 |
| --- | --- |
| 只能搜简体中文吗？ | 不是。英文及其他语言也可按原文匹配，多种语言可以在同一查询里组合。 |
| 搜两个词，是满足任意一个就行吗？ | 全局消息搜索要求两个都出现在同一条消息中；三个及更多词也是同样规则。 |
| 为什么 `cat` 还能搜到 `cats`？ | 本地规则是连续子串，不是英文整词边界。`cats` 包含 `cat`。 |
| 想搜连续的英文短语怎么办？ | 当前消息搜索按空白拆词，不提供用引号锁定含空格短语的功能。群名、联系人等名称则使用整个输入连续匹配。 |
| 没结果，是不是一定不存在？ | 不是。服务端可能没有返回，也可能大小写、繁简体、标点或字符序列不同，或内容已被屏蔽。 |
| 可以用 `OR`、减号排除词或星号吗？ | 补丁不会将它们作为特殊运算符；它们会参与字面匹配。 |
| 会自动删除广告或拉黑发广告的人吗？ | 不会。主动屏蔽后只隐藏原文相同的搜索结果，不删除消息，也不拉黑账号。 |
| 所有重复内容会自动去重吗？ | 不会。只有已手动加入内容黑名单的原文会被隐藏。 |
| 手机、Mac、Linux 可以安装吗？ | 当前发布仅适配兼容性清单中的 Windows x64 7.2.7，不适用于其他平台。 |
| Telegram 更新后补丁还在吗？ | 更新可能替换 EXE，需要按新版重新核验和适配；本项目不保证跨版本自动生效。 |
| 需要把账号密码或验证码交给补丁吗？ | 不需要。构建和安装工具不需要登录账号，也不需要 API 凭据。 |
| 删除源码 ZIP 或源码目录就算卸载吗？ | 不算。已安装的修改在 Telegram.exe 中，须先按上面的步骤恢复官方原版。 |

## 测试

建议在安装前运行以下回归测试，此时 `--original` 指向未修改的官方原版：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tests\test_menu_payload.py --build-dir build --original 'C:\TelegramPortable\Telegram.exe'
```

如果已经安装补丁，目标 `Telegram.exe` 已不是原版，测试参数应改为安装器保留的备份：

```powershell
.\.venv\Scripts\python.exe tests\test_menu_payload.py --build-dir build --original 'C:\TelegramPortable\Telegram.exe.before-chinese-search.7.2.7.bak'
```

回归测试在 Unicorn 模拟器中执行编译后的补丁，使用合成 Qt/WinAPI 对象及内存文件系统，不访问真实账号或聊天数据。它不等同于完整 Telegram UI 测试。详细覆盖与限制见 [验证说明](docs/verification.md)。

多语言回归已纳入仓库：`tests/test_language_examples.py --build-dir build`。另运行 `powershell -NoProfile -ExecutionPolicy Bypass -File tests\test_install_tools.ps1` 检查安装、版本备份、恢复和外置启动器。测试使用隔离的合成文件，不修改真实 Telegram。

`tests/test_build_rejection.py` 检查兼容性清单与构建器一致，并确认未知输入在编译或写入输出之前被拒绝。7.2.7 已安装并启动，用户实测确认全局搜索 `好人` 只返回连续包含 `好人` 的结果；右键屏蔽、撤销和再次重启后的规则读取尚未在本版逐项实测。完整范围见[验证记录](docs/verification.md)。

## 许可证

本项目原创补丁代码、脚本和文档采用 [MIT License](LICENSE)。Telegram Desktop 本体采用 [GPL-3.0 及上游附加条款](https://github.com/telegramdesktop/tdesktop/tree/v7.2.7)，本项目的 MIT 许可不改变 Telegram 及其依赖的许可。组合后的客户端不能作为纯 MIT 软件分发，详见 [NOTICE](NOTICE.md)。
