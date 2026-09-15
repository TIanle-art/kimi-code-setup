---
name: kimi-code-setup
description: |
  新机器上把 kimi-code 从零配到可用（macOS / Windows / Linux）：provider 与模型、内置 WebSearch/FetchURL 接自己的 Exa（exa-bridge）、MCP、权限、AGENTS.md、Todo 守卫钩子、状态栏；也支持只读体检。触发：「调试/配置 kimi-code」「体检」、WebSearch 不能用、FetchURL 撞 WEB_PRIVATE_ADDRESS、exa-bridge 挂了、/login 顶掉配置。
metadata:
  version: "3.8.0"
---

# 全新 kimi-code 落地（新机器开箱配置）

**这个 skill 管的是"把一台新机器上刚下载的 kimi-code 配到能用"，不是修 bug**——排错只是收尾的一环。细则按主题放在 `references/`，本文件只留主流程、判据和索引；手上的脚本放在 `assets/`。

> **验证版本**：配置字段、权限模式文案、迁移行为、脚本契约实测于 **kimi-code 0.41.0（macOS，2026-09-15）**；Windows 分支的常驻方式、钩子/状态栏命令写法、kimi-cu 入口实测于 **Windows 11 + kimi-code 0.43.1（Store 版 Python 3.13，非管理员账户，2026-09-16）**；**Linux 分支的 systemd 常驻、桥三层验证、钩子实时拦截实测于 WSL2 + kimi-code 0.41.0（Python 3.14，2026-09-16）**。实测结论都带"✅/❌ 实测"标注。换了版本（或机器上版本不同）先跑一次 `assets/verify.py` 看结论是否还对得上。

## 这个目录放在哪、怎么用

- **怎么触发**：拷进目标机器的 `~/.kimi-code/skills/kimi-code-setup/` 后，直接说「**调试 kimi-code**」「配置 kimi-code」这类话即可——agent 按 description 命中后自动加载本文件，缺参数（Exa key、平台是 mac / win 还是 linux、要不要挂 MCP）它会先问清再动手，不用背固定提示词。
- **本机（作者机器）**：**正本在桌面** `~/Desktop/kimi-code-setup/`（改动只动这份；它同时是个 git 仓库，`origin` 指向公开仓库 https://github.com/TIanle-art/kimi-code-setup ，改完 `git push` 就更新公开版），**安装副本在** `~/.kimi-code/skills/kimi-code-setup/`（kimi 自动发现、直接能命中 `kimi-code-setup` skill 的那份）。改完正本跑一次同步（**必须带 `--exclude=.git`**，否则会把仓库元数据拷进 skill 目录），再体检确认：

  ```bash
  rsync -a --delete --exclude=.git ~/Desktop/kimi-code-setup/ ~/.kimi-code/skills/kimi-code-setup/
  python3 ~/Desktop/kimi-code-setup/assets/verify.py | tail -3
  ```

  Windows 上没有 rsync（Git Bash 一般也不带），等价做法是 `robocopy` 或 `cp -r`，同步完照样用 `diff -rq --exclude=.git 旧目录 新目录` 核对：

  ```powershell
  robocopy "$env:USERPROFILE\Desktop\kimi-code-setup" "$env:USERPROFILE\.kimi-code\skills\kimi-code-setup" /MIR /XD .git /NFL /NDL
  python "$env:USERPROFILE\Desktop\kimi-code-setup\assets\verify.py" | Select-Object -Last 3
  ```
