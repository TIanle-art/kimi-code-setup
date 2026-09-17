---
name: kimi-code-setup
description: |
  新机器上把 kimi-code 从零配到可用（macOS / Windows / Linux）：provider 与模型、内置 WebSearch/FetchURL 接自己的 Exa（exa-bridge）、MCP、权限、AGENTS.md、Todo 守卫钩子、状态栏；也支持只读体检。触发：「调试/配置 kimi-code」「体检」、WebSearch 不能用、FetchURL 撞 WEB_PRIVATE_ADDRESS、exa-bridge 挂了、/login 顶掉配置。
metadata:
  version: "3.8.0"
---

# 全新 kimi-code 落地（新机器开箱配置）

**这个 skill 管的是"把一台新机器上刚下载的 kimi-code 配到能用"，不是修 bug**——排错只是收尾的一环。细则按主题放在 `references/`，本文件只留主流程、判据和索引；手上的脚本放在 `assets/`。

> **验证版本**：配置字段、权限模式文案、迁移行为、脚本契约实测于 **kimi-code 0.41.0（macOS，2026-09-15）**；Windows 分支的常驻方式、钩子/状态栏命令写法、kimi-cu 入口实测于 **Windows 11 + kimi-code 0.43.1（Store 版 Python 3.13，非管理员账户，2026-09-16）**；**Linux 分支的 systemd 常驻、桥三层验证、钩子实时拦截实测于 WSL2 + kimi-code 0.41.0（Python 3.14，2026-09-16）**；**Windows 11 + kimi-code 2.0.0（Python 3.11.9，非管理员，2026-09-18）复跑：主流程与 `assets/verify.py --e2e` 全通过；同期修复中文 Windows 的钩子提示 GBK 乱码（`-X utf8`，见 `references/todo-panel-guard.md`），并补记 kimi-cu 两条装法与 2.0.0 安装器会写冗余 `mcp.json` 条目（见 `references/computer-use.md`）**。实测结论都带"✅/❌ 实测"标注。换了版本（或机器上版本不同）先跑一次 `assets/verify.py` 看结论是否还对得上。

## 这个目录放在哪、怎么用

- **怎么触发**：拷进目标机器的 `~/.kimi-code/skills/kimi-code-setup/` 后，直接说「**调试 kimi-code**」「配置 kimi-code」这类话即可——agent 按 description 命中后自动加载本文件，缺参数（Exa key、平台是 mac / win 还是 linux、要不要挂 MCP）它会先问清再动手，不用背固定提示词。
- **作者机器（macOS，桌面正本）**：**正本在桌面** `~/Desktop/kimi-code-setup/`（改动只动这份；它同时是个 git 仓库，`origin` 指向公开仓库 https://github.com/TIanle-art/kimi-code-setup ，改完 `git push` 就更新公开版），**安装副本在** `~/.kimi-code/skills/kimi-code-setup/`（kimi 自动发现、直接能命中 `kimi-code-setup` skill 的那份）。改完正本跑一次同步（**必须带 `--exclude=.git`**，否则会把仓库元数据拷进 skill 目录），再体检确认：

  ```bash
  rsync -a --delete --exclude=.git ~/Desktop/kimi-code-setup/ ~/.kimi-code/skills/kimi-code-setup/
  python3 ~/Desktop/kimi-code-setup/assets/verify.py | tail -3
  ```

  Windows 上没有 rsync（Git Bash 一般也不带），等价做法是 `robocopy` 或 `cp -r`；同步完**在 Git Bash 里**用 `diff -rq --exclude=.git 旧目录 新目录` 核对（**PowerShell 里别这么写**：`diff` 是 `Compare-Object` 的别名，不认 `-rq` / `--exclude`）：

  ```powershell
  # 下面两行只在 PowerShell / cmd 里跑——Git Bash 会把 /MIR /XD 改写成 D:/…/MIR 报错（实测）
  robocopy "$env:USERPROFILE\Desktop\kimi-code-setup" "$env:USERPROFILE\.kimi-code\skills\kimi-code-setup" /MIR /XD .git /NFL /NDL
  python "$env:USERPROFILE\Desktop\kimi-code-setup\assets\verify.py" | Select-Object -Last 3
  ```

  Git Bash 里想用 robocopy 就加 `MSYS_NO_PATHCONV=1` 关掉路径改写：`MSYS_NO_PATHCONV=1 robocopy "C:/Users/<你>/Desktop/kimi-code-setup" "C:/Users/<你>/.kimi-code/skills/kimi-code-setup" /MIR /XD .git /NFL /NDL`。
