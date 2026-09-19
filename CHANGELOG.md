# v1.4.0 — Telegram 7.2.8 r6

## v1.4.2 / r8 — 2026-09-19

- 针对 Telegram 无主右键菜单定位同一界面线程的稳定主窗口，使关键词/多选弹窗保持正确的父窗口及模态关系。
- 重复点击时恢复已有弹窗并保留勾选与未保存的文字，不再因“已打开”而静默忽略；关闭后可在同一进程再次打开。
- 补充无主菜单销毁、父窗口禁用/恢复、重复打开保留编辑/选择，以及取消后同进程重新打开的真实 Win32 回归。


## v1.4.1 / r7 — 2026-09-19

- 修复关键词对话框被正在销毁的右键菜单连带关闭：使用稳定根所有者，并拒绝无主工具窗作为父窗口。
- 搜索结果右键增加“进入多选屏蔽…”：独立复选框列表按频道 ID 合并重复结果，支持右键连续选取/取消、边缘自动滚动、全选与取消全选。
- 批量频道规则在同一文件锁内合并并原子保存；任何失败都不留下部分已写入的选择。批量屏蔽后仍可编辑额外关键词。
- 增加原生关闭父菜单复现回归、真实列表勾选/拖动/边缘滚动测试，以及双加载地址的批量与快照回归。


- 屏蔽整个频道后，提供可跳过、可编辑的关键词建议。
- 新增跨广播频道的正文包含规则，以及频道名称包含规则。建议片段只在用户保存后生效。
- 新增关键词管理窗口及独立 Manage-Keywords.cmd 入口，支持删除误加规则。
- 规则保存在 Windows 我的文档/Telegram/blacklists，独立格式校验、文件锁和原子保存；私有规则不进入发布包。
- 用线性匹配处理高度重复文字，避免长重复前缀造成多次回溯；不额外批量请求服务器搜索页。
- 对弹窗期间的搜索页面销毁增加 QObject 生命周期保护。

# v1.3.0 — telegram 重庆好人版 7.2.8 + 精确搜索

- Adapt exact search and existing content blocking to official Telegram 7.2.8 x64.
- Add broadcast-channel blocking by stable typed PeerId, independent of message text/name/username; separate undo and persistent channel rules.
- Filter channel messages before original-text extraction and hashing; filter global peer/name candidates too.
- Create Known Documents/Telegram/blacklists on first launch, migrate validated legacy rules only when destination is absent, preserve existing/corrupt data and fail softly when storage is unavailable.
- Fresh-profile auto-update default off; native settings toggle and saved preference parser retained.
- Publish a clean full portable client, upstream full source, patch source and data-only difference bundle.
- Include rule management helper in external runtime; SHA-256 no longer depends on PowerShell module autoloading.

# Changelog

## v1.2.1 — 2026-09-08

- 修复 Windows PowerShell 5.1 在省略 `-Root` 时，手动管理入口解析默认目录失败的问题。
- 加入真实子进程执行入口的回归；现有显式路径的登录监控、差分包及 r4 搜索程序不变。

## v1.2.0 — 2026-09-08

- 增加外置补丁管理器与一键安装入口，无须 Python 或编译器；可注册当前用户登录后自动检测。
- 从固定 GitHub 仓库获取数据清单和按完整哈希绑定的小补丁。7.2.7 的补丁包为 7,338 字节，使用本机原版重建已验证的 r4 文件。
- 官方更新覆盖 EXE 后，已适配版本在 Telegram 正常退出后自动修复；未知版本等待适配，保留现有客户端。
- 增加差分包、离线缓存、升级修复、进程竞争、启动与卸载的回归检查。
- 本机已安装并启动 r4，用户确认全局搜索 `好人` 只返回含连续 `好人` 的结果；新增这一反馈对应的正反例回归。

搜索程序与 v1.1.0 的 r4 哈希完全相同。本版改进交付与恢复方式，不需要再次覆盖已正确运行的 r4。

## v1.1.0 — 2026-09-08

- 适配 Telegram Desktop 7.2.7 Windows x64 的指定官方 EXE，修复升级覆盖后精确搜索和内容屏蔽失效。
- 逐项迁移搜索/Qt 调用地址和 Windows IAT；修正 UI 文本对象增大引起的 Entry、History、InnerWidget 字段偏移。
- 增加独立启动器：启动前校验，已验证原版可重新应用补丁，未知新版保持原样并提示适配。
- 安装/恢复从兼容性清单读取严格哈希，备份名包含 Telegram 版本，避免误用旧版本备份。
- 将 73 个多语言测试纳入仓库，更新菜单/黑名单合成对象，增加安装、恢复和启动器回归。
- 补充更新持久化研究与边界；保留官方升级，不声明任意未来版本自动兼容。

本版支持指定 7.2.7 文件，7.2.5 仍使用历史 v1.0.0 发布包。黑名单格式不变。

## 使用说明更新 — 2026-09-07

- 项目统一命名为 **Telegram 精确搜索 Patch | Telegram Exact Search Patch**，仓库名改为 `telegram-exact-search-patch`。
- 补充多语言与混合语言支持说明、搜索组合速查及大量正反例。
- 讲明大小写、英文子串、空白 AND、名称匹配和不支持的运算符规则。
- 扩展源码构建、安装、卸载恢复、规则清理及常见问题。
- 文档更新不改变 v1.0.0（r3）的补丁程序和兼容文件哈希。

## v1.0.0 — 2026-09-07

首次公开源码发布，功能基于已经完成本地验证的 r3。

- 中文连续字面匹配与消息多关键词 AND 筛选。
- 搜索结果右键屏蔽相同内容、撤销最近一次屏蔽。
- 程序旁持久化长度及 SHA-256 规则，修复迁移目录保存。
- 300 ms 搜索防抖、长度快速排除及大规则集辅助索引。
- 可移植构建参数、合成对象回归测试、安装与恢复脚本。
- MIT 原创贡献许可及上游许可证边界说明。

支持范围固定为兼容性清单中指定的 Telegram Desktop 7.2.5 Windows x64 文件。