- **要用在别的机器上**：把整个目录拷到目标机器的 `~/.kimi-code/skills/kimi-code-setup/`（Windows：`%USERPROFILE%\.kimi-code\skills\kimi-code-setup\`），那里新开的 kimi 会话就会自动发现它；不拷也行，直接把文件带过去让 agent 读。
- **本机想临时当 skill 用**：`kimi --skills-dir ~/Desktop --skills-dir ~/.kimi-code/skills`（实测：`--skills-dir` 会**替换**自动发现的目录，所以要补上原来的 `~/.kimi-code/skills` 才不丢 `kimi-webbridge` / `markitdown`；它按整棵子树递归扫描，指到桌面会把 `桌面/开源工具/` 下的 170+ 个 skill 一起带进来，很吵）。更省事的是让 agent 直接读本文件。
- 下文里的 **`$SKILL_DIR`** 指这个 skill 所在目录：本机有正本（`~/Desktop/kimi-code-setup`）与安装副本（`~/.kimi-code/skills/kimi-code-setup`）两份、内容一致，用哪份都行；拷到目标机器后是 `~/.kimi-code/skills/kimi-code-setup`（Windows 用 `%USERPROFILE%\.kimi-code\skills\kimi-code-setup`）。命令里出现 `$SKILL_DIR` 时按实际位置展开。

## assets 里有什么（手脚）

| 脚本 | 干什么 |
|------|--------|
| `assets/exa-bridge.py` | 内置 WebSearch / FetchURL 的适配器（转调 Exa），部署到 `~/.kimi-code/exa-bridge/`；本文件里的副本 = 机器上在跑的那份 |
| `assets/launchagent.plist.template` | macOS LaunchAgent 模板（占位符替换，别手写 XML） |
| `assets/systemd-user.service.template` | Linux systemd 用户单元模板（同一套占位符；**2026-09-16 在 WSL2 实测通过**）。生成时的 `sed` 前面必须先 `tr -d '\r'`——CRLF 模板会把 `\r` 带进令牌，桥直接 401（见 `references/web-tools-exa.md`） |
| `assets/windows-launch.pyw.template` | Windows 桥启动器模板（给 `pythonw.exe` 用）：替桥写进 `EXA_BRIDGE_TOKEN` / `EXA_API_KEY`，并把 stdout/stderr 重定向到 `bridge.log`——计划任务与启动文件夹都塞不进环境变量，`pythonw` 又没有控制台。部署到 `~/.kimi-code/exa-bridge/launch.pyw`，见 `references/web-tools-exa.md` 第 3 节（Windows） |
| `assets/todo-panel-guard.py` | Stop 钩子：Todo 面板里的任务全部 `done` 却没清空时，拦下回合结束并提示先清空；部署到 `~/.kimi-code/hooks/`，见第 6 步 |
| `assets/statusline.py` | footer 状态栏：常显整个会话的缓存命中率与 provider 余额；部署到 `~/.kimi-code/`，靠 `tui.toml` 的 `[status_line]` 挂上，见第 7 步 |
| `assets/kimi-web-status.user.js` | 浏览器用户脚本（Tampermonkey）：把 cache/bal 显示在 `kimi web` 页面角落，数据来自桥的 `/status`；见 `references/statusline.md`「web 端」 |
| `assets/patch-config.py` | **改 config.toml / tui.toml 只用它**：幂等（存在就改值、不存在才插入）、保留注释、写前备份、写前复验（不通过不落盘）；数组表用 `ensure-rule` / `ensure-hook` 按内容去重追加，`unset` / `remove-rule` / `remove-hook` 负责删除（回滚用）；`--raw` 写裸值，默认按字符串加引号。值里带 `\r` / `\n` 会**当场拒绝**（CRLF 坑的防线之一） |
| `assets/verify.py` | **一条命令体检**：出网 / 配置 / 桥 / MCP / 工具清单 / 钩子（含守卫脚本行为自测）/ 状态栏（含脚本行为自测）/ `kimi doctor` / 补丁脚本自测 / 脚本漂移 / 常驻定义令牌一致性，只读，返回 0/1/2 |

## 主流程

| # | 步骤 | 做完的判据 | 细则在哪 |
|---|------|-----------|----------|
| 0 | 装好 kimi-code + 摸清现状 + 备份 | `kimi --version` 有输出；知道配置目录、有没有配过 | 本文 |
| 1 | LLM provider、模型与思考强度 | 新进程里能正常对话、思考强度符合预期 | 本文 |
| 2 | 内置 WebSearch / FetchURL → 自己的 Exa | 三层验证全过；Windows 上自启项写完要回读确认（见细则第 3 节） | `references/web-tools-exa.md` |
| 3 | 外部工具通道（exa 走 mcp.json、computer-use 走官方下载） | 工具清单里出现 `mcp__exa__*` 与 computer-use 工具（官方插件 `mcp__plugin-kimi-cu-win_win__*` / macOS `mcp__plugin-kimi-cu_*`）；若还看到旧的 `mcp__kimi-cu__*`，说明手写条目没删——`verify.py` 会报 FAIL | 本文 |
| 4 | 权限模式（Ask When Needed）与工具开关 | 启动就是期望的模式、工具没被 disabled | 本文 |
| 5 | 策略文件 AGENTS.md | 模型知道何时用哪条通道；任务清单那三条约定也在里面 | 本文 |
| 6 | Todo 面板守卫（Stop 钩子 + 约定） | 攻击性用例被拦下（`verify.py` 钩子项 PASS + 一次 `kimi -p` 实测） | `references/todo-panel-guard.md` |
| 7 | 状态栏（缓存命中率 + API 余额） | `verify.py` 状态栏项全 PASS；`/reload-tui` 后 footer 第一行出现 `cache N%` | `references/statusline.md` |
| 8 | 总验收 | `verify.py` 全绿 + 一次真实端到端调用 | 本文 |

### 0. 装好 kimi-code + 摸清现状 + 备份

**还没装就先装**（官方一行命令，见 [Kimi Code CLI Docs](https://moonshotai.github.io/kimi-code/)）：

```bash
# macOS / Linux
curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash
# Windows（PowerShell）：irm https://code.kimi.com/kimi-code/install.ps1 | iex
# macOS 也可以走 Homebrew（作者机器就是这条路径装的）
brew install kimi-code
```

```bash
kimi --version
ls -la ~/.kimi-code            # Windows: dir %USERPROFILE%\.kimi-code
kimi provider list             # 已配的 provider 与默认模型
pgrep -fl exa-bridge           # 有没有既存的桥
```

配置目录 = `$KIMI_CODE_HOME`，未设则 `~/.kimi-code`（Windows `%USERPROFILE%\.kimi-code`）。里面：`config.toml`（主配置）、`mcp.json`（MCP 清单）、`AGENTS.md`（策略）、`skills/`、`sessions/`。

**动手前先备份**（`patch-config.py` 自己也会备份，但整体改前留一份更稳）：`cp ~/.kimi-code/config.toml ~/.kimi-code/config.toml.bak-$(date +%Y%m%d-%H%M%S)`（`mcp.json` 同理）。

**开工先问（交互会话里，一次问全）**——用户只说了一句「调试 kimi-code」时，别猜，按下面这张表把缺的补齐再动手：

| 必须问到的 | 为什么 |
|------------|--------|
| 目标平台：macOS、Windows 11 还是 Linux | 决定常驻方式（launchd / 计划任务 / systemd user unit）、以及 `~` 与 `%USERPROFILE%` 的写法 |
| **Exa API key：有还是没有** | 第 2 步的桥**必须**有 key 才建得起来；没有就走下面那张表的三条路，别硬上（已有 key 的机器上可直接搬：`mcp.json` 的 `mcpServers.exa.headers.x-api-key`） |
| LLM provider 的 API key | **仅当** `kimi provider list` 显示还没配 provider 时才问 |

| 不用问，按默认走 | 默认值 |
|------------------|--------|
| 桥的端口 | `8787`（被占用才换） |
| 本地访问令牌 | 现场生成，不劳用户 |
| 常驻方式 | mac 用 launchd、win 用计划任务、Linux 用 systemd user unit，默认就装 |
| MCP 通道 | 默认装 exa + kimi-cu（见第 3 步） |
| 权限模式 / 思考强度 | `yolo`（Ask When Needed）+ 模型级 `default_effort = "max"`，见第 1、4 步 |
| 状态栏（缓存率 + 余额） | 默认装（见第 7 步）；余额段只在 provider 有余额接口时出现 |

**用户说"我没有 Exa key"时，给他三条路挑**（别卡住，也别拿别人的 key 顶上）：

| 选项 | 具体怎么做 | 代价 |
|------|-----------|------|
| ① 现在去注册（推荐） | 让用户打开 dashboard.exa.ai 注册 → 复制 key 贴回来。**新账号送 $20（约 2,800 次搜索），之后 Free Tier 每月再送 $10** | 两条通道都能建（内置 + MCP），花的也是他自己的额度 |
| ② 先用匿名 MCP 顶着 | 只写 `mcp.json` 的 exa 条目、**不要 `headers`**：`{"url": "https://mcp.exa.ai/mcp"}`。实测（2026-09）：不带任何 key 也能 `web_search_exa` / `web_fetch_exa` | 只有 MCP 通道可用（额度与速率由 Exa 服务端限制，上限未测）；**内置 `WebSearch`/`FetchURL` 建不了**——桥调 `api.exa.ai` 必须要 key，这时它俩只能走 Kimi 托管（要 `/login`），说明白别让用户以为坏了 |
| ③ 干脆不要 Exa | 自建 SearXNG 后把 `[services.moonshot_search].base_url` 指过去；或退回"用 Bash curl 抓指定页面" | 没有搜索能力，只有抓取 |

- 选了 ② 之后想升级：注册拿 key → 填 plist 的 `EXA_API_KEY`（或 `mcp.json` 的 `x-api-key`）→ 按第 2 步建桥 → 重启。
- 优先用 `AskUserQuestion` 工具把要问的**一次发完**（2–4 个带选项的问题），别一条一条挤牙膏；用户答不上来的项就用默认值往下走。
- **API key 不要在回复正文里回显**，直接写进 `config.toml` / `mcp.json` / plist 即可。
- 非交互场景（`kimi -p "调试 kimi-code"`）没有提问通道：这时要在提示词里一次把平台、key、要不要 MCP 说全，或让用户改用交互会话。

### 1. LLM provider、模型与思考强度

非交互（推荐，直接吃 models.dev 目录）：

```bash
kimi provider catalog list deepseek            # 看有哪些模型
kimi provider catalog add deepseek --api-key <你的 key> --default-model deepseek-flash
kimi provider list                             # 确认 provider 与默认模型
```

目录导入只解决 provider + 模型别名；**思考强度、默认权限模式仍要写进 `config.toml`**（用 `patch-config.py set`，见第 2 步的命令样式）。下面这段是作者机器上正在跑的 DeepSeek V4.1 Flash + 最高强度（实测可用）：

```toml
default_model = "deepseek/deepseek-flash"