- **WSL2（Linux）那台**：正本在 `~/projects/kimi-code-setup`（同一个 git 仓库、同一个 `origin`，改完 `git push` 就更新公开版），安装副本同样在 `~/.kimi-code/skills/kimi-code-setup/`，同步就是在那个目录里跑上面同一条命令（源路径换成 `./` 或 `~/projects/kimi-code-setup/`）。
- **要用在别的机器上**：把整个目录拷到目标机器的 `~/.kimi-code/skills/kimi-code-setup/`（Windows：`%USERPROFILE%\.kimi-code\skills\kimi-code-setup\`），那里新开的 kimi 会话就会自动发现它；不拷也行，直接把文件带过去让 agent 读。
- **本机想临时当 skill 用**：`kimi --skills-dir ~/Desktop --skills-dir ~/.kimi-code/skills`（实测：`--skills-dir` 会**替换**自动发现的目录，所以要补上原来的 `~/.kimi-code/skills` 才不丢 `kimi-webbridge` / `markitdown`；它按整棵子树递归扫描，指到桌面会把 `桌面/开源工具/` 下的 170+ 个 skill 一起带进来，很吵）。更省事的是让 agent 直接读本文件。
- 下文里的 **`$SKILL_DIR`** 指这个 skill 所在目录：macOS 上正本是 `~/Desktop/kimi-code-setup`、WSL2 上是 `~/projects/kimi-code-setup`，安装副本都是 `~/.kimi-code/skills/kimi-code-setup`（两份内容一致，用哪份都行）；拷到目标机器后就是 `~/.kimi-code/skills/kimi-code-setup`（Windows 用 `%USERPROFILE%\.kimi-code\skills\kimi-code-setup`）。命令里出现 `$SKILL_DIR` 时按实际位置展开。

## assets 里有什么（手脚）

| 脚本 | 干什么 |
|------|--------|
| `assets/exa-bridge.py` | 内置 WebSearch / FetchURL 的适配器（转调 Exa），部署到 `~/.kimi-code/exa-bridge/`；本文件里的副本 = 机器上在跑的那份 |
| `assets/launchagent.plist.template` | macOS LaunchAgent 模板（占位符替换，别手写 XML） |
| `assets/systemd-user.service.template` | Linux systemd 用户单元模板（同一套占位符；**2026-09-16 在 WSL2 实测通过**）。生成时的 `sed` 前面必须先 `tr -d '\r'`——CRLF 模板会把 `\r` 带进令牌，桥直接 401（见 `references/web-tools-exa.md`） |
| `assets/windows-launch.pyw.template` | Windows 桥启动器模板（给 `pythonw.exe` 用）：替桥写进 `EXA_BRIDGE_TOKEN` / `EXA_API_KEY`，并把 stdout/stderr 重定向到 `bridge.log`——计划任务与启动文件夹都塞不进环境变量，`pythonw` 又没有控制台。部署到 `~/.kimi-code/exa-bridge/launch.pyw`，见 `references/web-tools-exa.md` 第 3 节（Windows） |
| `assets/todo-panel-guard.py` | Stop 钩子：Todo 面板里的任务全部 `done` 却没清空时，拦下回合结束并提示先清空；部署到 `~/.kimi-code/hooks/`，见第 6 步 |
| `assets/statusline.py` | footer 状态栏：常显整个会话的缓存命中率与 provider 余额；部署到 `~/.kimi-code/`，靠 `tui.toml` 的 `[status_line]` 挂上，见第 7 步 |
| `assets/statusline-fast.c` | **Windows 专用**：状态栏热路径（编成 `statusline-fast.exe`，`gcc -O2 -static -s`）。同步 Python 空闲 240ms、忙时 400ms+，顶不住 300ms 预算；改由它做「快照落盘 + 打印预渲染行 + 拉起守护进程」，实测 **44–73ms**。见 `references/statusline.md` |
| `assets/statusline-daemon.pyw` | **Windows 专用**：状态栏守护进程（常驻 pythonw，约 1% CPU），读 `payload_*.json` 渲染 `line_*.txt`，顺带管 exa-bridge 探活与余额刷新；空闲 1 小时自动退出，热路径按心跳自动拉起 |
| `assets/kimi-web-status.user.js` | 浏览器用户脚本（Tampermonkey）：把 cache/bal 显示在 `kimi web` 页面角落，数据来自桥的 `/status`；见 `references/statusline.md`「web 端」 |
| `assets/patch-config.py` | **改 config.toml / tui.toml 只用它**：幂等（存在就改值、不存在才插入）、保留注释、写前备份、写前复验（不通过不落盘）；数组表用 `ensure-rule` / `ensure-hook` 按内容去重追加，`unset` / `remove-rule` / `remove-hook` 负责删除（回滚用）；`--raw` 写裸值，默认按字符串加引号。值里带 `\r` / `\n` 会**当场拒绝**（CRLF 坑的防线之一） |
| `assets/deploy.py` | **部署只用它**（幂等，可反复跑）：把上面这些部署脚本同步到各自落地点（Windows 5 个 / macOS·Linux 3 个），**按内容比对**——一致就一个字节都不动；Windows 上 `.c` 变过、或 exe 缺失/落后时用 MSYS2 gcc 重编 `statusline-fast.exe`，再重启状态栏守护进程让它加载新代码。`--check` 只报告（有漂移退 2），`--bridge` 连桥一起重启（会短暂中断搜索）。**不做**正本→安装副本的同步，也不碰 `config.toml` / `tui.toml`；体检报「脚本漂移」后跑它就收尾 |
| `assets/verify.py` | **一条命令体检**（分类摘要，细节以脚本输出为准）：CLI 版本 / `kimi doctor` / 出网 / 配置（默认模型、思考强度、权限模式、工具开关）/ `[services.*]` 端点**与两处 `api_key` 一致性** / 桥（`/health`、Exa key、`/status`、直打 `/search` **与 `/fetch`**）/ 常驻定义令牌一致性（与两处 `api_key` 对账）+ 解析自测 / MCP（含 kimi-cu 并存拦截）/ 工具清单 / 钩子（含行为自测）/ 状态栏（含行为自测；Windows 热路径另查「三件套齐全」与守护脚本一致性）/ 日志扫描 / 脚本漂移 / 补丁脚本自测 / 触发链；`--e2e` 再加一次真实端到端。只读，返回 0/1/2 |

> **「脚本漂移」比的是这 4 个部署脚本**：`assets/exa-bridge.py` → `~/.kimi-code/exa-bridge/exa-bridge.py`、`assets/todo-panel-guard.py` → `~/.kimi-code/hooks/todo-panel-guard.py`、`assets/statusline.py` → `~/.kimi-code/statusline.py`、`assets/statusline-daemon.pyw` → `~/.kimi-code/statusline-daemon.pyw`（Windows）。**不比对** `patch-config.py`、`verify.py`、`statusline-fast.c` 编译出的 `statusline-fast.exe`（本机产物）、三个 `.template` 生成出的常驻定义、`kimi-web-status.user.js`。

## 主流程

| # | 步骤 | 做完的判据 | 细则在哪 |
|---|------|-----------|----------|
| 0 | 装好 kimi-code + 摸清现状 + 备份 | `kimi --version` 有输出；知道配置目录、有没有配过 | 本文 |
| 1 | LLM provider、模型与思考强度 | 新进程里能正常对话、思考强度符合预期 | 本文 |
| 2 | 内置 WebSearch / FetchURL → 自己的 Exa | 三层验证全过；Windows 上自启项写完要回读确认（见细则第 3 节） | `references/web-tools-exa.md` |
| 3 | 外部工具通道（exa 走 mcp.json、computer-use 走官方下载） | 工具清单里出现 `mcp__exa__*` 与 computer-use 工具（官方插件 `mcp__plugin-kimi-cu-win_win__*` / macOS `mcp__plugin-kimi-cu_*`）；若还看到旧的 `mcp__kimi-cu__*`，说明手写条目没删——`verify.py` 会报 FAIL | 本文 + `references/computer-use.md` |
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
kimi provider list             # 已配的 provider 与默认模型
ls -la ~/.kimi-code            # 配置目录（macOS / Linux / Git Bash；cmd 里才是 dir %USERPROFILE%\.kimi-code）
curl -s http://127.0.0.1:8787/health   # 有没有既存的桥：存活只认 /health（三平台通用；Windows 写 curl.exe）
pgrep -fl exa-bridge           # 同上，但只有 macOS / Linux 有 pgrep（Windows 上没有）
```

