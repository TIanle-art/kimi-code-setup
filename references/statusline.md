# 状态栏：缓存命中率 + API 余额

**用途**：footer 第一行常显**整个会话的缓存命中率**和**当前 provider 的 API 余额**——不用开 `/usage` 就知道缓存省了多少、这把 key 还剩多少钱。

## 机制

- 走 `tui.toml` 的 `[status_line].command`：kimi-code 每秒最多调一次，把一份 JSON 快照从 stdin 喂给命令，**第一行 stdout 替换 footer 第一行**；超时 300ms / 退出码非 0 / 无输出 → 回落内置布局（脚本坏了不会把 footer 弄没）。
- 快照字段只有 `model / cwd / gitBranch / permissionMode / planMode / contextUsage / contextTokens / maxContextTokens / sessionId / version`——**没有** usage，缓存率得自己去会话日志里算。
- **缓存率**：扫 `~/.kimi-code/sessions/*/session_<id>/agents/main/wire.jsonl` 里全部 `usage.record` 事件，按 `inputCacheRead / (inputCacheRead + inputCacheCreation + inputOther)` 计算——与 `/usage` 面板同源，两边数字对得上。只统计主 agent，不含子 agent。
- **余额**：从 `config.toml` 找到当前模型对应的 provider，调它的余额接口（DeepSeek `/user/balance`、Moonshot `/users/me/balance`），结果缓存在 `~/.kimi-code/statusline/balance-<provider>.json`，默认 5 分钟刷新一次；主路径只读缓存文件，真实请求交给后台子进程。
- **增量**：日志按字节偏移量续读（偏移量与累计值存在 `statusline/usage-<session>.json`），单次最多花 0.15s，超大日志分几次收敛，不卡渲染。
- 显示格式：`<模式徽章>  <模型名>  cache 98%  bal ¥44.50  ~/proj main`，缓存率按 ≥80% 绿 / ≥50% 黄 / 红着色；顺序是刻意的——窄终端截断时先保住缓存率和余额。（2026-09-16 起去掉了 `cached … · uncached …` 明细段。）

### Windows：热路径 + 守护进程（2026-09-16 起）

本机实测（Windows 11 + kimi-code 0.43.1 + Store 版 Python 3.13）：`cmd.exe /d /s /c` + Python 启动 + 脚本自身，空闲 ≈240ms、机器忙时 400ms+——300ms 预算站不住，runner 超时会 `taskkill /T /F` 丢弃结果、footer 回落内置布局。所以 Windows 拆成两级，**热路径不启动任何解释器**：

| 角色 | 文件 | 干什么 | 实测 |
|------|------|--------|------|
| 热路径 | `statusline-fast.exe`（源码 `assets/statusline-fast.c`，`gcc -O2 -static -s` 编译；19KB，只依赖 KERNEL32/msvcrt） | 读 stdin 快照 → 按「会话键」写 `statusline/payload_<键>.json`；把 `statusline/line_<键>.txt` 原样打到 stdout；心跳过期（>5 秒）时用 `CreateProcess`（`bInheritHandles=FALSE` + `DETACHED_PROCESS`，不拖住 runner 的管道）拉起守护进程 | **44–73ms**（runner 复刻 12 连测全过） |
| 守护进程 | `statusline-daemon.pyw`（常驻 pythonw） | 读 `payload_*.json`，调 `statusline.py` 的 `build_line()` 渲染成 `line_<键>.txt`；顺带做 exa-bridge 探活与余额刷新（不在 runner 进程树里，不受那记 `taskkill /T` 连坐）；空闲 1 小时自动退出，下一次 tick 由热路径自动拉起 | 约 1% CPU |

- **会话键 = 当前工作目录的叶子名**：两个窗口在不同目录就各渲染各行、互不干扰；同一目录开两个会话会共用一行（后写的生效）——已知取舍。
- 状态文件都在 `~/.kimi-code/statusline/`：`payload_<键>.json`（快照）、`line_<键>.txt`（预渲染行）、`daemon.heartbeat`（心跳，>5 秒判定守护进程已死）、`daemon.lock`（单实例锁）、`daemon.log`（启动/异常记录）。
- 热路径的第一次 tick 通常只有 payload、没有行（守护进程还没渲染完）；1–2 秒后的 tick 就有行了，footer 不显示只是慢一拍，不是坏了。
- macOS / Linux 保持原样（直接 `python3 statusline.py`，本机启动只要 26–50ms，用不上这条）。