[providers.deepseek]
type = "openai"
base_url = "https://api.deepseek.com"
api_key = "<你的 key>"

[models."deepseek/deepseek-flash"]
provider = "deepseek"
model = "deepseek-flash"                    # 上游真实模型名，以 provider 文档为准
display_name = "DeepSeek V4.1 Flash"        # 界面里显示的名字
max_context_size = 1000000                  # 必填且为正数，漏了启动直接报错
capabilities = ["image_in", "thinking", "tool_use"]
reasoning_key = "reasoning_content"         # DeepSeek 的思考内容字段
support_efforts = ["low", "high", "max"]    # 这个模型允许的思考强度档位

[models."deepseek/deepseek-flash".overrides]
default_effort = "max"                      # 只对该模型生效（比全局 [thinking] 优先）

[thinking]
enabled = true
effort = "max"                              # 全局兜底强度，其它模型也按这个来
```

- 临时换：启动参数 `-m <别名>`、会话里 `/model`。
- 别名规则是 `<provider>/<别名>`；`max_context_size` 之外写错模型名也会在启动时报错。
- **⚠️ 新机器上的坑（实测）**：kimi-code 有一次性的 `thinking-effort-max-to-high` 迁移——**首次**启动某个 kimi home 时，如果 `[thinking] effort` 是 `max`，它会被自动改写成 `high`（迁移标记记在 `<home>/migrations-effort.json`，同一 home 只跑一次，之后你手写的值不再被改）。所以在新机器上要么**先启动一次再写** `[thinking] effort = "max"`，要么就别依赖全局值——把 `max` 放在模型级的 `[models."…".overrides].default_effort = "max"`（迁移只碰全局 `[thinking]`，不动它）。

注意：跑过 `/login`（登录 Kimi 账号）会把 `config.services` 重写成 Kimi 托管服务，**第 2 步的 Exa 配置会被顶掉**；两者想共存得重新加回来。

### 2. 内置联网工具 → 自己的 Exa

一句话：放脚本（`$SKILL_DIR/assets/exa-bridge.py`）→ 用 `assets/patch-config.py` 写两段 `[services.*]` → 起常驻（macOS launchd / Windows 计划任务·`HKCU\...\Run`·启动文件夹三选一 / Linux systemd user unit）→ 三层验证。

**别手动往 config.toml 追加配置**（实测坑：重复追加已存在的表会让整份配置失效，报错却是 `No model configured`）——统一走补丁脚本：

```bash
python3 "$SKILL_DIR/assets/patch-config.py" set services.moonshot_search.base_url http://127.0.0.1:8787/search
python3 "$SKILL_DIR/assets/patch-config.py" set services.moonshot_search.api_key  "<本地令牌>"
python3 "$SKILL_DIR/assets/patch-config.py" set services.moonshot_fetch.base_url  http://127.0.0.1:8787/fetch
python3 "$SKILL_DIR/assets/patch-config.py" set services.moonshot_fetch.api_key   "<本地令牌>"
python3 "$SKILL_DIR/assets/patch-config.py" check
```

**动手前必读 `references/web-tools-exa.md`**：HTTP 契约、mac / win / linux 三套常驻命令、验证命令、排错表、回滚都在那里。Windows 实测提醒：非管理员机器上计划任务会 `Access is denied`、`HKCU\...\Run` 可能被安全软件静默回滚（写完立刻回读），最后一条**启动文件夹快捷方式**不需要提权；桥的令牌与日志靠 `assets/windows-launch.pyw.template` 生成的 `launch.pyw`（`pythonw` 没有控制台，不包装就没有 `bridge.log`）。

### 3. 外部工具通道（exa 走 mcp.json、computer-use 走官方下载）

`~/.kimi-code/mcp.json` —— **只放 exa**（kimi-cu 不走这里，官方插件自带声明，见下）：

```json
{
  "mcpServers": {
    "exa": {
      "url": "https://mcp.exa.ai/mcp",
      "headers": { "x-api-key": "<Exa key>" }
    }
  }
}
```

- **exa**：与内置通道是**同一把 Exa key、同一份额度**，但能力是超集：多 URL 批量抓取、`maxCharacters`、`numResults`/`objective`、`agent_run` 多步调研。
- **kimi-cu（computer-use，默认也装上）**：操作本机真实浏览器 / App 界面的工具——截图读界面、点击、输入、滚动……
  - **一律走 kimi 官方下载**。kimi-code 自己内置了这个能力（`kimiCu.ts`：先 `detect` 再 `install`），安装器从官方 CDN 取包、装插件，**并且会自动移除旧的 `mcp.json` 手写注册**：

    | 平台 | 官方下载（`https://cdn.kimi.com/…`） | 插件 id | 装好后的工具名 |
    |------|--------------------------------------|---------|----------------|
    | macOS | `kimi-computer-use/latest/KimiCU.app.zip`（App，用 `ditto` 解压）+ `kimi-computer-use/latest/kimi-cu-plugin.zip`（插件），装完跑 `request-permissions --ax --screen` | `kimi-cu` | `mcp__plugin-kimi-cu_<server>__*` |
    | Windows | `kimi-computer-use-windows/latest/setup_windows.ps1`（校验 SHA-256 + Authenticode，把 runtime 装到 `%LOCALAPPDATA%\KimiCU\`）+ `kimi-computer-use-windows/latest/kimi-cu-win-plugin.zip`（插件） | `kimi-cu-win` | `mcp__plugin-kimi-cu-win_win__*` |
    | Linux | **没有**——官方只发 macOS / Windows 两套包（2026-09-16 查证：官方文档只列这两个平台；CLI 的 `kimiCu.ts` 里只有 `createMacKimiCuEntry` / `createWindowsKimiCuEntry`；官方插件市场 `plugins/marketplace.json` 里没有 kimi-cu 条目）。**别硬装 macOS 包**：`KimiCU.app.zip` 是带 AppleScript 的 Mach-O App，Linux 上跑不起来 | — | — |

  - **手动装**（两条路等价，Windows 侧实测过）：TUI 里 `/plugins install <上表 plugin.zip 的完整 URL>`（`/plugins` 是**交互式斜杠命令，`kimi -p` 里不会执行**）；Windows 的 runtime 也可以直接跑官方脚本：`powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod 'https://cdn.kimi.com/kimi-computer-use-windows/latest/setup_windows.ps1' | Invoke-Expression"`。装完 `/reload` 或新开会话生效。
  - **别再手写 `mcp.json` 的 kimi-cu 条目**：官方插件自带 MCP 声明（Windows 是 `cmd /c bin\kimi-cu-mcp.cmd` → `%LOCALAPPDATA%\KimiCU\kimi-cu.exe mcp`，cwd 是插件根）。手写条目与插件**并存会各拉一个实例抢键鼠**——`verify.py` 的 MCP 检查专门拦这一条（实测报 FAIL），所以切换顺序是「先装插件 → 再删手写条目 → `/reload` 或新开会话」。
  - **macOS 权限**：首次调用若报权限错误，按安装器提示、或去「系统设置 → 隐私与安全性」给 KimiCU 打开辅助功能 / 屏幕录制。
  - **Windows 注意**：需要 PowerShell 5.1 或 7；会短暂接管真实鼠标键盘（不如 macOS 能稳定后台注入）；目标程序以管理员运行时 KimiCU 也要同级权限；安全软件可能拦"输入注入"，需要放行。另外**桌面端设置里的「Computer Use」是 macOS 专属**（`process.platform !== "darwin"` 直接返回 unsupported），Windows 上找不到它是正常的。
  - **Linux 上没有官方安装路径（2026-09-16 查证，别白费劲）**：要"操作界面"只能绕——① 官方插件 **Kimi WebBridge**（`/plugins` → Official，跨平台；装的是浏览器扩展，驱动你自己的浏览器，不是桌面 App）；② 需要点界面的活儿改走 API / CLI。`verify.py` 在 Linux 上已把 kimi-cu 两项降级成 INFO，不再算告警。