配置目录 = `$KIMI_CODE_HOME`，未设则 `~/.kimi-code`（Windows `%USERPROFILE%\.kimi-code`）。里面：`config.toml`（主配置）、`mcp.json`（MCP 清单）、`AGENTS.md`（策略）、`skills/`、`sessions/`。

**动手前先备份**（`patch-config.py` 自己也会备份，但整体改前留一份更稳）：`cp ~/.kimi-code/config.toml ~/.kimi-code/config.toml.bak-$(date +%Y%m%d-%H%M%S)`（`mcp.json` 同理）。

**开工先问（交互会话里，一次问全）**——用户只说了一句「调试 kimi-code」时，别猜，按下面这张表把缺的补齐再动手：

| 必须问到的 | 为什么 |
|------------|--------|
| 目标平台：macOS、Windows 11 还是 Linux | 决定常驻方式（launchd / 计划任务 / systemd user unit）、以及 `~` 与 `%USERPROFILE%` 的写法 |
| **Exa API key：有还是没有** | 第 2 步的桥**必须**有 key 才建得起来；没有就走下面那张表的三条路，别硬上（已有 key 的机器上可直接搬：`mcp.json` 的 `mcpServers.exa.headers.x-api-key`） |
| LLM provider 的 API key | **仅当** `kimi provider list` 显示还没配 provider 时才问 |
| **computer-use 的插件装法（macOS / Windows 才问）**：用户手动走官方 `/plugins install`，还是 agent 代装 | 两条路都实测过、效果一样过程不同：官方装由 kimi 登记，但 **2.0.0 会多写一条 `mcp.json` 条目要删**；agent 代装＝下载 zip 原样解压 + 手写登记（2026-09-18 沙箱实测可加载），用户零命令。Linux 不问（不装）。细节 `references/computer-use.md` |