## 安装

**macOS / Linux**（直连 Python，本机启动 26–50ms，够用）：

```bash
cp "$SKILL_DIR/assets/statusline.py" ~/.kimi-code/
python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" \
  set status_line.command "python3 ~/.kimi-code/statusline.py"
```

**Windows**（2026-09-16 起走「热路径 + 守护进程」，见上文机制那一节）：

```bash
cp "$SKILL_DIR/assets/statusline.py"         ~/.kimi-code/
cp "$SKILL_DIR/assets/statusline-daemon.pyw" ~/.kimi-code/
cp "$SKILL_DIR/assets/statusline-fast.c"     ~/.kimi-code/
/c/msys64/mingw64/bin/gcc.exe -O2 -static -s -o ~/.kimi-code/statusline-fast.exe ~/.kimi-code/statusline-fast.c
python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" \
  set status_line.command "C:/Users/<你>/.kimi-code/statusline-fast.exe"
```

- **命令必须是「无引号的正斜杠绝对路径」**：runner 走 `cmd.exe /d /s /c <command>`，带引号的路径会被 `/s` 的引号处理搞坏（实测报 `'"C:\...\pythonw.exe"' is not recognized`）。
- gcc 来自 MSYS2（`C:\msys64\mingw64\bin\gcc.exe`）；`-static` 保证 exe 不依赖 MSYS2 的 DLL。改过 `.c` 要重新编译；改 `statusline.py` / `statusline-daemon.pyw` 后杀掉 pythonw 让守护进程重启（下一次 tick 自动拉起），不用动 tui.toml。
- 双窗口各开一次也没问题：会话键按 cwd 分文件。
- **`--file` 必须写在子命令前面**（argparse 的位置要求）：写成 `set … --file …` 会报 `unrecognized arguments`（实测踩过）。
- `patch-config.py` 对 `tui.toml` 一样幂等：`[status_line]` 存在就改 `command` 的值，不存在才追加整段；写前备份、写前复验（不通过就不落盘）。**别手写追加**。
- **为什么 Windows 不再直连 Python（实测数据）**：`cmd.exe /d /s /c` + Store 版 Python 启动 + 脚本自身 = 空闲 ≈240ms、机器忙时 400ms+；而预算是 300ms——超时会**静默回落内置布局**。历史上做过惰性导入优化（244ms → 156ms，urllib/subprocess 约 130ms 启动成本），但机器一忙/多开几个窗口就重新顶穿，所以改走上面的两级结构。**别照搬 `py -3`**：Store 版 Python 不带 `py` 启动器。
- 生效：`/reload-tui`（只重载 tui.toml）或新开会话。`tui.toml` 写坏了 kimi-code 会回落默认布局并提示，不会起不来。

## 验证

```bash
python3 "$SKILL_DIR/assets/verify.py" | grep 状态栏     # 体检里的状态栏几项

# 手工喂一份快照看输出（macOS / Linux / Git Bash）：
echo '{"model":"X","cwd":"'$HOME'","permissionMode":"yolo","sessionId":"session_x"}' \
  | python3 ~/.kimi-code/statusline.py

# Windows：跑一次热路径（cwd 决定会话键；第一次可能只落 payload、不打印行，1~2 秒后再跑就有行）
cd C:/Users/<你>/Desktop/wsl2
echo '{"model":"X","cwd":"C:/Users/<你>/Desktop/wsl2","permissionMode":"yolo","sessionId":"session_x"}' \
  | C:/Users/<你>/.kimi-code/statusline-fast.exe

# 守护进程活着没：心跳应该是最近几秒内；日志里能看到 daemon start
ls -la ~/.kimi-code/statusline/daemon.heartbeat
tail -3 ~/.kimi-code/statusline/daemon.log
```

