# 状态栏：缓存命中率 + API 余额

**用途**：footer 第一行常显**整个会话的缓存命中率**和**当前 provider 的 API 余额**——不用开 `/usage` 就知道缓存省了多少、这把 key 还剩多少钱。

## 机制

- 走 `tui.toml` 的 `[status_line].command`：kimi-code 每秒最多调一次，把一份 JSON 快照从 stdin 喂给命令，**第一行 stdout 替换 footer 第一行**；超时 300ms / 退出码非 0 / 无输出 → 回落内置布局（脚本坏了不会把 footer 弄没）。
- 快照字段只有 `model / cwd / gitBranch / permissionMode / planMode / contextUsage / contextTokens / maxContextTokens / sessionId / version`——**没有** usage，缓存率得自己去会话日志里算。
- **缓存率**：扫 `~/.kimi-code/sessions/*/session_<id>/agents/main/wire.jsonl` 里全部 `usage.record` 事件，按 `inputCacheRead / (inputCacheRead + inputCacheCreation + inputOther)` 计算——与 `/usage` 面板同源，两边数字对得上。只统计主 agent，不含子 agent。
- **余额**：从 `config.toml` 找到当前模型对应的 provider，调它的余额接口（DeepSeek `/user/balance`、Moonshot `/users/me/balance`），结果缓存在 `~/.kimi-code/statusline/balance-<provider>.json`，默认 5 分钟刷新一次；网络请求丢给 detached 子进程，主路径（300ms 预算内）只读缓存文件。
- **增量**：日志按字节偏移量续读（偏移量与累计值存在 `statusline/usage-<session>.json`），单次最多花 0.15s，超大日志分几次收敛，不卡渲染。
- 显示格式：`<模式徽章>  <模型名>  cache 98%  bal ¥44.50  cached 5.8M · uncached 74.3k  ~/proj main`，缓存率按 ≥80% 绿 / ≥50% 黄 / 红着色；顺序是刻意的——窄终端截断时先保住缓存率和余额。

## 安装

```bash
cp "$SKILL_DIR/assets/statusline.py" ~/.kimi-code/
python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" \
  set status_line.command "python3 ~/.kimi-code/statusline.py"
```

- **`--file` 必须写在子命令前面**（argparse 的位置要求）：写成 `set … --file …` 会报 `unrecognized arguments`（实测踩过）。
- `patch-config.py` 对 `tui.toml` 一样幂等：`[status_line]` 存在就改 `command` 的值，不存在才追加整段；写前备份、写前复验（不通过就不落盘）。**别手写追加**。
- **Windows（2026-09-16 实测：Windows 11 + kimi-code 0.43.1 + Store 版 Python 3.13）**：脚本放 `%USERPROFILE%\.kimi-code\`，命令写 `python3 C:/Users/<你>/.kimi-code/statusline.py`——用正斜杠绝对路径，cmd.exe 与 Git Bash 都能跑（`~` 两边都不展开，`%USERPROFILE%` 只在 cmd 里展开）。**别照搬 `py -3`**：本机就没有 `py` 启动器（Store 版 Python 不带），用 `where python` / `where pythonw` 看装了哪个。
- **Windows 的 300ms 预算很紧（实测数据）**：同一份脚本，旧版直连启动 200ms、经 `cmd.exe` 244ms；把 `urllib.request` 与 `subprocess` 改成惰性导入后降到 **113ms / 156ms**——这两个模块在 Windows 上合计约 130ms。作者机器（macOS）只要 ~50ms，所以 Windows 上尤其别把重依赖放回文件顶部。超时会**静默回落内置布局**（不是报错），现象就是 footer 第一行没出现 `cache N%`。
- 生效：`/reload-tui`（只重载 tui.toml）或新开会话。`tui.toml` 写坏了 kimi-code 会回落默认布局并提示，不会起不来。

## 验证

```bash
python3 "$SKILL_DIR/assets/verify.py" | grep 状态栏     # 体检里的状态栏几项
echo '{"model":"X","cwd":"'$HOME'","permissionMode":"yolo","sessionId":"session_x"}' \
  | python3 ~/.kimi-code/statusline.py                   # 手工喂一份快照看输出（macOS / Linux / Git Bash）

