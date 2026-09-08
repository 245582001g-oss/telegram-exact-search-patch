# 升级后保留补丁：可实现范围与使用方式

## 结论

把补丁工具、构建产物和启动入口放在 **Telegram 安装目录外**，可以避免这些文件被 Telegram 更新器覆盖；启动前核对程序哈希，对已适配的原版自动重新应用补丁，可以恢复被覆盖的功能。

这不等于任意未来版本都兼容。**补丁文件能保留，针对客户端内部结构的适配仍需要随版本维护。** 当前启动器只接受 `compatibility.json` 中的精确原版和补丁版哈希。未知新版保持原样并报告需要适配，不会用旧版客户端替换它。

## 为什么不只做一个永久 DLL

本项目修改的是 Telegram 原生搜索和 Qt 菜单的内部调用，没有稳定的、专用于该功能的扩展接口。即使把执行代码搬进外置 DLL，也仍需定位调用点、原生函数、导入表和对象字段。

7.2.5 → 7.2.7 就是实际反例：底层 `Ui::Text::String` [新增 `_version` 字段](https://github.com/desktop-app/lib_ui/blob/b9290ba091c254bdb5421f6e3da8bb24cadf5b5f/ui/text/text.h#L544-L552)，使嵌入它的对象发生布局变化。搜索条目的标志、History 的 peer 指针、右键菜单关联消息、加载状态和菜单指针都需要重新核对。只扫描函数特征码、平移地址或保留 DLL 文件，无法证明读写的是正确字段。具体地址与字段核对记录见 [7.2.7 ABI 清单](abi-7.2.7.json)。

此外，Telegram 共享库初始化会[限制动态库搜索目录到 System32](https://github.com/desktop-app/lib_base/blob/de35c7abcbf6464a0845695a55568bdac12a5fba/base/platform/win/base_windows_safe_library.cpp#L129-L136)，旧系统备用流程还会检查相邻 DLL。这不足以证明所有 DLL 加载方式都不可行，但不能把“放一个代理 DLL 到程序旁”当作稳定的官方扩展入口。

| 方式 | 升级后的效果 | 本项目处理 |
| --- | --- | --- |
| 直接修改 Telegram.exe | 更新替换 EXE 后，修改消失 | 当前底层补丁方式，配合外置启动器 |
| 外置启动器 + 已验证适配 | 工具保留；支持的原版被覆盖后可在下次启动前修复 | 已提供 |
| 常驻检测器 | 可发现更新，但运行中的 EXE 不能安全替换；未知版本仍需适配 | 本版不注册后台任务 |
| 代理 DLL / 内存注入 | 文件可能保留，但内部 ABI 变化仍会破坏功能 | 不作为跨版本保证 |
| 维护完整分支及自己的更新渠道 | 可在每次发布时合入源代码修改和上游修复 | 长期替代方案，需持续构建、测试和发布完整客户端 |
| 把 EXE 设为只读或阻止更新 | 会阻断官方升级，也无法获得新版修复 | 不采用 |

## 外置启动器

将完整补丁源码与自己的构建结果放在独立目录，例如 `C:\TelegramSearchPatch`。不要放入 Telegram 的安装目录。保留 `compatibility.json`、`tools` 和构建的 `Telegram.exact.exe`。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\TelegramSearchPatch\tools\Start-PatchedTelegram.ps1' -TelegramExe 'C:\TelegramPortable\Telegram.exe' -PatchedExe 'C:\TelegramSearchPatch\build\Telegram.exact.exe'
```

可把这条启动命令保存为自己的快捷方式，以后通过它启动。启动器会：

1. 核对当前 Telegram 的完整 SHA-256；需要安装时，再验证补丁产物的完整 SHA-256。
2. 如果已是本版补丁，直接启动；如果是支持的官方原版，调用安装器备份并原子替换，再启动。
3. 如果要修复但 Telegram 或更新器仍在运行，要求先正常退出，避免文件替换竞争。
4. 如果是未知新版，报告需要更新适配包，保留现有程序且不启动它；仍可通过 Telegram 自身的快捷方式使用原版。

为覆盖目录链接导致的进程路径别名，安装/恢复会拒绝在任何 `Updater.exe` 运行时继续，要求其结束后重试；其他软件的同名更新器也会暂时阻止操作，脚本不会结束这些进程。

`-NoLaunch` 可用于只验证/修复、不启动客户端。脚本不会修改 Telegram 的自动更新设置、登录项、协议关联或账号数据，也不会从网络下载并执行新代码。

**通过旧快捷方式启动，或者 Telegram 更新器直接重启程序，会绕过这个入口。** 因此本版保证的是“经此外置入口启动时检查并恢复已支持版本”，不是“升级完成的一瞬间在运行中恢复任意新版”。安装器保存的原版备份带 Telegram 版本号，不会把 7.2.5 备份当作 7.2.7 原版使用。

## 遇到未来新版

从项目发布页获取明确支持该版本的新适配包，核对兼容性清单，构建并运行对应回归后，把外置入口指向新包。原来的 `exact-search-blacklist.v1.bin` 格式保持不变，无须重新添加规则。

补丁恢复工具属于本地工具，不依赖 Telegram 登录凭据。公开仓库与发布包只含源码和工具；不上传 Telegram 本体、聊天数据、黑名单或本机路径清单。

## 上游依据

- [Telegram v7.2.7 Windows 更新器源码](https://github.com/telegramdesktop/tdesktop/blob/v7.2.7/Telegram/SourceFiles/_other/updater_win.cpp#L204-L255)：更新器覆盖客户端文件；重命名 EXE 也会被识别并更新。[更新器直接重启新 EXE](https://github.com/telegramdesktop/tdesktop/blob/v7.2.7/Telegram/SourceFiles/_other/updater_win.cpp#L486-L490)，因此外置入口在下次经该入口启动时才执行检查。
- [v7.2.5 与 v7.2.7 的源代码比较](https://github.com/telegramdesktop/tdesktop/compare/v7.2.5...v7.2.7)：应用源文件与 UI 子模块版本需要一起核对。
- [本版验证说明](verification.md)：记录实际支持文件和测试边界。