`verify.py` 的「状态栏脚本行为」用临时 `KIMI_CODE_HOME` + 假会话日志（read 900 / uncached 100）跑一次，期望输出含 `cache 90%`（不联网）；「状态栏脚本一致性」另外比对 `statusline.py` 与 `statusline-daemon.pyw` 两份部署文件。

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
- skill 更新后用户脚本不会自动跟随，要重新粘贴一次。**2026-09-16** 起状态行里没有 `cached …` 明细段了，用户脚本的明细行改成直接显示整行——旧脚本也只会退回同样的行为，所以不重贴不算坏，想跟上就重贴一次。

## 排错

| 现象 | 原因 / 处理 |
|------|-------------|
| footer 第一行还是内置布局 | 没 `/reload-tui`；或 `command` 没写进 tui.toml（`verify.py` 会报）；或脚本超时/报错——回落是设计行为，不是 bug |
| 只有模型名，没有 `cache N%` | 当前会话还没有 `usage.record`（刚开、还没发过消息），或快照里的 sessionId 定位不到日志 |
| 有 `cache`，没有 `bal …` | provider 没有余额接口（Kimi 托管账号就是这种情况）；或首次抓取还没回来（等约 10s）；带 `(stale)` 表示最近一次刷新失败，显示的是旧值 |
| 余额一直是 `(stale)` | 出网 / 代理层问题——`verify.py` 的出网项会同时报，先去查网络 |
| 数字和 `/usage` 对不上 | 两者口径相同（都从 `wire.jsonl` 的 `usage.record` 累计）；差一点通常是读取时刻不同 |
| **Windows：footer 刚开始没有行** | 正常慢一拍：第一次 tick 只落 payload，守护进程渲染完（1–2 秒）下一次 tick 就有行了 |
| **Windows：行一直不出现 / 数字冻住** | 看 `~/.kimi-code/statusline/`：`line_<键>.txt` 在不在、`daemon.heartbeat` 是不是最近几秒。守护进程死了热路径下一次 tick（≤5 秒）会自动拉起；想立刻验证就 `pythonw C:/Users/<你>/.kimi-code/statusline-daemon.pyw` 手动前台跑一次看报错，日志在 `daemon.log` |
| **两个窗口显示同一行** | 两个会话的 cwd 是同一个目录（会话键相同，后渲染的覆盖）——已知取舍，换个目录开就分开了 |

## 已知边界