# Windows（PowerShell：绝对路径 + python，`~` 不展开）：
# '{"model":"X","cwd":"C:/Users/<你>","permissionMode":"yolo","sessionId":"session_x"}' | python C:/Users/<你>/.kimi-code/statusline.py
```

`verify.py` 的「状态栏脚本行为」用临时 `KIMI_CODE_HOME` + 假会话日志（read 900 / uncached 100）跑一次，期望输出含 `cache 90%`（不联网）。

## web 端（kimi web）也能看

`kimi web` 是浏览器 UI：`tui.toml` 的 `[status_line]` 管不到它，它的 CSP（`default-src 'self'`）也让页面自己连不到 8787 的桥。所以做法是「用户脚本 + 桥端点」：

- 桥（`assets/exa-bridge.py`）带 `GET /status`（只读，返回 `cache`/`balance`；不带 CORS 头、只认本机 Host）和 `GET /panel`（自包含小页面）。
- 浏览器里装一个用户脚本，把两个数字显示在页面角落。

**装一次（约 1 分钟）**：

1. 浏览器装 Tampermonkey / Violentmonkey；
2. 新建脚本，把 `$SKILL_DIR/assets/kimi-web-status.user.js` 的内容整段粘贴、保存；
3. 打开 `kimi web`，页面右下角出现小徽标（首次会弹一次 `@connect 127.0.0.1` 授权，允许即可）。

徽标可拖动（位置记在 localStorage）、点一下折叠/展开明细行；桥停了它自动隐藏，不干扰页面。

**不想装扩展的退路**：浏览器直接开 `http://127.0.0.1:8787/panel`——自包含小页面，5 秒刷新同样的数字，开个小窗口挂在角落即可。

**注意**：

- 数据来自桥的 `/status`：桥还是旧脚本（没有这个端点）时什么都没有——`verify.py` 的「桥 /status」一项会 WARN，按提示部署 `assets/exa-bridge.py` 并重启桥。
- 桥端口改过的话，把用户脚本顶部的 `BRIDGE_URL` 一起改。
- skill 更新后用户脚本不会自动跟随，要重新粘贴一次。

## 排错

| 现象 | 原因 / 处理 |
|------|-------------|
| footer 第一行还是内置布局 | 没 `/reload-tui`；或 `command` 没写进 tui.toml（`verify.py` 会报）；或脚本超时/报错——回落是设计行为，不是 bug |
| 只有模型名，没有 `cache N%` | 当前会话还没有 `usage.record`（刚开、还没发过消息），或快照里的 sessionId 定位不到日志 |
| 有 `cache`，没有 `bal …` | provider 没有余额接口（Kimi 托管账号就是这种情况）；或首次抓取还没回来（等约 10s）；带 `(stale)` 表示最近一次刷新失败，显示的是旧值 |
| 余额一直是 `(stale)` | 出网 / 代理层问题——`verify.py` 的出网项会同时报，先去查网络 |
| 数字和 `/usage` 对不上 | 两者口径相同（都从 `wire.jsonl` 的 `usage.record` 累计）；差一点通常是读取时刻不同 |

## 已知边界

