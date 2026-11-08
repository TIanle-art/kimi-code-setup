---
name: kimi-code-setup
description: |
  新机器上把 kimi-code 从零配到可用（macOS / Windows / Linux）：provider 与模型、内置 WebSearch/FetchURL 接自己的 Exa 或 DeepSeek Search/Fetch API（exa-bridge，没有 Exa key 时自动走 DeepSeek）、MCP、权限、AGENTS.md、Todo 守卫钩子、状态栏；也支持只读体检。触发：「调试/配置 kimi-code」「体检」、WebSearch 不能用、没有 Exa key 怎么联网、FetchURL 撞 WEB_PRIVATE_ADDRESS、exa-bridge 挂了、/login 顶掉配置。
metadata:
  version: "4.1.0"
---

# 全新 kimi-code 落地（新机器开箱配置）

**这个 skill 管的是"把一台新机器上刚下载的 kimi-code 配到能用"，不是修 bug**——排错只是收尾的一环。本文件只留主流程、判据和索引；细则在 `references/`，脚本在 `assets/`。**每一步动手前先读它指向的那份 reference**，别凭本文的摘要硬做。

> **验证版本**：主流程在 macOS / Windows 11 / Linux（WSL2）上实测过，最近一次 Windows 11 + kimi-code 2.0.0（2026-09-18）`verify.py --e2e` 全通过；DeepSeek 后端 2026-11 在 Windows 11 上实测。逐平台的版本与日期见 `references/maintainer.md`。机器上版本不同时先跑一次 `assets/verify.py`。

## 这个目录放在哪、怎么用

- **怎么触发**：拷进目标机器的 `~/.kimi-code/skills/kimi-code-setup/`（Windows：`%USERPROFILE%\.kimi-code\skills\kimi-code-setup\`）后，说「**调试 kimi-code**」「配置 kimi-code」即可；不拷也行，直接把文件带过去让 agent 读。
- 下文 **`$SKILL_DIR`** 指这个 skill 所在目录（通常就是上面那个安装路径），命令里按实际位置展开。
- **维护这个 skill**（正本 / 安装副本同步、扩展规范、各平台验证版本、assets 逐个详解）：`references/maintainer.md`。

## assets 里有什么

| 脚本 | 干什么 |
|------|--------|
| `exa-bridge.py` | 内置 WebSearch / FetchURL 的本机适配器：转调 Exa；没有 Exa key 但有 DeepSeek key 时自动改调 DeepSeek（`EXA_BRIDGE_BACKEND` 可强制）。部署到 `~/.kimi-code/exa-bridge/` |
| `launchagent.plist.template` / `systemd-user.service.template` / `windows-launch.pyw.template` | 桥的常驻定义模板（macOS / Linux / Windows），**先 `tr -d '\r'` 再 `sed`** 生成 |
| `todo-panel-guard.py` | Stop 钩子：Todo 面板全部 `done` 却没清空时拦下回合结束（第 6 步） |
| `statusline.py`（Windows 另加 `statusline-fast.c` + `statusline-daemon.pyw`） | footer 状态栏：缓存命中率 + provider 余额（第 7 步） |
| `kimi-web-status.user.js` | 浏览器用户脚本：把同样两个数字显示在 `kimi web` 页面角落 |
| `patch-config.py` | **改 `config.toml` / `tui.toml` 只用它**：幂等、保留注释、写前备份与复验；`set` / `ensure-rule` / `ensure-hook` 写，`unset` / `remove-rule` / `remove-hook` 删，`check` 只查 |
| `deploy.py` | **部署只用它**：按内容比对把部署脚本送到落地点，Windows 上按需重编 exe、重启守护进程；`--check` 只报告，`--bridge` 连桥一起重启 |
| `verify.py` | **一条命令体检**（只读，退出码 0/1/2），`--e2e` 再加一次真实端到端；结论怎么读见 `references/health-check.md` |

## 主流程

| # | 步骤 | 做完的判据 | 细则 |
|---|------|-----------|------|
| 0 | 装好 kimi-code + 摸清现状 + 备份 + 问清参数 | `kimi --version` 有输出；平台与联网后端已确定 | 本文 |
| 1 | LLM provider、模型与思考强度 | 新进程里能正常对话、思考强度符合预期 | `references/provider-model.md` |
| 2 | 内置 WebSearch / FetchURL → 自己的 Exa（或 DeepSeek） | 三层验证全过；Windows 上自启项写完要回读 | `references/web-tools-exa.md` + `references/bridge-<平台>.md` |
| 3 | exa MCP（只在有 Exa key 时） | 工具清单里出现 `mcp__exa__*` | 本文 |
| 4 | 权限模式与工具开关 | 启动就是 Ask When Needed、联网工具没被 disabled | 本文 |
| 5 | 策略文件 AGENTS.md | 模型知道何时用哪条通道；任务清单三条约定在里面 | 本文 |
| 6 | Todo 面板守卫（Stop 钩子） | `verify.py` 钩子项 PASS + 一次 `kimi -p` 实测 | `references/todo-panel-guard.md` |
| 7 | 状态栏（缓存命中率 + 余额） | `verify.py` 状态栏项 PASS；`/reload-tui` 后 footer 出现 `cache N%` | `references/statusline.md` |
| 8 | 总验收 | `verify.py` 全绿 + 一次真实端到端 | 本文 |

### 0. 装好 kimi-code + 摸清现状 + 备份 + 问清参数

没装就先装（[官方文档](https://moonshotai.github.io/kimi-code/)）：macOS / Linux `curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash`；Windows PowerShell `irm https://code.kimi.com/kimi-code/install.ps1 | iex`；macOS 也可 `brew install kimi-code`。