- 自定义行**整体替换** footer 第一行：脚本自己复刻了模式徽章、模型名、cwd、git 分支，但**没有** git 脏标记 / PR 徽章，也没有轮换 tips。
- 缓存率是**会话累计**（含 `usage.record` 的所有轮次），不是"最近一次请求"。
- Kimi 托管账号（`/login`）走 `/usages` 配额接口、需要 OAuth 凭据，本脚本**不接**——那种机器上余额段自动消失，缓存率不受影响。
- 本机实测（kimi-code 0.41.0，2026-09-15，macOS）：footer 渲染正常（另起临时实例截屏确认）、余额 ¥44.50 正常、脚本热路径 44ms（预算 300ms）。
- Linux 实测（WSL2 + kimi-code 0.41.0 + Python 3.14，2026-09-16）：脚本行为自测通过（`cache 90%`）；真机负载下全程 **26–31 ms**（spawn→出结果，6 次取样，预算 300ms），真实余额渲染正常（`bal ¥33.06`）；**footer 那一行没在 TUI 里肉眼复核**（只验到脚本层）。桥的存活由 systemd `Restart=always` 兜（`kill -9` 后几秒自动拉起），用不上 Windows 那条探活自愈。
- Windows 实测（kimi-code 0.43.1 + Store 版 Python 3.13，2026-09-16）：脚本输出正确（`cache 95%`、余额走 DeepSeek `/user/balance` 拿到 ¥39.25），后台刷新子进程正常；耗时直连 200ms → 惰性导入后 **113ms**，经 `cmd.exe` 244ms → **156ms**。
- **Windows 的结论（2026-09-16 复测后改版）**：`cmd.exe /d /s /c` + Store 版 Python + 脚本自身，空闲 ≈240ms、机器忙/多开窗口时 400ms+，300ms 预算站不住——探针实测 runner 每秒都在调、脚本每次都跑完，但结果被超时那记 `taskkill /T /F` 丢掉，footer 就一直回落内置布局（表现为"时好时坏、忙时完全不显示"）。所以改成「热路径 `statusline-fast.exe` + 守护进程 `statusline-daemon.pyw`」（见上文机制），热路径实测 **44–73ms**，runner 完整复刻 12 连测全部落在预算内。**重建前提**：机器上有 MSYS2 gcc（`C:\msys64\mingw64\bin\gcc.exe`）；exe 是本机编译产物，仓库里只放 `.c` 源码、不放二进制。
- **超时是静默的，且跟机器忙不忙强相关**：runner 的 300ms 从 spawn 起算，超时就 `taskkill /T /F` 丢掉这次结果、回落内置布局，下一次成功再切回来——macOS / Linux 上仍要把脚本保持轻量。想确认 TUI 到底有没有在调，可以在命令外面套一层探针脚本记录调用时刻（**实测 1 次/秒**）；runner 会给子进程注入 `KIMI_CODE_STATUS_LINE=1`，用它区分"runner 在调"和"别的东西在调"。
- **Windows 附加职责：顺手给 exa-bridge 兜底（已实测自愈）**。桥被杀过两次（见 `references/web-tools-exa.md` 2.5），而启动文件夹的自启不会拉活（macOS 的 launchd / Linux 的 systemd 都会），所以让一秒一次的探活顺手做掉：只做 TCP `connect`（**不发请求、不读响应**），30 秒最多一次；拒连就拉起——**优先走启动文件夹快捷方式**（ShellExecute 由 explorer 起、不在我们的进程树里，`taskkill /T /F` 杀不到；没有快捷方式才退回直接 `Popen` launch.pyw），重试间隔 30 秒，且**先落盘再拉起**。改版后**这个探活在守护进程里做**（`statusline-daemon.pyw` 每秒循环里调 `statusline.watch_bridge()`，并自己把 `KIMI_CODE_STATUS_LINE=1` 设上以通过门闩；`verify.py` 的行为自测、手工调试仍然不会误触发）。边界：守护进程空闲 1 小时会退出，那段时间没有桥的守护；热路径下次 tick 会把它拉回来。
- **Windows 侧三处加固（2026-09-16，按标准做法写）**：① 兜底拉起改走 ShellExecute 以躲开 `taskkill /T` 连坐——**未在 Windows 上复测**；② 余额刷新子进程曾被那记 taskkill 连坐（`start_new_session` 在 Windows 是空转），当时的修法是不再把"尝试过"当权威、`amount` 没写回就按 60 秒短重试——**改版后守护进程不在 runner 进程树里，这个坑自然消失**（脚本里的短重试逻辑保留，macOS / Linux 上仍走同步模式）；③ `sys.stdout` 钉死 UTF-8——cp936 / cp932 / cp1251 上 `¥` 编不出来会让整行被丢弃、退出码非 0，本机用 `PYTHONIOENCODING` 复现并验过修复。
- 2026-09-16 起显示格式去掉了 `cached … · uncached …` 明细段（只留 `cache N%` + `bal ¥xx` + 位置），`format_tokens` / `token_detail` 一并删掉。

## 回滚

- 只关掉：把 `tui.toml` 里 `[status_line]` 的 `command` 注释掉（下面一行 `items = [...]` 是内置槽位写法）。
- Windows 退回同步 Python 模式（能用但不稳，机器闲时 240ms 内会显示）：

  ```bash
  python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" \
    set status_line.command "python3 C:/Users/<你>/.kimi-code/statusline.py"
  # 再 /reload-tui；守护进程不用管，空闲 1 小时会自己退出（或直接 taskkill pythonw3.13）
  ```
- 彻底删：用补丁脚本删掉 `command`（同表还有 `items = [...]` 时只删 command，表空了会连表头一起删），再删脚本与缓存目录：

  ```bash
  python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" unset status_line.command
  rm ~/.kimi-code/statusline.py ~/.kimi-code/statusline-daemon.pyw ~/.kimi-code/statusline-fast.c ~/.kimi-code/statusline-fast.exe
  rm -rf ~/.kimi-code/statusline/
  ```