| 不用问，按默认走 | 默认值 |
|------------------|--------|
| 桥的端口 | `8787`（被占用才换） |
| 本地访问令牌 | 现场生成，不劳用户 |
| 常驻方式 | mac 用 launchd、Linux 用 systemd user unit，默认就装；**win 先试计划任务，被权限拒（非管理员）或被安全软件回滚就改用启动文件夹快捷方式**——两条都实测过，见第 2 步（细则 `references/web-tools-exa.md` 第 3 节） |
| MCP 通道 | `mcp.json` 里**只放 exa**；computer-use **不写 `mcp.json`**（走官方插件，macOS / Windows 默认装、Linux 不装），见第 3 步 |
| 权限模式 / 思考强度 | `yolo`（Ask When Needed）+ 模型级 `default_effort = "max"`，见第 1、4 步 |
| 状态栏（缓存率 + 余额） | 默认装（见第 7 步）；余额段只在 provider 有余额接口时出现 |

**用户说"我没有 Exa key"时，给他三条路挑**（别卡住，也别拿别人的 key 顶上；优先用 `AskUserQuestion` 工具把要问的**一次发完**，用户答不上来的项走默认值）：

- ① **现在去注册（推荐）**：dashboard.exa.ai 注册 → 把 key 贴回来（**2026-09 时**新账号送 $20、之后 Free Tier 每月 $10——营销数字会变，以 dashboard 为准）；两条通道都能建，花的也是他自己的额度。
- ② **先用匿名 MCP 顶着**：只写 `mcp.json` 的 `{"url": "https://mcp.exa.ai/mcp"}`、**不要 `headers`**；代价是只有 MCP 通道可用（上限未测），**内置 `WebSearch`/`FetchURL` 建不了**——桥调 `api.exa.ai` 必须要 key，这时它俩只能走 Kimi 托管（要 `/login`），说明白别让用户以为坏了。
- ③ **干脆不要 Exa**：自建 SearXNG 后把 `[services.moonshot_search].base_url` 指过去，或退回"用 Bash curl 抓指定页面"；没有搜索能力，只有抓取。