```bash
kimi --version
kimi provider list                      # 已配的 provider 与默认模型
ls -la ~/.kimi-code                     # 配置目录 = $KIMI_CODE_HOME，未设则 ~/.kimi-code
curl -s http://127.0.0.1:8787/health    # 有没有既存的桥：存活只认 /health（Windows 写 curl.exe）
cp ~/.kimi-code/config.toml ~/.kimi-code/config.toml.bak-$(date +%Y%m%d-%H%M%S)   # 动手前备份（mcp.json 同理）
```

**开工先问，一次问全**（交互会话优先用 `AskUserQuestion`；用户答不上来的走默认）：

| 必须问到的 | 为什么 |
|------------|--------|
| 平台：macOS、Windows 11 还是 Linux | 决定桥的常驻方式和路径写法 |
| **Exa API key 有没有** | 决定第 2、3 步走哪条路（见下） |
| LLM provider 的 API key | **仅当** `kimi provider list` 显示还没配 |

**没有 Exa key 时给三条路挑**（别卡住，也别拿别人的 key 顶上；细节与非交互 `kimi -p` 的做法见 `references/web-tools-exa.md`「收集参数」）：

- ① **去 dashboard.exa.ai 注册**（推荐）：内置通道 + exa MCP 都能建。
- ② **匿名 exa MCP 顶着**：`mcp.json` 只写 `{"url": "https://mcp.exa.ai/mcp"}`；内置 `WebSearch` / `FetchURL` 建不了，说明白别让用户以为坏了。
- ③ **改用 DeepSeek Search / Fetch API**（✅ 2026-11 Windows 11 实测）：桥照建、Exa key 留空，桥读到 `config.toml` 的 `[providers.deepseek].api_key`（或 `DEEPSEEK_API_KEY`）就自动走 DeepSeek——对话用 DeepSeek 的机器**不用再要 key**；代价是没有 exa MCP。

**默认值，不用问**：端口 `8787`；本地令牌现场生成（**别留空**，留空 `verify.py` 报 WARN）；常驻方式按平台（Windows 先试计划任务，被拒就用启动文件夹）；权限 `yolo` + 模型级 `default_effort = "max"`；状态栏默认装。**key 一律写进文件，不在回复正文里回显。**

### 1. LLM provider、模型与思考强度

```bash
kimi provider catalog add deepseek --api-key <你的 key> --default-model deepseek-flash
kimi provider list
```

目录导入只解决 provider + 模型别名；思考强度写进 `config.toml`（用 `patch-config.py set`）。**新机器的坑**：首次启动会把全局 `[thinking] effort = "max"` 一次性迁成 `high`——把 `max` 写在模型级 `[models."…".overrides].default_effort`（迁移不碰它）。完整 toml 示例与字段说明见 `references/provider-model.md`。

**`/login` 会把 `config.services` 重写成 Kimi 托管**，第 2 步的配置会被顶掉。

### 2. 内置联网工具 → 自己的 Exa（或 DeepSeek）

放脚本 → 用补丁脚本写两段 `[services.*]` → 起常驻 → 三层验证。**别手动往 `config.toml` 追加**（重复表会让整份配置失效，报错却是 `No model configured`）：

