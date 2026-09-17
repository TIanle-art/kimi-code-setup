# computer-use（kimi-cu）：装法、权限与注意事项

> 主流程第 3 步的细则。**用途**：操作本机真实浏览器 / App 界面的工具——截图读界面、点击、输入、滚动……
> 约定：**macOS / Windows 默认装，Linux 不装**；**一律走 kimi 官方下载**；**插件装法先问用户**（① 官方 `/plugins install`、② agent 代装，见下节）；**别再手写 `mcp.json` 条目**（并存＝两个实例抢键鼠）。

## 平台对照（一律走官方下载）

kimi-code 自己内置了这个能力（`kimiCu.ts`：先 `detect` 再 `install`），安装器从官方 CDN 取包、装插件。**注意版本差异：0.43.1 实测它会移除旧的 `mcp.json` 手写注册，2.0.0 实测相反——安装器自己会写一条**（见「别再手写…」一节）：

| 平台 | 官方下载（`https://cdn.kimi.com/…`） | 插件 id | 装好后的工具名 |
|------|--------------------------------------|---------|----------------|
| macOS | `kimi-computer-use/latest/KimiCU.app.zip`（App，用 `ditto` 解压）+ `kimi-computer-use/latest/kimi-cu-plugin.zip`（插件），装完跑 `request-permissions --ax --screen` | `kimi-cu` | `mcp__plugin-kimi-cu_<server>__*` |
| Windows | `kimi-computer-use-windows/latest/setup_windows.ps1`（校验 SHA-256 + Authenticode，把 runtime 装到 `%LOCALAPPDATA%\KimiCU\`）+ `kimi-computer-use-windows/latest/kimi-cu-win-plugin.zip`（插件） | `kimi-cu-win` | `mcp__plugin-kimi-cu-win_win__*` |
| Linux | **不装**（2026-09-16 与用户确认的约定）——官方只发 macOS / Windows 两套包，Linux 上直接跳过、别去折腾。查证：官方文档只列这两个平台；CLI 的 `kimiCu.ts` 里只有 `createMacKimiCuEntry` / `createWindowsKimiCuEntry`；官方插件市场 `plugins/marketplace.json` 里没有 kimi-cu 条目。**别硬装 macOS 包**：`KimiCU.app.zip` 是带 AppleScript 的 Mach-O App，Linux 上跑不起来 | — | — |

## 装法：先问用户（两条路，Windows 侧都实测过）

**插件的装法有两条路，开工时先问用户走哪条**（用 AskUserQuestion）；**runtime 不用问**——两条路都用同一份官方脚本（`setup_windows.ps1`，校验 SHA-256 + Authenticode → `%LOCALAPPDATA%\KimiCU\`），agent 直接代跑。

问题模板（一次一个题、两个选项）：「computer-use 的插件装法：① 官方路径——你在 TUI 里跑一条 `/plugins install <zip-url>`（推荐）；② 全自动——agent 下载 zip、原样解压并登记，你一条命令都不用敲。选哪个？」

| | ① 用户手动·官方插件（推荐） | ② agent 代装·手装插件 |
|---|---|---|
| 怎么装 | TUI 里 `/plugins install <上表 plugin.zip 的完整 URL>`（`/plugins` 是**交互式斜杠命令，`kimi -p` 里不会执行**） | agent：下载同一份官方 zip → **原样解压**到 `~/.kimi-code/plugins/managed/kimi-cu-win/`（zip 是平铺结构、无外层目录）→ 照下面结构写 `~/.kimi-code/plugins/installed.json` |
| 实测 | 0.43.1（2026-09-16）与 2.0.0（2026-09-18）都实测通过 | **2026-09-18 沙箱实测通过**（隔离 `KIMI_CODE_HOME`：手装后新会话拿到全部 13 个 `mcp__plugin-kimi-cu-win_win__*` 工具） |
| 官方性 | 官方安装器负责下载/登记 | 绕过安装器、手写登记（结构简单、实测能加载）；**将来的 `/plugins` 更新/卸载对它是否顺畅未实测** |
| `mcp.json` 副作用 | **2.0.0 实测：安装器会多写一条 kimi-cu 手写条目**（与插件自带声明重复 → `verify.py` 报 FAIL），装完要删（见下节） | 不写 `mcp.json`，天然干净 |
| 用户要敲的命令 | `/plugins install …` 一条（+ `/reload` 或新开会话） | 零条；下次新开 kimi 会话自动生效 |
| 适合 | 想走官方登记、用户能切到 TUI | 非交互 / 无人值守（`kimi -p`）、或用户不想动手 |

两条路的共同点：插件自带 MCP 声明（**都不需要手写 `mcp.json`**）；runtime 都从官方 CDN 装；生效都要**新开会话**（或 `/reload`）。

路 ② 的具体做法（Windows；macOS 未实测，路径与字段以实际安装结果为准）：

```bash
# 1) runtime——与路 ① 相同（官方脚本）：
#    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod 'https://cdn.kimi.com/kimi-computer-use-windows/latest/setup_windows.ps1' | Invoke-Expression"
# 2) 插件 zip 原样解压（平铺结构）：
curl -fsSL -o /tmp/kimi-cu-win-plugin.zip https://cdn.kimi.com/kimi-computer-use-windows/latest/kimi-cu-win-plugin.zip
python - <<'PY'
import zipfile, pathlib
dest = pathlib.Path.home()/".kimi-code/plugins/managed/kimi-cu-win"
zipfile.ZipFile(r"C:/Users/<你>/AppData/Local/Temp/kimi-cu-win-plugin.zip").extractall(dest)
PY
# 3) 手写登记 ~/.kimi-code/plugins/installed.json（已有别的插件就追加一条，结构照抄）：
```

```json
{
  "version": 1,
  "plugins": [
    {
      "id": "kimi-cu-win",
      "root": "C:\\Users\\<你>\\.kimi-code\\plugins\\managed\\kimi-cu-win",
      "source": "zip-url",
      "enabled": true,
      "installedAt": "2026-09-18T00:00:00.000Z",
      "updatedAt": "2026-09-18T00:00:00.000Z",
      "originalSource": "https://cdn.kimi.com/kimi-computer-use-windows/latest/kimi-cu-win-plugin.zip"
    }
  ]
}
```

## 别再手写 `mcp.json`（与官方插件互斥；2.0.0 的安装器自己会写一条）

- 官方插件自带 MCP 声明（Windows 是 `cmd /c bin\kimi-cu-mcp.cmd` → `%LOCALAPPDATA%\KimiCU\kimi-cu.exe mcp`，cwd 是插件根）。
- 手写条目与插件**并存会各拉一个实例抢键鼠**——`verify.py` 的 MCP 检查专门拦这一条（实测报 FAIL）。
- **2.0.0 实测：官方安装器自己会写一条**（指向 `%LOCALAPPDATA%\KimiCU\kimi-cu.exe mcp`，mtime 与 `plugins/installed.json` 的 `installedAt` 同刻；插件自带的 `INSTALL.md` 里并没有这一步——是安装器行为；与 0.43.1 时"会移除手写条目"相反）。装完把它删掉，保持"只有插件一份声明"。
- **删掉它不影响功能（2026-09-18 沙箱实测）**：隔离 `KIMI_CODE_HOME`、`mcp.json` 只留 exa——新会话照样拿到 13 个 `mcp__plugin-kimi-cu-win_win__*` 工具、没有第二个 `mcp__kimi-cu__*` 命名空间。
- 切换顺序：**先装插件 → 再删手写条目 → `/reload` 或新开会话**。

## 权限与平台注意事项

- **别给 computer-use 加 allow 规则**（`[[permission.rules]]` 里保持按默认询问）——它会真的操纵键鼠（`SKILL.md` 红线一节）。
- **macOS 权限**：首次调用若报权限错误，按安装器提示、或去「系统设置 → 隐私与安全性」给 KimiCU 打开辅助功能 / 屏幕录制。
- **Windows 注意**：需要 PowerShell 5.1 或 7；会短暂接管真实鼠标键盘（不如 macOS 能稳定后台注入）；目标程序以管理员运行时 KimiCU 也要同级权限；安全软件可能拦"输入注入"，需要放行。另外**桌面端设置里的「Computer Use」是 macOS 专属**（`process.platform !== "darwin"` 直接返回 unsupported），Windows 上找不到它是正常的。
- **Linux 上不装 kimi-cu（2026-09-16 与用户确认的约定；官方也没有 Linux 包，别白费劲）**：`verify.py` 在 Linux 上把 kimi-cu 两项降级成 INFO，不再算告警。真要"驱动浏览器"另有官方 **Kimi WebBridge** 插件（`/plugins` → Official，跨平台），但那属于额外需求、**默认不装**；需要点界面的活儿改走 API / CLI。