- 权限：`[[permission.rules]]` + `decision = "allow"` + `pattern = "mcp__exa__*"`；**kimi-cu 别给 allow，让它按默认询问**——它会真的动你的鼠标键盘。
- `enabled` / `startupTimeoutMs` / `toolTimeoutMs` / `enabledTools` 都可省；改完新开会话生效。

**通道优先级：默认走内置，MCP 只在"需要"时上**（这条必须同时落到第 5 步的 AGENTS.md 里，模型才会照做）：

| 场景 | 用哪个 |
|------|--------|
| 普通搜一下 / 抓一个网页 | **内置 `WebSearch` / `FetchURL`**（免确认；固定 5 条、约 400 字符摘要） |
| 内置做不到的：一次抓多个 URL、控长 `maxCharacters`、`numResults`/`objective`、多步调研 `agent_run` | exa 的 `mcp__exa__*` |
| 内置通道坏了（桥挂 / 没起） | 切 `mcp__exa__*`（独立连接，不受桥影响） |
| 内网地址、localhost、要登录态 cookie 的页面 | 只能 Bash curl（两条通道都抓不到） |
| 要操作本机浏览器 / App 界面 | computer-use 工具（官方插件：`mcp__plugin-kimi-cu-win_win__*` / macOS `mcp__plugin-kimi-cu_*`） |

