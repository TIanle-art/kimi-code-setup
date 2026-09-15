# 基线快照：作者机器现状 + 三平台实测（搬配置 / 对照用）

**用途**：把新机器配好后和这里对照，判断"哪里和作者机器不一样"。**只对照，不照抄**——key / 令牌 / 路径都以你自己机器上的为准。

**读哪份**（三份以前互相矛盾，现在按下表认）：

| 基线 | 状态 |
|------|------|
| Windows 11（2026-09-16 实测） | **现行**——作者眼下在用的机器 |
| macOS（2026-09-15 实测） | ⚠️ **历史快照**：加新检查之前的数字，**未复跑** |
| Linux / WSL2（2026-09-16 实测） | ⚠️ **历史快照**：加新检查之前的数字，**未复跑** |

检查项清单与判据看 `SKILL.md`「assets 里有什么」的 `verify.py` 一行；`verify.py` 的检查项会随版本增减，**项数对不上不代表配错了**。

## 作者机器现状（macOS，搬配置 / 对照用）

- `~/.kimi-code/config.toml`：`default_model = "deepseek/deepseek-flash"`（DeepSeek V4.1 Flash）、`default_permission_mode = "yolo"`（Ask When Needed）、`[thinking] effort = "max"` 与该模型的 `default_effort = "max"`、`[services.*]` 指向本机 exa-bridge、`[[permission.rules]]` 放行 `mcp__exa__*`、`[[hooks]]` 一条 `Stop` 钩子指向 `~/.kimi-code/hooks/todo-panel-guard.py`（`timeout = 5`）。
- `mcp.json`：只有 `exa`（computer-use 走官方插件，**不写进 `mcp.json`**）；`AGENTS.md`：联网工具分工 + 任务清单三条约定 + 本 skill 的触发约定。
- 常驻：macOS LaunchAgent `ai.kimi.exa-bridge`；脚本 `~/.kimi-code/exa-bridge/exa-bridge.py`（除 `/search`、`/fetch` 外还带只读的 `/status` 与 `/panel`，供 kimi web 端小面板用），日志同目录 `bridge.log`，本地令牌写在 `config.toml` 的两处 `[services.*].api_key` 里。
- 面板守卫：`~/.kimi-code/hooks/todo-panel-guard.py`（与本目录 `assets/` 副本逐字节一致；要核对就跑 `verify.py` 的「守卫脚本一致性」一项，别依赖写死的哈希——行尾一变哈希就全废）；端到端实测过——`kimi -p` 故意留一个全 done 面板，被钩子拦回、模型随后自行清空。
- 状态栏：`~/.kimi-code/statusline.py`（与本目录 `assets/` 副本逐字节一致，同样看 `verify.py` 的「状态栏脚本一致性」）+ `tui.toml` 的 `[status_line].command = "python3 ~/.kimi-code/statusline.py"`；端到端实测过——另起一个临时实例截屏，footer 第一行渲染出 `… cache 98%  bal ¥44.50 …`。

## macOS 实测基线（2026-09-15，kimi-code 0.41.0）—— ⚠️ 历史快照

- `verify.py` **34 项通过 / 0 告警 / 0 失败**（当时网络是通的）。**注意：这是加「常驻定义令牌」等新检查之前的数字，未复跑**——同一套脚本在 macOS / Windows 上会比 Linux 多 2 项 kimi-cu 的 PASS（当时预计 36 / `--e2e` 38），没有在实机复跑过。代理出口挂掉时唯一失败项会是"出网不通"，属网络层，与配置无关。

## Windows 11 实测基线（2026-09-16，kimi-code 0.43.1，Store 版 Python 3.13，非管理员账户）—— ✅ 现行