```bash
P="$SKILL_DIR/assets/patch-config.py"
python3 "$P" set services.moonshot_search.base_url http://127.0.0.1:8787/search
python3 "$P" set services.moonshot_search.api_key  "<本地令牌>"
python3 "$P" set services.moonshot_fetch.base_url  http://127.0.0.1:8787/fetch
python3 "$P" set services.moonshot_fetch.api_key   "<本地令牌>"
python3 "$P" check
```

**动手前读 `references/web-tools-exa.md`**（契约、放脚本、验证、回滚、排错），常驻那一步再读**本机平台那一份** `references/bridge-macos.md` / `bridge-windows.md` / `bridge-linux.md`。

### 3. exa MCP（只在有 Exa key 时）

`~/.kimi-code/mcp.json` **只放 exa**（改前先读现有内容，JSON 后写的键会静默覆盖前面的）：

```json
{ "mcpServers": { "exa": { "url": "https://mcp.exa.ai/mcp", "headers": { "x-api-key": "<Exa key>" } } } }
```

与内置通道同一把 key、同一份额度，能力是超集：多 URL 批量抓取、`maxCharacters`、`numResults` / `objective`、`agent_run` 多步调研。`enabled` / `startupTimeoutMs` / `toolTimeoutMs` / `enabledTools` 都可省，改完新开会话生效。**走 DeepSeek 的机器跳过这一步。**

### 4. 权限模式与工具开关

```bash
python3 "$SKILL_DIR/assets/patch-config.py" set default_permission_mode yolo
python3 "$SKILL_DIR/assets/patch-config.py" ensure-rule allow 'mcp__exa__*'    # 走 DeepSeek 的机器不用这条
```

| 配置值 | 界面名 | 行为 |
|--------|--------|------|
| `manual` | Always Ask | 只自动读文件，其它都要批准 |
| `yolo` | **Ask When Needed**（推荐） | 常规编辑和命令自动跑；风险操作、提问、计划仍会问 |
| `auto` | Never Ask | 全自动 |

临时覆盖：`kimi -y` / `kimi --auto`；会话里 `/yolo`、`/auto`、`/permission`。`[tools] disabled` 里**不要**出现 `WebSearch` / `FetchURL`（`verify.py` 的「工具开关」一项盯这个）。规则 `pattern` 是工具名或 `工具名(参数 glob)`，decision 取 `allow | deny | ask`。

### 5. 策略文件 AGENTS.md

写进 `~/.kimi-code/AGENTS.md`（kimi 还会叠加项目里的 `.kimi-code/AGENTS.md` 与 `AGENTS.md`，就近优先）。**联网分工按桥的后端二选一**（看 `/health` 的 `backend`；没有这个字段 = exa），只写一段：

**A. 后端是 Exa：**

> **默认优先内置**：普通搜索 / 抓取一律先用 `WebSearch` / `FetchURL`（打到本机 exa-bridge，固定 5 条、约 400 字符摘要，免确认）。**只有需要内置做不到的能力时**才切到 exa 的 MCP `mcp__exa__*`：一次抓多个 URL、控制 `maxCharacters`、调 `numResults`/`objective`、`agent_run` 多步调研。内置通道失效（桥挂、未起）时也切 MCP；内网地址、localhost、需登录态 cookie 的页面只能用 Bash curl。

**B. 后端是 DeepSeek：**

> **联网只用内置**：搜索 / 抓取一律用 `WebSearch` / `FetchURL`（打到本机 exa-bridge，后端是 DeepSeek Search / Fetch API，固定 5 条、约 400 字符摘要，免确认）。本机**没有** exa 的 MCP，别去找 `mcp__exa__*`；要抓多个 URL 就逐个调 `FetchURL`。内置通道失效（桥挂、未起）时先告诉用户、别硬猜；内网地址、localhost、需登录态 cookie 的页面只能用 Bash curl。

**再加任务清单约定**（第 6 步的钩子兜底的就是第 ② 条）：

> **任务清单（Todo 面板）**：① 一项一确认——每完成一项先核对结果（实测 / 查状态 / 看输出）再标 `done`，不攒到最后批量改，也不凭"看起来完成了"下判断；② 做完就清——所有项 `done` 后立即 `TodoList(todos: [])` 清空面板；③ 等用户的项——只能由用户手动完成或被外部条件卡住的项，如实留在清单里并注明「这步等你」，用户做完后下一轮先核对，再标 `done` 或整体清空。

### 6. Todo 面板守卫（Stop 钩子）

