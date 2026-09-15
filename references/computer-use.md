# computer-use（kimi-cu）：装法、权限与注意事项

> 主流程第 3 步的细则。**用途**：操作本机真实浏览器 / App 界面的工具——截图读界面、点击、输入、滚动……
> 约定：**macOS / Windows 默认装，Linux 不装**；**一律走 kimi 官方下载**；**别再手写 `mcp.json` 条目**（并存＝两个实例抢键鼠）。

## 平台对照（一律走官方下载）

kimi-code 自己内置了这个能力（`kimiCu.ts`：先 `detect` 再 `install`），安装器从官方 CDN 取包、装插件，**并且会自动移除旧的 `mcp.json` 手写注册**：

| 平台 | 官方下载（`https://cdn.kimi.com/…`） | 插件 id | 装好后的工具名 |
|------|--------------------------------------|---------|----------------|
| macOS | `kimi-computer-use/latest/KimiCU.app.zip`（App，用 `ditto` 解压）+ `kimi-computer-use/latest/kimi-cu-plugin.zip`（插件），装完跑 `request-permissions --ax --screen` | `kimi-cu` | `mcp__plugin-kimi-cu_<server>__*` |
| Windows | `kimi-computer-use-windows/latest/setup_windows.ps1`（校验 SHA-256 + Authenticode，把 runtime 装到 `%LOCALAPPDATA%\KimiCU\`）+ `kimi-computer-use-windows/latest/kimi-cu-win-plugin.zip`（插件） | `kimi-cu-win` | `mcp__plugin-kimi-cu-win_win__*` |
| Linux | **不装**（2026-09-16 与用户确认的约定）——官方只发 macOS / Windows 两套包，Linux 上直接跳过、别去折腾。查证：官方文档只列这两个平台；CLI 的 `kimiCu.ts` 里只有 `createMacKimiCuEntry` / `createWindowsKimiCuEntry`；官方插件市场 `plugins/marketplace.json` 里没有 kimi-cu 条目。**别硬装 macOS 包**：`KimiCU.app.zip` 是带 AppleScript 的 Mach-O App，Linux 上跑不起来 | — | — |

## 手动装（两条路等价，Windows 侧实测过）

- TUI 里 `/plugins install <上表 plugin.zip 的完整 URL>`（`/plugins` 是**交互式斜杠命令，`kimi -p` 里不会执行**）。
- Windows 的 runtime 也可以直接跑官方脚本：`powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod 'https://cdn.kimi.com/kimi-computer-use-windows/latest/setup_windows.ps1' | Invoke-Expression"`。
- 装完 `/reload` 或新开会话生效。

## 别再手写 `mcp.json` 条目（与官方插件互斥）

- 官方插件自带 MCP 声明（Windows 是 `cmd /c bin\kimi-cu-mcp.cmd` → `%LOCALAPPDATA%\KimiCU\kimi-cu.exe mcp`，cwd 是插件根）。
- 手写条目与插件**并存会各拉一个实例抢键鼠**——`verify.py` 的 MCP 检查专门拦这一条（实测报 FAIL）。
- 切换顺序：**先装插件 → 再删手写条目 → `/reload` 或新开会话**。

## 权限与平台注意事项

- **别给 computer-use 加 allow 规则**（`[[permission.rules]]` 里保持按默认询问）——它会真的操纵键鼠（`SKILL.md` 红线一节）。
- **macOS 权限**：首次调用若报权限错误，按安装器提示、或去「系统设置 → 隐私与安全性」给 KimiCU 打开辅助功能 / 屏幕录制。
- **Windows 注意**：需要 PowerShell 5.1 或 7；会短暂接管真实鼠标键盘（不如 macOS 能稳定后台注入）；目标程序以管理员运行时 KimiCU 也要同级权限；安全软件可能拦"输入注入"，需要放行。另外**桌面端设置里的「Computer Use」是 macOS 专属**（`process.platform !== "darwin"` 直接返回 unsupported），Windows 上找不到它是正常的。
- **Linux 上不装 kimi-cu（2026-09-16 与用户确认的约定；官方也没有 Linux 包，别白费劲）**：`verify.py` 在 Linux 上把 kimi-cu 两项降级成 INFO，不再算告警。真要"驱动浏览器"另有官方 **Kimi WebBridge** 插件（`/plugins` → Official，跨平台），但那属于额外需求、**默认不装**；需要点界面的活儿改走 API / CLI。