三条路的完整细节、② 之后怎么升级成正式 key、非交互（`kimi -p`）没有提问通道时怎么办，都在 `references/web-tools-exa.md` 的「收集参数」一节；**key 不要在回复正文里回显**（写进 `config.toml` / `mcp.json` / plist 即可）。

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

**动手前必读 `references/web-tools-exa.md`**：HTTP 契约、mac / win / linux 三套常驻命令、验证命令、排错速查、回滚都在那里。Windows 实测提醒：非管理员机器上计划任务会 `Access is denied`、`HKCU\...\Run` 可能被安全软件静默回滚（写完立刻回读），最后一条**启动文件夹快捷方式**不需要提权；桥的令牌与日志靠 `assets/windows-launch.pyw.template` 生成的 `launch.pyw`（`pythonw` 没有控制台，不包装就没有 `bridge.log`）。

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
- **kimi-cu（computer-use）——操作本机真实浏览器 / App 界面的工具**（截图读界面、点击、输入、滚动……）：**macOS / Windows 默认装，Linux 不装**（官方只发 mac / win 两套包，Linux 上直接跳过、别硬装 macOS 包）；**一律走 kimi 官方下载**；**插件装法先问用户**（① 用户手动走官方 `/plugins install`；② agent 代装＝下载 zip 原样解压 + 手写登记，用户零命令——两条路都实测过，差异与做法见 `references/computer-use.md` 的「装法：先问用户」）；runtime 两条路都用官方脚本，agent 直接代跑不用问。装完 `/reload` 或新开会话生效。
- **别再手写 `mcp.json` 的 kimi-cu 条目**：官方插件自带 MCP 声明（macOS `mcp__plugin-kimi-cu_*` / Windows `mcp__plugin-kimi-cu-win_win__*`），手写条目与插件**并存＝两个实例抢键鼠**——`verify.py` 的 MCP 检查专门拦这一条（实测报 FAIL）。**2.0.0 实测：官方安装器自己会写一条**（与 0.43.1 相反）——装完删掉它、功能不受影响（沙箱实测）。切换顺序是「先装插件 → 再删手写条目 → `/reload` 或新开会话」。
- 平台对照表、两条手动装命令、macOS 权限、Windows 注意事项、Linux 不装的查证，都在 `references/computer-use.md`。
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
- 工具开关：`[tools] disabled = []` 里**不要**出现 `WebSearch` / `FetchURL`——盯这件事的是 `verify.py` 的「工具开关」一项（`patch-config.py check` 只查重复表 / 解析 / services / 钩子，不看这个）。
- `[[permission.rules]]` 的 `pattern` 语法：工具名，或 `工具名(参数 glob)`；`*` 通配；decision 取 `allow | deny | ask`。

### 5. 策略文件 AGENTS.md

kimi-code 会读（层级叠加，就近优先）：`~/.kimi-code/AGENTS.md` → 项目 `.kimi-code/AGENTS.md` → 项目 `AGENTS.md`（另有 `~/.agents/AGENTS.md`）。新机器至少写清联网工具的分工，否则模型不知道什么时候换通道：

> **默认优先内置**：普通搜索 / 抓取一律先用 `WebSearch` / `FetchURL`（打到本机 exa-bridge，固定 5 条、约 400 字符摘要，免确认）。**只有需要内置做不到的能力时**才切到 exa 的 MCP `mcp__exa__*`：一次抓多个 URL、控制 `maxCharacters`、调 `numResults`/`objective`、`agent_run` 多步调研。内置通道失效（桥挂、未起）时也切 MCP；内网地址、localhost、需登录态 cookie 的页面只能用 Bash curl；要操作本机浏览器 / App 界面时用 computer-use 工具（官方插件：Windows `mcp__plugin-kimi-cu-win_win__*`、macOS `mcp__plugin-kimi-cu_*`；**Linux 上不装**，见第 3 步）。

### 6. Todo 面板守卫（Stop 钩子 + 约定）

多步任务用 `TodoList` 记进度时，面板很容易烂尾（活干完了、一屏 ✔ 还挂着）。**先落约定**（写进 `~/.kimi-code/AGENTS.md`）：

> **任务清单（Todo 面板）**：① 一项一确认——每完成一项先核对结果（实测 / 查状态 / 看输出）再标 `done`，不攒到最后批量改，也不凭"看起来完成了"下判断；② 做完就清——所有项 `done` 后立即 `TodoList(todos: [])` 清空面板；③ 等用户的项——只能由用户手动完成或被外部条件卡住的项，如实留在清单里并注明「这步等你」，用户做完后下一轮先核对，再标 `done` 或整体清空。