### 4. 权限模式（Ask When Needed）与工具开关

```bash
python3 "$SKILL_DIR/assets/patch-config.py" set default_permission_mode yolo
python3 "$SKILL_DIR/assets/patch-config.py" ensure-rule allow 'mcp__exa__*'
```

三种模式（界面名与行为来自 CLI 自带文案）：

| 配置值 | 界面名 | 行为 |
|--------|--------|------|
| `manual` | Always Ask | 只自动读文件，其它动作都要你批准 |
| `yolo` | **Ask When Needed**（推荐） | 常规编辑和命令自动跑；风险操作、提问、计划仍会问你 |
| `auto` | Never Ask | 全自动，不打扰，全部由它自己决定 |

- 启动时临时覆盖：`kimi -y`（Ask When Needed）、`kimi --auto`（Never Ask）。
- 会话里切换：斜杠命令 `/yolo`（别名 `/yes`）、`/auto`、`/permission`。
- 工具开关：`[tools] disabled = []` 里**不要**出现 `WebSearch` / `FetchURL`（补丁脚本的 `check` 会替你盯这件事）。
- `[[permission.rules]]` 的 `pattern` 语法：工具名，或 `工具名(参数 glob)`；`*` 通配；decision 取 `allow | deny | ask`。

### 5. 策略文件 AGENTS.md

kimi-code 会读（层级叠加，就近优先）：`~/.kimi-code/AGENTS.md` → 项目 `.kimi-code/AGENTS.md` → 项目 `AGENTS.md`（另有 `~/.agents/AGENTS.md`）。新机器至少写清联网工具的分工，否则模型不知道什么时候换通道：

> **默认优先内置**：普通搜索 / 抓取一律先用 `WebSearch` / `FetchURL`（打到本机 exa-bridge，固定 5 条、约 400 字符摘要，免确认）。**只有需要内置做不到的能力时**才切到 exa 的 MCP `mcp__exa__*`：一次抓多个 URL、控制 `maxCharacters`、调 `numResults`/`objective`、`agent_run` 多步调研。内置通道失效（桥挂、未起）时也切 MCP；内网地址、localhost、需登录态 cookie 的页面只能用 Bash curl；要操作本机浏览器 / App 界面时用 computer-use 工具（官方插件：Windows `mcp__plugin-kimi-cu-win_win__*`、macOS `mcp__plugin-kimi-cu_*`）。

### 6. Todo 面板守卫（Stop 钩子 + 约定）

多步任务用 `TodoList` 记进度时，面板很容易烂尾（活干完了、一屏 ✔ 还挂着）。**先落约定**（写进 `~/.kimi-code/AGENTS.md`）：

> **任务清单（Todo 面板）**：① 一项一确认——每完成一项先核对结果（实测 / 查状态 / 看输出）再标 `done`，不攒到最后批量改，也不凭"看起来完成了"下判断；② 做完就清——所有项 `done` 后立即 `TodoList(todos: [])` 清空面板；③ 等用户的项——只能由用户手动完成或被外部条件卡住的项，如实留在清单里并注明「这步等你」，用户做完后下一轮先核对，再标 `done` 或整体清空。

**再用配置兜住第 ② 条**（人（模型）会忘，钩子不会）：

```bash
mkdir -p ~/.kimi-code/hooks
cp "$SKILL_DIR/assets/todo-panel-guard.py" ~/.kimi-code/hooks/
python3 "$SKILL_DIR/assets/patch-config.py" ensure-hook Stop "python3 ~/.kimi-code/hooks/todo-panel-guard.py" --timeout 5
```

判据：`patch-config.py check` 出现 `PASS 有 Todo 面板守卫钩子`；`verify.py` 的「钩子脚本行为」PASS（全 done → 拦、清空 → 放行）。机制、三平台写法（Windows 用 `python3 C:/…` 形式，已实测）、端到端验证法、回滚都在 `references/todo-panel-guard.md`。**新会话生效**（钩子不热加载），装完按**第 8 步**总验收时顺手再验一次。

### 7. 状态栏（缓存命中率 + API 余额）

footer 第一行常显**整个会话的缓存命中率**和**当前 provider 的 API 余额**（DeepSeek / Moonshot 这类有余额接口的 provider），不用每次都开 `/usage`：

```bash
cp "$SKILL_DIR/assets/statusline.py" ~/.kimi-code/
python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" \
  set status_line.command "python3 ~/.kimi-code/statusline.py"
```

- 缓存率从会话日志 `agents/main/wire.jsonl` 的 `usage.record` 累计（与 `/usage` 面板同源），余额走 provider 的余额接口、缓存 5 分钟后台刷新；脚本主路径 macOS ~50ms、**Windows 实测 156ms（经 `cmd.exe`，惰性导入 `urllib.request`/`subprocess` 之后；改之前 244ms）**，而 kimi-code 给的上限是 300ms，失败/超时自动回落内置布局。
- Windows（2026-09-16 实测：Windows 11 + kimi-code 0.43.1）：脚本放 `%USERPROFILE%\.kimi-code\`，命令写 `python3 C:/Users/<你>/.kimi-code/statusline.py`——正斜杠绝对路径，cmd.exe 与 Git Bash 都能跑（`~` 不展开；`%USERPROFILE%` 只在 cmd 里展开）。**别照搬 `py -3`**：Store 版 Python 不带 `py` 启动器，先 `where python` 看一眼。300ms 余量很薄，别把重依赖加回脚本顶部。
- **Windows 上这脚本还顺手兜底桥**（2026-09-16 加）：同一条命令会探活 exa-bridge，拒连就自动拉起（门闩是 runner 注入的 `KIMI_CODE_STATUS_LINE=1`，手动跑/体检自测不触发；实测杀掉桥 2 秒内自愈）。也就是说它不再只是"显示"——细节、开销与边界都在 `references/statusline.md` 已知边界。
- 判据：`verify.py` 的状态栏几项全 PASS（含脚本行为自测）；`/reload-tui` 后 footer 第一行出现 `cache N%`（**Windows 2026-09-16 截屏复核过**：footer 第一行渲染出 `… cache 97%  bal ¥38.16  cached 8.4M · uncached 223k  ~`，数字逐秒更新）。
- 自定义行会**整体替换** footer 第一行（脚本复刻了模式徽章 / 模型名 / cwd / git 分支，另加缓存率与余额）——想回到内置槽位就注释掉 `command`。机制、排错表、回滚、已知边界都在 `references/statusline.md`。

### 8. 总验收

**一条命令**（推荐，只读，覆盖出网 / 配置 / 桥 / MCP / 工具清单 / 钩子 / 状态栏 / CLI doctor / 补丁脚本自测 / 脚本漂移）：

```bash
python3 "$SKILL_DIR/assets/verify.py"          # 快速体检
python3 "$SKILL_DIR/assets/verify.py" --e2e    # 再跑一次真实端到端（慢，20–60s）
```

退出码 `0` 全通过 / `1` 有告警 / `2` 有失败；末尾会列出所有失败项。**脚本会替你分清楚"网络不通"和"配置错了"**——出网不通时它把桥的失败降级成告警，别再去冤枉桥。

想自己看原始记录时：

```bash
python3 - "$(ls -t ~/.kimi-code/sessions/*/session_*/agents/main/wire.jsonl | head -1)" <<'PY'
import json, sys
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    if '"llm.tools_snapshot"' in line:
        tools = json.loads(line)["tools"]
        print(len(tools), "个工具:", ", ".join(t["name"] for t in tools))
        break