- `verify.py`（2026-09-16 复跑，本机 kimi-code 0.43.1）：**39 项通过 / 0 项告警 / 0 失败**；`--e2e` **41 项通过 / 0 项告警 / 0 失败**（真实搜索走桥成功，`bridge.log` 10268 → 12022 字节）。**「脚本漂移」几项会随正本更新而复现**：skill 副本一改、机器上还跑着旧版，它们就各报一条告警（跑一条 `python3 assets/deploy.py` 就归零）。本轮变更：状态栏改走「热路径 `statusline-fast.exe` + 守护进程 `statusline-daemon.pyw`」（体检新增「command 走热路径时三件套齐全」与「状态栏守护脚本一致性」两项检查）；状态行去掉 `cached … · uncached …` 明细段（`format_tokens` / `token_detail` 一并删除）。
- 工具清单项是"最近 3 个会话快照的并集"，因为 `kimi -p` 有时在 MCP 握手前就拍快照。
- `config.toml` / `tui.toml`：字段与 macOS 完全一致（`yolo`、`[thinking] effort = "max"`、`[services.*]` 指本机桥、`[[permission.rules]]` 放行 `mcp__exa__*`），另加 `[status_line].command = "C:/Users/<你>/.kimi-code/statusline-fast.exe"`（Windows 热路径）。
- 钩子命令写成 `python3 C:/Users/<你>/.kimi-code/hooks/todo-panel-guard.py`（**实测 kimi 用 `cmd.exe` 执行钩子命令**，`%USERPROFILE%` 也会展开；但 Store 版 Python 没有 `py` 启动器，别写 `py -3`）。**状态栏不再直连 Python**：本机实测同步跑 Python 空闲 ≈240ms、忙时 400ms+，300ms 预算站不住（runner 超时即 `taskkill /T /F` 丢结果）；改走热路径 exe（**44–73ms**，runner 复刻 12 连测全过）+ 守护进程，详见 `references/statusline.md`。
- 常驻：启动文件夹快捷方式 `kimi-exa-bridge.lnk` → `pythonw.exe "%USERPROFILE%\.kimi-code\exa-bridge\launch.pyw"`（计划任务被非管理员权限拒、`HKCU\...\Run` 被火绒回滚，见 `references/web-tools-exa.md`）。桥日志照常落在 `%USERPROFILE%\.kimi-code\exa-bridge\bridge.log`。
- kimi-cu（computer-use）：**全部走官方下载**——Windows 侧是官方 runtime（`setup_windows.ps1` → `%LOCALAPPDATA%\KimiCU\`）+ 官方插件（`/plugins install …/kimi-cu-win-plugin.zip`；2026-09-16 实机切换完成，v0.2.17 落在 `~/.kimi-code/plugins/managed/kimi-cu-win/`，`plugins/installed.json` 记 `enabled: true`）；kimi-code 自己内置了这个能力的安装器（`kimiCu.ts`），会顺手**移除旧的 `mcp.json` 手写注册**。插件自带 MCP 声明 `mcpServers.win`（`cmd.exe` + `bin\kimi-cu-mcp.cmd`，cwd 是插件根，13 个 enabledTools），所以**工具名是 `mcp__plugin-kimi-cu-win_win__*`**，不再是 `mcp__kimi-cu__*`；`mcp.json` 里**已无** kimi-cu 条目。**两条路互斥**（并存＝两个实例抢键鼠）：`verify.py` 的 MCP 检查专门拦这一条（实测会报 FAIL），切换顺序是「先装插件 → 再删手写条目 → 最后 `/reload` 或新开会话」。

## Linux 实测基线（2026-09-16，WSL2 + kimi-code 0.41.0，Python 3.14.7，非 root）—— ⚠️ 历史快照

- `verify.py`：**34 项通过 / 0 告警 / 0 失败**；`--e2e` 36 项全过（真实搜索走桥成功、`bridge.log` 同步增长）。**这是加新检查之前的数字，未复跑**。kimi-cu 那两项在 Linux 上降级成 `INFO`——没有官方路径，不该算告警。
- `config.toml` / `tui.toml`：字段与 macOS 完全一致（`yolo`、`[thinking] effort = "max"` + 模型级 `default_effort = "max"`、`[services.*]` 指本机桥、`[[permission.rules]]` 放行 `mcp__exa__*`、`[status_line].command`）。
- 常驻：systemd 用户单元 `ai.kimi.exa-bridge`（`~/.config/systemd/user/`，`enable --now`；软链落在 `default.target.wants/`）。`loginctl enable-linger "$USER"` 在 WSL2 上**免提权**通过；`kill -9` 桥后 `Restart=always` 几秒内拉起（新 PID + `/health` 恢复）。
- 钩子 / 状态栏命令都写成 `python3 ~/.kimi-code/hooks/todo-panel-guard.py` / `python3 ~/.kimi-code/statusline.py`（与 macOS 相同；`~` 由 shell 展开，实测可用）。
- **CRLF 坑（本机实测踩到，已修）**：从 Windows 侧打包出来的工作区是 CRLF，`sed` 生成的 systemd unit 每行结尾带 `\r` → `EXA_BRIDGE_TOKEN` 尾部多一个回车，与 `config.toml` 里的值对不上（当时 `patch-config.py` 的复验拦下了没落盘，但没修之前一直是个雷）。现在的五道防线：整仓转 LF + `.gitattributes`（`* text=auto eol=lf`）+ 文档里 `sed` 前一律先 `tr -d '\r'` + `patch-config.py` 当场拒绝控制字符 + `verify.py` 新增「常驻定义令牌」比对（连 `\r` 都认得出来）。
- 端到端：Todo 守卫用 `kimi -p` 实测——故意留一个全 `done` 的面板，被钩子拦回、模型随后自行清空。
- kimi-cu：**Linux 上不装**（官方没有 Linux 包，2026-09-16 与用户确认的约定；见 `SKILL.md` 第 3 步与 `references/computer-use.md`）。