**再用配置兜住第 ② 条**（人（模型）会忘，钩子不会）：

```bash
mkdir -p ~/.kimi-code/hooks
cp "$SKILL_DIR/assets/todo-panel-guard.py" ~/.kimi-code/hooks/
python3 "$SKILL_DIR/assets/patch-config.py" ensure-hook Stop "python3 ~/.kimi-code/hooks/todo-panel-guard.py" --timeout 5

# Windows：kimi 用 cmd.exe 执行钩子命令、`~` 不展开，命令必须写绝对路径（正斜杠，实测）——
# python3 "$SKILL_DIR/assets/patch-config.py" ensure-hook Stop "python3 C:/Users/<你>/.kimi-code/hooks/todo-panel-guard.py" --timeout 5
# 中文 Windows 再加上 `-X utf8`（否则拦截提示按 GBK 写出、被当 UTF-8 读成乱码；2026-09-18 实测）——
# python3 "$SKILL_DIR/assets/patch-config.py" ensure-hook Stop "python.exe -X utf8 C:/Users/<你>/.kimi-code/hooks/todo-panel-guard.py" --timeout 5
```

判据：`patch-config.py check` 出现 `PASS 有 Todo 面板守卫钩子`；`verify.py` 的「钩子脚本行为」PASS（全 done → 拦、清空 → 放行）。**Windows 上必须按上面注释里那串绝对路径装**（`~` 在 `cmd.exe` 里不展开；Store 版 Python 没有 `py` 启动器，别写 `py -3`；**中文 Windows 用带 `-X utf8` 的那一串**），而且 `remove-hook` 按 event+command **逐字匹配**——用哪串装的就得用哪串删。机制、端到端验证法、回滚都在 `references/todo-panel-guard.md`。**新会话生效**（钩子不热加载），装完按**第 8 步**总验收时顺手再验一次。

### 7. 状态栏（缓存命中率 + API 余额）

footer 第一行常显**整个会话的缓存命中率**和**当前 provider 的 API 余额**（DeepSeek / Moonshot 这类有余额接口的 provider），不用每次都开 `/usage`：

```bash
cp "$SKILL_DIR/assets/statusline.py" ~/.kimi-code/
python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" \
  set status_line.command "python3 ~/.kimi-code/statusline.py"
```

- 缓存率从会话日志 `agents/main/wire.jsonl` 的 `usage.record` 累计（与 `/usage` 面板同源），余额走 provider 的余额接口、缓存 5 分钟后台刷新。显示格式：`<模式徽章>  <模型名>  cache 98%  bal ¥44.50  ~/proj main`（2026-09-16 起去掉了 `cached … · uncached …` 明细段）；kimi-code 给的上限是 300ms，超时/失败自动回落内置布局。
- **Windows 为什么不是直连 Python**（2026-09-16 实测：Windows 11 + kimi-code 0.43.1 + Store 版 Python 3.13）：`cmd.exe /d /s /c` + Python 启动 + 脚本自身 = 空闲 ≈240ms、机器忙/多开窗口 400ms+，300ms 预算站不住（runner 超时会 `taskkill /T /F` 丢弃结果，footer 就回落内置布局）。所以 Windows 改成两级结构：

  ```bash
  cp "$SKILL_DIR/assets/statusline.py" "$SKILL_DIR/assets/statusline-daemon.pyw" "$SKILL_DIR/assets/statusline-fast.c" ~/.kimi-code/
  /c/msys64/mingw64/bin/gcc.exe -O2 -static -s -o ~/.kimi-code/statusline-fast.exe ~/.kimi-code/statusline-fast.c
  python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" \
    set status_line.command "C:/Users/<你>/.kimi-code/statusline-fast.exe"
  ```

  热路径 `statusline-fast.exe`（实测 **44–73ms**）只做：快照落盘 → 打印守护进程预渲染的行 → 心跳过期时拉起守护进程；渲染、桥探活、余额刷新全在常驻的 `statusline-daemon.pyw` 里（不在 runner 进程树里，不受 `taskkill /T` 连坐）。命令必须写成**无引号的正斜杠绝对路径**（cmd 的 `/s` 会吃掉引号）。**别照搬 `py -3`**：Store 版 Python 不带 `py` 启动器。