PY
```

**汇报**：改过哪些文件、`verify.py` 的输出、哪一步没验证（明说，别含糊）。

## 体检模式（只读：不动任何文件）

用户说"**看看这台机器的 kimi-code 现在怎么样**""帮我体检一下"时走这条路，别顺手去改配置：

```bash
python3 "$SKILL_DIR/assets/verify.py"          # 体检主入口
python3 "$SKILL_DIR/assets/patch-config.py" check   # 只看配置结构（重复表 / 解析 / services 段 / 钩子）
```

体检结论怎么读：

| 结果 | 含义 | 下一步 |
|------|------|--------|
| `出网不通` / `代理出口不通` | 网络 / 代理层问题，**不是 kimi-code 的错**——体检脚本会替你区分"要走代理的域名全超时但直连正常"（=代理出口挂了）和"整机没网" | 代理软件里换节点 / 更新订阅 / 确认选中了可用节点（或 TUN 开着）；恢复后重试即可，不用改配置。细节见 `references/web-tools-exa.md` 排错表 |
| `services.*` 缺失或指向 Kimi 托管 | 大概被 `/login` 顶掉了 | 按第 2 步用补丁脚本加回来 |
| `桥 /health 打不通` | 桥没在跑（实测会被静默杀掉：重启后没起来、或中途被杀；日志无 traceback 不代表没挂） | **先只认 `/health`**（别用 `Get-Process pythonw`——真名是 `pythonw3.13`）。**先等 5~10 秒**：Windows 上状态栏脚本的兜底会自己把它拉起来（实测 2 秒内自愈）；还不行再手动救活：macOS `launchctl print gui/$(id -u)/ai.kimi.exa-bridge`；**Windows 跑一次 `kimi-exa-bridge.lnk`**（不用 `Get-ScheduledTaskInfo`，本机没建计划任务）；Linux `systemctl --user status ai.kimi.exa-bridge`。细节见 `references/web-tools-exa.md` 2.5 |
| `直打桥搜索 401` | `config.toml` 的令牌与桥的 `EXA_BRIDGE_TOKEN` 不一致 | 两边对齐，或把桥的 token 留空 |
| `常驻定义令牌 … 不一致` / `常驻定义有 CR（\r）` | 常驻定义（plist / systemd unit / launch.pyw）里的令牌与 `config.toml` 对不上；最隐蔽的一种是 **CRLF 模板 sed 出来的定义**（令牌尾部多个回车） | 重新生成定义：`sed` 前先 `tr -d '\r' < 模板 \| sed …`；细节见 `references/web-tools-exa.md` 排错表 |
| `桥脚本一致性 … 有漂移` | skill 里的副本 ≠ 机器上在跑的 | 想清楚以哪份为准，再 `cp` 过去 + 重启桥 |
| `钩子：没有 [[hooks]]` / `没装 Todo 面板守卫` / `钩子脚本行为 … FAIL` | 第 6 步没做、规则被删、或脚本被改坏 | 按第 6 步重装（`ensure-hook` 幂等，重复跑安全）；钩子**新开会话**才生效 |
| `状态栏：` 开头的几项（tui.toml 缺 `[status_line]` / command 为空 / 脚本缺失 / 行为自测 FAIL） | 第 7 步没做、`tui.toml` 被还原或被 `/reload-tui` 之外的手段改回、脚本被改坏 | 按第 7 步重装（补丁脚本幂等）；**`/reload-tui` 当场生效**，不用重启会话 |
| `kimi doctor` 非 0 | `config.toml` / `tui.toml` 连 CLI 都读不进去（手改出语法错 / 补丁脚本被绕过） | `patch-config.py check` 只看结构，doctor 是"CLI 能否真的读进去"的最终判据；对照 `.bak` 还原或按对应章节重跑补丁脚本 |
| `补丁脚本行为 … FAIL` | skill 里的 `patch-config.py` 被改坏（幂等 / 复验 / 删除逻辑） | 它是一切改配置动作的底座，先用备份或重新拷 skill 副本修好它，再动别的 |
| 工具清单缺 `WebSearch` | `[tools] disabled` 关了它，或版本变了 | 看第 4 步；版本变了先核对本文的验证版本 |
| 日志里同一条 WARN 反复出现（体检会报） | 后台任务空转；最常见是 `session index reconciliation failed`（实验特性 minidb read-model 在重建会话索引） | 它只是加速用的读模型，**不影响正常干活**；成功一次后会打印 `repaired drift` 自愈。持续刷屏时可以 `find ~/.kimi-code -name .DS_Store -delete` 清掉 Finder 垃圾再跑一次；仍不行就设 `KIMI_CODE_EXPERIMENTAL_PERSISTENCE_MINIDB_READMODEL=false` 关掉该实验特性（**实测有效**：关掉后日志里连 `minidb query-store opening` 都不再出现） |

什么时候该体检：**升级 kimi-code 之后、怀疑 `/login` 动过配置、桥挂过一恢复、把配置搬到新机器前后、以及每次改完 `config.toml`**。

## 红线（别做这些）

- **别手动改 `config.toml` / `tui.toml`（增、改、删都不行）**——重复表 = 整份配置失效，`patch-config.py` 就是为这个存在的：写入用 `set` / `ensure-rule` / `ensure-hook`，删除用 `unset` / `remove-rule` / `remove-hook`。
- **别主动跑 `/login`**：它会重写 `config.services`，把 Exa 通道顶掉（用户自己要登录另说，登完记得复检）。
- **别覆盖 `config.toml`**：只动该动的字段（providers 里其它条目、用户自己的注释都留着）。
- **别给 computer-use 工具加 allow 规则**（官方插件 `mcp__plugin-kimi-cu-win_win__*` / macOS `mcp__plugin-kimi-cu_*`）：它会真的操纵键鼠，保持按默认询问。
- **别把 A 机器的 key 写进 B 机器**：key 属于用户，缺就让用户贴；写进文件的路径是 plist / `mcp.json` / `config.toml`，**不要贴进聊天正文**。
- **别重复追加 MCP server**：`mcp.json` 是 JSON，后写的键覆盖前面的（不会报错但会静默丢配置），改前先读现有内容。
- **别跳步验收**：`verify.py` 没全绿就说"配好了"是不允许的；没验证的项要明说。

## 配置生效时机（省时间，别瞎重启）

| 改动 | 生效方式 |
|------|----------|
| `[services.*]`（搜索/抓取端点） | 进程里只解析一次 → **退出重启 `kimi`**（`-r` 恢复会话） |
| `[tools].disabled` | 当场生效 |
| `[[hooks]]` | 会话启动时加载 → **新开会话**生效（当前会话不变） |
| `mcp.json` | 有文件监听，通常会热重载；不确定就重启最稳 |
| `tui.toml`（状态栏 / 主题 / 编辑器等） | `/reload-tui` 当场生效（`/reload` 也行） |
| 常驻定义（launchd plist / 计划任务 / 启动文件夹 / systemd unit） | mac：`bootout` + `bootstrap`（只改脚本用 `kickstart -k`）；Windows：计划任务就重建任务，启动文件夹就改那个 `.lnk`、注册表就重写值（**只改脚本**时直接重启桥进程即可）；Linux：`systemctl --user daemon-reload`，再 `systemctl --user restart ai.kimi.exa-bridge` |
| 会话日志 | `~/.kimi-code/sessions/<工作目录 id>/session_<uuid>/agents/main/wire.jsonl` |

## 扩展这个 skill

- **细则放 `references/<主题>.md`，本文件只留 3–6 行要点 + 判据 + 链接**，文件再长也不挤上下文。
- 加了新主题，记得在上面的主流程表里补一行，否则后来的人（或 agent）看不见它。
- 脚本、配置模板、安装脚本放 `assets/`；**新增落地点优先复用 `patch-config.py`（写）和 `verify.py`（读）**，别再手写"追加/覆盖"逻辑。
- **已实测 与 "按标准做法写的" 要分开标注**（例：Windows 那节就是这么标的），免得下次被当成已验证。
- **一律 LF**（仓库已用 `.gitattributes` 钉住）：`assets/*.template` 要拿去 `sed` 生成常驻定义，CRLF 会让令牌尾部多一个 `\r`（实测 401）。Windows 侧检出后别再把行尾改回 CRLF。
- **正本只保留一份**（本机的"安装副本"除外）：改动只动正本，改完按上面「放在哪」一节同步到 `~/.kimi-code/skills/kimi-code-setup/`；搬运/归档完别在别处再留第三份，前后用 `diff -rq 旧目录 新目录` 核对——`verify.py` 的"脚本一致性"只比对 3 个部署脚本，不比对文档。
- 正本是个 git 仓库（`origin` = 公开仓库）：动手前 `git status` 确认工作区干净，改完 `git commit` + `git push`。**别再用 `cp -a` 做目录备份**——git 就是备份，`cp -a` 只会把 `.git` / `__pycache__` 一起拷进去。
- 换了 kimi-code 版本，先跑 `verify.py`，再更新顶部那句"验证版本"。
- 改了目录名或位置，记得同步：frontmatter 的 `name`、本文件与 `references/` 里的 `$SKILL_DIR` 说明、以及作者机器上 `~/.kimi-code/AGENTS.md` 里的指路与触发约定。

## 参考：作者机器上的现状（搬配置/对照用）

- `~/.kimi-code/config.toml`：`default_model = "deepseek/deepseek-flash"`（DeepSeek V4.1 Flash）、`default_permission_mode = "yolo"`（Ask When Needed）、`[thinking] effort = "max"` 与该模型的 `default_effort = "max"`、`[services.*]` 指向本机 exa-bridge、`[[permission.rules]]` 放行 `mcp__exa__*`、`[[hooks]]` 一条 `Stop` 钩子指向 `~/.kimi-code/hooks/todo-panel-guard.py`（`timeout = 5`）。
- `mcp.json`：只有 `exa`（computer-use 走官方插件，**不写进 `mcp.json`**）；`AGENTS.md`：联网工具分工 + 任务清单三条约定 + 本 skill 的触发约定。
- 常驻：macOS LaunchAgent `ai.kimi.exa-bridge`；脚本 `~/.kimi-code/exa-bridge/exa-bridge.py`（除 `/search`、`/fetch` 外还带只读的 `/status` 与 `/panel`，供 kimi web 端小面板用），日志同目录 `bridge.log`，本地令牌写在 `config.toml` 的两处 `[services.*].api_key` 里。
- 面板守卫：`~/.kimi-code/hooks/todo-panel-guard.py`（与本目录 `assets/` 副本逐字节一致，sha256 前 12 位 `bcab948b6ff0`）；端到端实测过——`kimi -p` 故意留一个全 done 面板，被钩子拦回、模型随后自行清空。
- 状态栏：`~/.kimi-code/statusline.py`（与本目录 `assets/` 副本逐字节一致，sha256 前 12 位 `dc0642a2e5f2`）+ `tui.toml` 的 `[status_line].command = "python3 ~/.kimi-code/statusline.py"`；端到端实测过——另起一个临时实例截屏，footer 第一行渲染出 `… cache 98%  bal ¥44.50 …`。
- 本机体检基线（2026-09-15，kimi-code 0.41.0）：`verify.py` **34 项通过 / 0 告警 / 0 失败**（当时网络是通的）。代理出口挂掉时唯一失败项会是"出网不通"，属网络层，与配置无关。

### Windows 11 实测基线（2026-09-16，kimi-code 0.43.1，Store 版 Python 3.13，非管理员账户）

- `verify.py`：**34 项通过 / 0 告警 / 0 失败**（`--e2e` 再 +2 = 36 项全过，真实搜索走桥成功；2026-09-16 复核。早先那次的 3 条告警是 kimi-cu 未启用，现已消除）。工具清单项是"最近 3 个会话快照的并集"，因为 `kimi -p` 有时在 MCP 握手前就拍快照。
- `config.toml` / `tui.toml`：字段与 macOS 完全一致（`yolo`、`[thinking] effort = "max"`、`[services.*]` 指本机桥、`[[permission.rules]]` 放行 `mcp__exa__*`）。
- 钩子 / 状态栏命令都写成 `python3 C:/Users/<你>/.kimi-code/...`（**实测 kimi 用 `cmd.exe` 执行钩子命令**，`%USERPROFILE%` 也会展开；但 Store 版 Python 没有 `py` 启动器，别写 `py -3`）。
- 常驻：启动文件夹快捷方式 `kimi-exa-bridge.lnk` → `pythonw.exe "%USERPROFILE%\.kimi-code\exa-bridge\launch.pyw"`（计划任务被非管理员权限拒、`HKCU\...\Run` 被火绒回滚，见 `references/web-tools-exa.md`）。桥日志照常落在 `%USERPROFILE%\.kimi-code\exa-bridge\bridge.log`。
- kimi-cu（computer-use）：**全部走官方下载**——Windows 侧是官方 runtime（`setup_windows.ps1` → `%LOCALAPPDATA%\KimiCU\`）+ 官方插件（`/plugins install …/kimi-cu-win-plugin.zip`；2026-09-16 实机切换完成，v0.2.17 落在 `~/.kimi-code/plugins/managed/kimi-cu-win/`，`plugins/installed.json` 记 `enabled: true`）；kimi-code 自己内置了这个能力的安装器（`kimiCu.ts`），会顺手**移除旧的 `mcp.json` 手写注册**。插件自带 MCP 声明 `mcpServers.win`（`cmd.exe` + `bin\kimi-cu-mcp.cmd`，cwd 是插件根，13 个 enabledTools），所以**工具名是 `mcp__plugin-kimi-cu-win_win__*`**，不再是 `mcp__kimi-cu__*`；`mcp.json` 里**已无** kimi-cu 条目。**两条路互斥**（并存＝两个实例抢键鼠）：`verify.py` 的 MCP 检查专门拦这一条（实测会报 FAIL），切换顺序是「先装插件 → 再删手写条目 → 最后 `/reload` 或新开会话」。

### Linux 实测基线（2026-09-16，WSL2 + kimi-code 0.41.0，Python 3.14.7，非 root）

- `verify.py`：**33 项通过 / 0 告警 / 0 失败**；`--e2e` 35 项全过（真实搜索走桥成功、`bridge.log` 同步增长）。kimi-cu 那两项在 Linux 上降级成 `INFO`——没有官方路径，不该算告警。
- `config.toml` / `tui.toml`：字段与 macOS 完全一致（`yolo`、`[thinking] effort = "max"` + 模型级 `default_effort = "max"`、`[services.*]` 指本机桥、`[[permission.rules]]` 放行 `mcp__exa__*`、`[status_line].command`）。
- 常驻：systemd 用户单元 `ai.kimi.exa-bridge`（`~/.config/systemd/user/`，`enable --now`；软链落在 `default.target.wants/`）。`loginctl enable-linger "$USER"` 在 WSL2 上**免提权**通过；`kill -9` 桥后 `Restart=always` 几秒内拉起（新 PID + `/health` 恢复）。
- 钩子 / 状态栏命令都写成 `python3 ~/.kimi-code/hooks/todo-panel-guard.py` / `python3 ~/.kimi-code/statusline.py`（与 macOS 相同；`~` 由 shell 展开，实测可用）。
- **CRLF 坑（本机实测踩到，已修）**：从 Windows 侧打包出来的工作区是 CRLF，`sed` 生成的 systemd unit 每行结尾带 `\r` → `EXA_BRIDGE_TOKEN` 尾部多一个回车，与 `config.toml` 里的值对不上（当时 `patch-config.py` 的复验拦下了没落盘，但没修之前一直是个雷）。现在的五道防线：整仓转 LF + `.gitattributes`（`* text=auto eol=lf`）+ 文档里 `sed` 前一律先 `tr -d '\r'` + `patch-config.py` 当场拒绝控制字符 + `verify.py` 新增「常驻定义令牌」比对（连 `\r` 都认得出来）。
- 端到端：Todo 守卫用 `kimi -p` 实测——故意留一个全 `done` 的面板，被钩子拦回、模型随后自行清空。
- kimi-cu：**Linux 没有官方路径**（证据与退路见第 3 步的表格和下面那条说明）。