- 自定义行**整体替换** footer 第一行：脚本自己复刻了模式徽章、模型名、cwd、git 分支，但**没有** git 脏标记 / PR 徽章，也没有轮换 tips。
- 缓存率是**会话累计**（含 `usage.record` 的所有轮次），不是"最近一次请求"。
- Kimi 托管账号（`/login`）走 `/usages` 配额接口、需要 OAuth 凭据，本脚本**不接**——那种机器上余额段自动消失，缓存率不受影响。
- 本机实测（kimi-code 0.41.0，2026-09-15，macOS）：footer 渲染正常（另起临时实例截屏确认）、余额 ¥44.50 正常、脚本热路径 44ms（预算 300ms）。
- Linux 实测（WSL2 + kimi-code 0.41.0 + Python 3.14，2026-09-16）：脚本行为自测通过（`cache 90%`）；真机负载下全程 **26–31 ms**（spawn→出结果，6 次取样，预算 300ms），真实余额渲染正常（`bal ¥33.06`）；**footer 那一行没在 TUI 里肉眼复核**（只验到脚本层）。桥的存活由 systemd `Restart=always` 兜（`kill -9` 后几秒自动拉起），用不上 Windows 那条探活自愈。
- Windows 实测（kimi-code 0.43.1 + Store 版 Python 3.13，2026-09-16）：脚本输出正确（`cache 95%`、余额走 DeepSeek `/user/balance` 拿到 ¥39.25），后台刷新子进程正常；耗时直连 200ms → 惰性导入后 **113ms**，经 `cmd.exe` 244ms → **156ms**。
- **Windows footer 渲染（2026-09-16 截屏复核，同一台）**：footer 第一行确实渲染出 `… cache 97%  bal ¥38.16  cached 8.4M · uncached 223k  ~`，数字逐秒更新——这条以前写的是"没在这一台复核"，现在补上了。链路构成（本机实测）：`cmd.exe /d /s /c` + Store 版 Python 启动常态 ≈115ms、机器忙时能顶到 ≈165ms，脚本自身 ≈40ms（import 12.5 + `load_config` 14.6 + usage 扫描 6.3 + 组行 3~10）——常态合计 ≈156ms（与上面那条对得上），忙时逼近 200ms、300ms 预算只剩三成余量。
- **超时是静默的，且跟机器忙不忙强相关**：runner 的 300ms 从 spawn 起算，超时就 `taskkill /T /F` 丢掉这次结果、回落内置布局，下一次成功再切回来——所以"footer 一直没出现 `cache N%`"时要先看当时机器是不是在跑重活（大量并行子进程会把 165ms 的启动开销顶过 300ms），别只怀疑脚本。想确认 TUI 到底有没有在调，可以在命令外面套一层探针脚本记录调用时刻（**实测 1 次/秒**）；runner 会给子进程注入 `KIMI_CODE_STATUS_LINE=1`，用它区分"runner 在调"和"别的东西在调"。
- **Windows 附加职责：顺手给 exa-bridge 兜底（2026-09-16 加的，已实测自愈）**。桥被杀过两次（见 `references/web-tools-exa.md` 2.5），而启动文件夹的自启不会拉活（macOS 的 launchd / Linux 的 systemd 都会），所以让这条一秒一次的命令顺手探活：只做 TCP `connect`（**不发请求、不读响应**），30 秒最多一次；拒连就拉起——**优先走启动文件夹快捷方式**（ShellExecute 由 explorer 起、不在我们的进程树里，runner 超时那记 `taskkill /T /F` 杀不到它；没有快捷方式才退回直接 `Popen` launch.pyw，实测 34ms），重试间隔 30 秒（与探活同频；原来是 60 秒冷却，被连坐时桥要多躺 30~90 秒），且**先落盘再拉起**（拉起可能被 runner 的 300ms 超时打断，时间戳写不进去就会变成每秒重试）。**门闩是 `KIMI_CODE_STATUS_LINE=1`**——只有 runner 调用时才生效，`verify.py` 的行为自测、手工调试都不会误拉起（已用隔离测试验过门闩/节流/冷却/落盘四件事）。开销：桥在跑时每次调用多 ~1ms；桥挂着时多 ~50ms（本机连本机拒连端口实测是 `TimeoutError` 而不是 refused），都远在 300ms 预算内。边界：**只在 kimi 会话活着时有效**——关掉 kimi 就没有守护，而那正是搜索用不上的时候。
- **Windows 侧三处加固（2026-09-16，按标准做法写）**：① 兜底拉起改走 ShellExecute 以躲开 `taskkill /T` 连坐——**未在 Windows 上复测**；② 余额刷新子进程同样会被那记 taskkill 带走（`start_new_session` 在 Windows 是空转），修法是不再把"尝试过"当权威：`amount` 没写回就按 60 秒短重试，本机用假状态文件做过 A/B（旧版继续等 300 秒 → 新版立刻重试）；③ `sys.stdout` 钉死 UTF-8——cp936 / cp932 / cp1251 上 `¥` 编不出来会让整行被丢弃、退出码非 0，本机用 `PYTHONIOENCODING` 复现并验过修复。

## 回滚

- 只关掉：把 `tui.toml` 里 `[status_line]` 的 `command` 注释掉（下面一行 `items = [...]` 是内置槽位写法）。
- 彻底删：用补丁脚本删掉 `command`（同表还有 `items = [...]` 时只删 command，表空了会连表头一起删），再删脚本与缓存目录：

  ```bash
  python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" unset status_line.command
  rm ~/.kimi-code/statusline.py
  rm -rf ~/.kimi-code/statusline/
  ```