- 判据：`verify.py` 的状态栏几项全 PASS（含脚本行为自测）；`/reload-tui` 后 footer 第一行出现 `cache N%`。Windows 上第一次 tick 可能只有快照、没有行（守护进程 1–2 秒渲染完，下一次 tick 就有）——不是坏了，过程与排错见 `references/statusline.md`。
- **Windows 上桥的兜底探活也归守护进程管**（拒连就拉活，实测 2 秒内自愈；细节见 `references/statusline.md`「已知边界」与 `references/web-tools-exa.md`）。
- 自定义行会**整体替换** footer 第一行（脚本复刻了模式徽章 / 模型名 / cwd / git 分支，另加缓存率与余额）——想回到内置槽位就注释掉 `command`。机制、排错、回滚、已知边界都在 `references/statusline.md`。

### 8. 总验收

**一条命令**（推荐，只读；覆盖清单只写在上面「assets 里有什么」的 `assets/verify.py` 一行，这里不重复枚举）：

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
| `出网不通` / `代理出口不通` | 网络 / 代理层问题，**不是 kimi-code 的错**——体检脚本会替你区分"要走代理的域名全超时但直连正常"（=代理出口挂了）和"整机没网" | 代理软件里换节点 / 更新订阅 / 确认选中了可用节点（或 TUN 开着）；恢复后重试即可，不用改配置。细节见 `references/web-tools-exa.md`「排错速查」 |
| `services.*` 缺失或指向 Kimi 托管 | 大概被 `/login` 顶掉了 | 按第 2 步用补丁脚本加回来 |
| `桥 /health 打不通` | 桥没在跑（实测会被静默杀掉：重启后没起来、或中途被杀；日志无 traceback 不代表没挂） | **先只认 `/health`**（别用 `Get-Process pythonw`——真名是 `pythonw3.13`）。**Windows 上先等 30 秒左右**：状态栏脚本的兜底最多 30 秒探活一次，拒连就拉起——**优先跑启动文件夹的 `kimi-exa-bridge.lnk`**（ShellExecute 由 explorer 起、不在我们的进程树里，runner 超时那记 `taskkill /T /F` 杀不到它），没有快捷方式才回退 `Popen`（直接拉 `launch.pyw`）；重试间隔 30 秒（实测 2 秒内自愈），`statusline/bridge-watch.json` 里能看到 `last_ok`/`relaunched`——别按 5~10 秒预期；还不行再手动救活：macOS `launchctl print gui/$(id -u)/ai.kimi.exa-bridge`；**Windows 跑一次 `kimi-exa-bridge.lnk`**（不用 `Get-ScheduledTaskInfo`，本机没建计划任务）；Linux `systemctl --user status ai.kimi.exa-bridge`。细节见 `references/web-tools-exa.md` 2.5 |
| `直打桥搜索 401` | `config.toml` 的令牌与桥的 `EXA_BRIDGE_TOKEN` 不一致 | 两边对齐，或把桥的 token 留空 |
| `两处 services.*.api_key 不一致` | `moonshot_search` 与 `moonshot_fetch` 的令牌不是同一把——**只错一处时以前查不出来**，但 FetchURL 直打桥会 401 | 两处都该等于桥的 `EXA_BRIDGE_TOKEN`：用补丁脚本 `set` 对齐（想不出令牌就两边留空） |
| `直打桥抓取 → …` 失败 | 桥的**抓取通道**坏了（Exa `contents` 报错 / key 没权限 / 额度耗尽）。这条最容易漏诊：桥对抓取失败一律回 200、把原因写进正文，CLI 会把它当正文吞掉，只有体检会直说 | 看消息里带的正文前 80 字符判断是哪类错；`/search` 正常而 `/fetch` 坏，基本是 Exa `contents` 侧的问题 |
| `常驻定义令牌 … 不一致` / `常驻定义有 CR（\r）` | 常驻定义（plist / systemd unit / launch.pyw）里的令牌与 `config.toml` 对不上；最隐蔽的一种是 **CRLF 模板 sed 出来的定义**（令牌尾部多个回车） | 重新生成定义：`sed` 前先 `tr -d '\r' < 模板 \| sed …`；细节见 `references/web-tools-exa.md`「排错速查」 |
| `桥脚本一致性 … 有漂移` / `守卫脚本一致性 … 有漂移` | skill 里的副本 ≠ 机器上在跑的 | 跑 `python3 "$SKILL_DIR/assets/deploy.py" --bridge`（按内容比对重新拷贝，并重启桥）；只想自己动手就 `cp` 过去 + 重启桥。**注意**：如果改动还停在正本、没进安装副本，先做正本→安装副本那一步同步 |
| `钩子：没有 [[hooks]]` / `没装 Todo 面板守卫` / `钩子脚本行为 … FAIL` | 第 6 步没做、规则被删、或脚本被改坏 | 按第 6 步重装（`ensure-hook` 幂等，重复跑安全）；钩子**新开会话**才生效 |
| `状态栏：` 开头的几项（tui.toml 缺 `[status_line]` / command 为空 / 脚本缺失 / 行为自测 FAIL / Windows 热路径三件套缺失） | 第 7 步没做、`tui.toml` 被还原或被 `/reload-tui` 之外的手段改回、脚本被改坏 | 按第 7 步重装（补丁脚本幂等）；**`/reload-tui` 当场生效**，不用重启会话。Windows 上若只是 footer 没行/数字冻住，先看 `~/.kimi-code/statusline/daemon.heartbeat` 与 `daemon.log`——守护进程死了热路径下一次 tick（≤5 秒）会自动拉起 |
| `状态栏脚本一致性 … 有漂移` / `状态栏守护脚本一致性 … 有漂移` | 改了 `assets/statusline.py` / `assets/statusline-daemon.pyw` 但没重新部署 | 跑 `python3 "$SKILL_DIR/assets/deploy.py"`（拷贝 + 自动重启守护进程让它加载新代码；`.c` 变过时它还会顺手重编 exe） |
| `触发链：…` WARN | skill **既不在 `~/.kimi-code/skills/`、`~/.kimi-code/AGENTS.md` 里也没有指路**——表现是「skill 突然不生效」 | 把目录拷进 `~/.kimi-code/skills/kimi-code-setup/`，或在 `AGENTS.md` 里加一条含 "kimi-code-setup" 字样的触发约定（见「这个目录放在哪、怎么用」） |
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
- **正本只保留一份**（本机的"安装副本"除外）：改动只动正本，改完按上面「放在哪」一节同步到 `~/.kimi-code/skills/kimi-code-setup/`；搬运/归档完别在别处再留第三份，前后用 `diff -rq 旧目录 新目录` 核对——`verify.py` 的「脚本漂移」只比对 **`exa-bridge.py` / `todo-panel-guard.py` / `statusline.py` / `statusline-daemon.pyw`** 这 4 个部署脚本（对应关系见上文），**不比对** `patch-config.py`、`verify.py`、`deploy.py`、`.template` 生成出的常驻定义、`statusline-fast.c` 编出的 exe、`kimi-web-status.user.js`，也不比对任何文档——所以改完部署脚本要跑一次 `assets/deploy.py`（幂等）把它们送到落地点，别靠记性。
- 正本是个 git 仓库（`origin` = 公开仓库）：动手前 `git status` 确认工作区干净，改完 `git commit` + `git push`。**别再用 `cp -a` 做目录备份**——git 就是备份，`cp -a` 只会把 `.git` / `__pycache__` 一起拷进去。
- 换了 kimi-code 版本，先跑 `verify.py`，再更新顶部那句"验证版本"。
- 改了目录名或位置，记得同步：frontmatter 的 `name`、本文件与 `references/` 里的 `$SKILL_DIR` 说明、以及作者机器上 `~/.kimi-code/AGENTS.md` 里的指路与触发约定。

## 参考：基线快照（搬配置 / 对照用）

作者机器现状、macOS / Windows / Linux 三份实测基线、kimi-cu 现状详情都搬到了 **`references/baselines.md`**——**只对照、不照抄**（key / 令牌 / 路径以你自己机器为准）：

- **Windows 11 那份是现行的**；**macOS / Linux 两份是历史快照**——加新检查之前的数字、**未复跑**，别拿来对新版 `verify.py`。
- `verify.py` 的检查项随版本增减，**项数对不上不代表配错了**。