```bash
mkdir -p ~/.kimi-code/hooks && cp "$SKILL_DIR/assets/todo-panel-guard.py" ~/.kimi-code/hooks/
python3 "$SKILL_DIR/assets/patch-config.py" ensure-hook Stop "python3 ~/.kimi-code/hooks/todo-panel-guard.py" --timeout 5
# Windows：钩子由 cmd.exe 执行、~ 不展开，写正斜杠绝对路径；中文 Windows 加 -X utf8（否则提示变乱码）：
# python3 "$SKILL_DIR/assets/patch-config.py" ensure-hook Stop "python.exe -X utf8 C:/Users/<你>/.kimi-code/hooks/todo-panel-guard.py" --timeout 5
```

`remove-hook` 按 event+command **逐字匹配**，用哪串装就用哪串删。**新会话生效**（钩子不热加载）。机制（含"跨回合旧面板只拦一次"）、端到端验证、回滚见 `references/todo-panel-guard.md`。

### 7. 状态栏（缓存命中率 + 余额）

```bash
cp "$SKILL_DIR/assets/statusline.py" ~/.kimi-code/
python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" \
  set status_line.command "python3 ~/.kimi-code/statusline.py"
```

footer 第一行变成 `<模式徽章>  <模型名>  cache 98%  bal ¥44.50  ~/proj main`（余额段只在 provider 有余额接口时出现）；超过 300ms 自动回落内置布局。**Windows 不能直连 Python**（预算撑不住），改用 `statusline-fast.exe` + 守护进程两级结构，需要 MSYS2 gcc 编译一次——安装命令、原因、排错、回滚都在 `references/statusline.md`；Windows 上守护进程还顺带给桥兜底探活。

### 8. 总验收

```bash
python3 "$SKILL_DIR/assets/verify.py"          # 快速体检
python3 "$SKILL_DIR/assets/verify.py" --e2e    # 再跑一次真实端到端（20–60s）
```

退出码 `0` 全通过 / `1` 有告警 / `2` 有失败，末尾列出所有失败项；出网不通时它会把桥的失败降级成告警，别冤枉桥。**汇报**：改过哪些文件、`verify.py` 的输出、哪一步没验证（明说）。

## 体检模式（只读：不动任何文件）

用户说"看看这台机器的 kimi-code 怎么样""帮我体检一下"时走这条路，别顺手改配置：跑 `verify.py`（和 `patch-config.py check`），按 **`references/health-check.md`** 查每条 FAIL / WARN 的含义与下一步。**出网不通 / 代理出口不通是网络层问题**，不用改配置。

该体检的时机：升级 kimi-code 之后、怀疑 `/login` 动过配置、桥挂过一恢复、搬配置前后、每次改完 `config.toml`。

## 红线

- **别手动改 `config.toml` / `tui.toml`**（增、改、删都不行），只用 `patch-config.py`；也别整份覆盖——只动该动的字段，用户的其它条目和注释留着。
- **别主动跑 `/login`**：会把联网配置顶掉（用户自己要登录另说，登完复检）。
- **别把 A 机器的 key 写进 B 机器**；key 不贴进聊天正文。
- **别给桥留空令牌**；别重复追加 `mcp.json` 条目。
- **别跳步验收**：`verify.py` 没全绿不说"配好了"，没验证的项明说。

## 配置生效时机

| 改动 | 生效方式 |
|------|----------|
| `[services.*]` | 进程里只解析一次 → **退出重启 `kimi`**（`-r` 恢复会话） |
| `[tools].disabled` | 当场生效 |
| `[[hooks]]` | **新开会话**生效 |
| `mcp.json` | 通常热重载；不确定就重启 |
| `tui.toml` | `/reload-tui` 当场生效 |
| 桥的常驻定义 / 脚本 | 见对应平台的 `references/bridge-<平台>.md`；只改脚本时跑 `deploy.py --bridge` |

会话日志在 `~/.kimi-code/sessions/<工作目录 id>/session_<uuid>/agents/main/wire.jsonl`。

## 参考

- `references/baselines.md`：三平台实测基线，**只对照、不照抄**；Windows 11 那份是现行的，macOS / Linux 是历史快照，`verify.py` 项数对不上不代表配错了。
- `references/maintainer.md`：扩展这个 skill 的规范（细则放 references、本文件只留要点；写配置复用 `patch-config.py`、读复用 `verify.py`；实测与未实测分开标注；一律 LF）。
