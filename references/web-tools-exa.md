# 内置联网工具（WebSearch / FetchURL）→ 自己的 Exa 账号

> 主流程第 2 步的细则。目标：kimi-code 的 `WebSearch` / `FetchURL` 不再走 Kimi 托管服务，而是记在**你自己的 exa.ai 额度**上，工具名不变。
>
> 下文 **`$SKILL_DIR`** = 这个 skill 所在目录（本机有正本 `~/Desktop/kimi-code-setup` 与安装副本 `~/.kimi-code/skills/kimi-code-setup`，内容一致、用哪份都行；在目标机器上是 `~/.kimi-code/skills/kimi-code-setup`，Windows `%USERPROFILE%\.kimi-code\skills\kimi-code-setup`）。

## 为什么不直连

`WebSearch` / `FetchURL` 是 CLI **内置**工具，端点由 `config.toml` 的 `[services.*]` 决定：

- 默认指向 Kimi 托管服务（登录账号走会员额度，未登录/未配置时不可用）；
- 本方案把端点改成本机适配器 `exa-bridge`，由它用你的 Exa key 调 `api.exa.ai`；
- **与模型供应商无关**——接了 DeepSeek 也是这套配置。

```
kimi-code 内置工具          本机适配器                      云端
WebSearch ──POST /search──► exa-bridge 127.0.0.1:8787 ──► api.exa.ai /search
FetchURL  ──POST /fetch ──►   （纯标准库 Python）      ──► api.exa.ai /contents
```

## 契约（改脚本时照这个写）

| 方向 | 请求 | 期望响应 |
|------|------|----------|
| 搜索 | `POST {base_url}` body `{"text_query": "..."}` | `200` + `{"search_results":[{"title","url","snippet","date?","site_name?"}]}`；非 200 会被报成错误（401 会提示 auth/unauthorized） |
| 抓取 | `POST {base_url}` body `{"url": "..."}` | `200` + 页面正文（文本/Markdown 皆可） |

三个反直觉点，脚本里已经处理，改的时候别改回去：

1. **抓取失败必须回 200**。CLI 的实现是 `try { 远程 } catch { localFallback.fetch(...) }`——非 200 或异常会**静默回落本地直连**。在 TUN/fake-IP 代理环境下域名被解析到 `198.18.x.x` 保留段，看到的是 `WEB_PRIVATE_ADDRESS`，而不是真正的错误原因。所以脚本把失败写进正文、状态码仍给 200。（2026-09-16 补：`handle_fetch` 整体包了 `try/except`，连桥自己内部的异常也回 200——之前只兜住了"Exa 调用失败"这一条路，响应形状一变仍可能穿出去。）
2. **认证是本地令牌，不是 Exa key**。CLI 会带 `Authorization: Bearer <config.toml 里 [services.*].api_key>`，这只是本机闸门（脚本侧 `EXA_BRIDGE_TOKEN` 留空则不校验）。Exa key 只在脚本内部使用。
3. **401 之后必须读完请求体**（脚本已修）：keep-alive 连接上没读干净的 body 会被当成下一条请求行，表现为紧随其后的请求莫名 `400 Bad request syntax`。

桥另外带两个只读端点（跟 `/search` `/fetch` 无关，给 web 端小面板用）：

- `GET /status` → `{"ok", "session", "text", "cache", "balance"}`：本地 `statusline.py` 跑出的缓存率与余额（结果缓存 2 秒；`?session=session_…` 可指定会话，缺省取最新的）。只认本机 `Host`（防 DNS rebinding）、**不带 CORS 头**——普通网页读不到，浏览器用户脚本用 `GM_xmlhttpRequest` 才能取。
- `GET /panel` → 自包含小页面，每 5s 轮询 `/status`，开在浏览器里就能看这两个数字。

想把它们显示在 `kimi web` 页面角落（右下角小徽标），见 `references/statusline.md` 的「web 端」一节。

kimi-code 侧读取优先级：环境变量 `KIMI_WEB_SEARCH_BASE_URL` / `KIMI_WEB_SEARCH_API_KEY` / `KIMI_WEB_FETCH_BASE_URL` / `KIMI_WEB_FETCH_API_KEY` **优先于** `config.toml` 的 `[services.*]`。

## 收集参数

| 参数 | 取值 |
|------|------|
| Exa API key | 问用户要（UUID 形状，dashboard.exa.ai 可查）；已配置过的机器上可取自 `~/.kimi-code/mcp.json` 的 `mcpServers.exa.headers.x-api-key` |
| 本地令牌 | `python3 -c "import secrets;print(secrets.token_hex(16))"`（跨平台）或 `openssl rand -hex 16`；可留空跳过校验 |
| 端口 | 默认 `8787`，被占用就换（`EXA_BRIDGE_PORT`） |
| Python | ≥ 3.9，纯标准库。macOS `command -v python3`；Windows `where pythonw` |

**没有 Exa key 就别往下做这一节**：桥调 `api.exa.ai` 必须要 key，否则调不通。两条退路——

1. **去注册**（推荐）：dashboard.exa.ai 注册即得 key，新账号送 $20（约 2,800 次搜索），之后 Free Tier 每月再送 $10；拿到 key 再回来做这一节。
2. **先不建桥，只挂匿名 MCP**：`mcp.json` 里只写 `{"url": "https://mcp.exa.ai/mcp"}`、**不要 `headers`**——实测（2026-09）不带任何 key 也能搜索、也能抓取。代价：内置 `WebSearch` / `FetchURL` 用不了（它们会回落到需要 `/login` 的 Kimi 托管服务），联网只能走 MCP 工具。

## 1. 放脚本

```bash
mkdir -p ~/.kimi-code/exa-bridge
cp "$SKILL_DIR/assets/exa-bridge.py" ~/.kimi-code/exa-bridge/
chmod +x ~/.kimi-code/exa-bridge/exa-bridge.py
```

Windows 上 `chmod` 是无操作，跳过即可——桥由 `pythonw.exe <脚本>` 拉起，不靠可执行位。

## 2. 写 config.toml（只增不覆盖）

**别手动"追加"——用幂等补丁脚本**。实测坑：往 `config.toml` 末尾重复追加一个已经存在的表，会让 TOML 解析失败，kimi-code 会**丢弃整份配置**并报 `No model configured. Run /login …`（日志里没有任何线索）。所以一律走 `assets/patch-config.py`：

```bash
S=$SKILL_DIR/assets
python3 "$S/patch-config.py" set services.moonshot_search.base_url http://127.0.0.1:8787/search
python3 "$S/patch-config.py" set services.moonshot_search.api_key  "<本地令牌>"
python3 "$S/patch-config.py" set services.moonshot_fetch.base_url  http://127.0.0.1:8787/fetch
python3 "$S/patch-config.py" set services.moonshot_fetch.api_key   "<本地令牌>"
python3 "$S/patch-config.py" check      # 体检：重复表 / 解析结果 / services 段
```

它只改指定字段、保留注释排版；存在就改值、不存在才插入；写前自动备份、写前复验（不通过就不落盘）。写成上面的效果等价于：

```toml
[services.moonshot_search]
base_url = "http://127.0.0.1:8787/search"
api_key = "<本地令牌>"

[services.moonshot_fetch]
base_url = "http://127.0.0.1:8787/fetch"
api_key = "<本地令牌>"
```

## 3. 起常驻

**macOS（launchd，已实测）**——用模板生成，别手写 XML：

```bash
D=$HOME/.kimi-code/exa-bridge
TOKEN=<本地令牌>
# 先 tr -d '\r'：CRLF 的工作区会把 \r 带进令牌（与 config.toml 对不上 → 桥 401，实测踩过）
tr -d '\r' < "$SKILL_DIR/assets/launchagent.plist.template" | \
  sed -e "s|__PYTHON__|$(command -v python3)|" -e "s|__SCRIPT__|$D/exa-bridge.py|" \
    -e "s|__LOG__|$D/bridge.log|" \
    -e "s|__PORT__|8787|" -e "s|__EXA_API_KEY__|<Exa key>|" -e "s|__EXA_BRIDGE_TOKEN__|$TOKEN|" \
    > ~/Library/LaunchAgents/ai.kimi.exa-bridge.plist
plutil -lint ~/Library/LaunchAgents/ai.kimi.exa-bridge.plist   # 必须 OK，XML 坏了 launchd 会静默不理
chmod 600 ~/Library/LaunchAgents/ai.kimi.exa-bridge.plist

launchctl bootout gui/$(id -u)/ai.kimi.exa-bridge 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.kimi.exa-bridge.plist
launchctl print gui/$(id -u)/ai.kimi.exa-bridge | head -20
```

- 改了 **plist** 必须 `bootout` + `bootstrap`（`kickstart -k` 只重启已加载的旧定义，不重读文件）；
- 只改了**脚本**用 `launchctl kickstart -k gui/$(id -u)/ai.kimi.exa-bridge` 即可；
- 脚本被 kill 后 launchd 会自动拉起（`KeepAlive`）。

**Windows 11（2026-09-16 实测：Windows 11 + kimi-code 0.43.1 + Store 版 Python 3.13，非管理员账户）**——分两步：先做第 0 步生成启动器，再按可用性从上往下挑一条常驻路。

**0. 生成启动器（三条常驻路都要用）**：`pythonw.exe` 是 GUI 子系统程序、没有控制台，计划任务和启动文件夹又都塞不进环境变量——所以令牌和日志得靠一个 `.pyw` 包装器（它等价于 macOS plist 里的 `EnvironmentVariables` + `StandardErrorPath`）：

```powershell
$skillDir = "$env:USERPROFILE\.kimi-code\skills\kimi-code-setup"   # 没拷进 skills 目录就改成实际路径
$dst = "$env:USERPROFILE\.kimi-code\exa-bridge"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item "$skillDir\assets\exa-bridge.py" "$dst\exa-bridge.py" -Force

$exaKey = ''            # 留空 = 桥改读 mcp.json 的 x-api-key（推荐，省得把 key 散在三处）
$token  = '<本地令牌>'   # 留空 = 不校验；填了就要和 config.toml 两处 [services].api_key 一致
$tpl = Get-Content "$skillDir\assets\windows-launch.pyw.template" -Raw
$tpl = $tpl.Replace('__SCRIPT__', "$dst\exa-bridge.py".Replace('\','/')) `
           .Replace('__LOG__', "$dst\bridge.log".Replace('\','/')) `
           .Replace('__EXA_API_KEY__', $exaKey).Replace('__EXA_BRIDGE_TOKEN__', $token)
Set-Content "$dst\launch.pyw" $tpl -Encoding UTF8

python --version                                    # 没有就先装：winget install -e --id Python.Python.3.12
$pyw = (Get-Command pythonw.exe).Source             # Store 版 Python 也有 pythonw；机器上没有 py 启动器不代表没有它
Start-Process -FilePath $pyw -ArgumentList "`"$dst\launch.pyw`"" -WindowStyle Hidden   # 先手动起一次
curl.exe -s http://127.0.0.1:8787/health            # 期望 {"ok":true,..."key":true}
```

**1. 三条常驻路**（实测结论：①②在本机被挡，③可用）：

| 路 | 做法 | 实测 |
|----|------|------|
| ① 计划任务 | 见下方脚本 | ❌ 非管理员账户下 `Register-ScheduledTask`、`schtasks /Create`、计划任务 COM 三种写法全是 `Access is denied (0x80070005)` |
| ② `HKCU\...\Run` | `reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v kimi-exa-bridge /t REG_SZ /d "\"$pyw\" \"$dst\launch.pyw\"" /f` | ❌ 命令报成功、**下一条命令回读就没了**——被安全软件静默回滚（本机装火绒 HIPS）；把它加进白名单后可再用 |
| ③ 启动文件夹快捷方式 | 见下方脚本，**不需要管理员** | ✅ 本机采用；`.lnk` 落盘正常。⚠️ 2026-09-16 实测有一次重启后它**没被处理**，见下方 **2.5** |

①计划任务（管理员 / 组策略允许时最标准）：
```powershell
$action  = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dst\launch.pyw`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
# 两个默认设置的坑（计划任务通用默认行为）：电池供电时不启动/被停、执行满 72 小时被强杀：
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "kimi-exa-bridge" -Action $action -Trigger $trigger -Settings $settings -Force
Start-ScheduledTask -TaskName "kimi-exa-bridge"     # 立即起，不必重登录
```

③启动文件夹（用户级，无需提权）：
```powershell
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'kimi-exa-bridge.lnk'
$sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sc.TargetPath = $pyw
$sc.Arguments = '"' + $dst + '\launch.pyw"'
$sc.WorkingDirectory = $dst
$sc.WindowStyle = 7        # 最小化，避免登录时闪一下
$sc.Save()
```

**2. 判据（三条路相同）**：`curl.exe -s http://127.0.0.1:8787/health` 返回 `"ok":true` 且 `"key":true`；`$dst\bridge.log` 里出现 `exa-bridge listening on ...`。写完自启项**立刻回读一次**，别只信命令回显的"成功"——`Get-ScheduledTaskInfo -TaskName kimi-exa-bridge` / `reg query "HKCU\..." /v kimi-exa-bridge` / `Get-ChildItem ([Environment]::GetFolderPath('Startup'))`。

**2.5 桥没在跑（重启后没起来 / 中途被杀，2026-09-16 两次实测）**：① **重启后没起来**——01:07 重启、01:08 登录，之后桥没有自己起来（`/health` 连接被拒、`bridge.log` 里没有新横幅），而 Windows「设置 → 应用 → 启动」里那条 `pythonw.exe`（就是本快捷方式）**显示为「开」**；同一次登录里 OneDrive、TranslucentTB 等**用户级**自启项同样"标记为开却没在跑"（服务级的火绒 / RtkAudUService 正常）。② **没重启也会挂**——同一天 02:01 又发现桥没了，`bridge.log` 里**只有请求行、没有任何 traceback**，说明它是**被杀**而不是自己崩（火绒是头号嫌疑，未坐实）；那次同样是"手动跑一次快捷方式"救活。**快捷方式本身两次都是好的**：跑一次那个 `.lnk`，桥立刻 `listening`。另外注意：桥的进程名是 **`pythonw3.13`**（Store 版 Python 的真名），`Get-Process pythonw` 查不到它，别据此判定"桥没在跑"——**判断存活只认 `/health`，别依赖日志**。**兜底（2026-09-16 加，已实测自愈）**：状态栏脚本（每秒被 runner 调一次）现在顺手探活——只做 TCP `connect`、30 秒最多一次，拒连就 `Popen` 拉起 `exa-bridge/launch.pyw`，冷却 60 秒；门闩是 `KIMI_CODE_STATUS_LINE=1`，只有 runner 调用时才生效（手动跑 / `verify.py` 自测都不会误拉起）。实测：杀掉桥后 **2 秒内自动回来**。边界：**只在 kimi 会话活着时有效**（关掉 kimi 就没守护，而那正是用不上搜索的时候）。实现细节见 `references/statusline.md` 已知边界。

处理顺序：① `verify.py` 或 `curl /health` 确认桥不在；② **先等最多 30 秒**——兜底探活最多 30 秒跑一次，撞上就会把它拉起来（`statusline/bridge-watch.json` 里能看到 `last_ok`/`relaunched`）；③ 还没起来就跑一次快捷方式；④ 只有重现失败才去查配置。

**火绒这条线索（2026-09-16 翻过日志）**：把火绒的「安全日志」按当天翻了一遍——只有 5 条，全是它自己的动作（01:41:55 升级到 6.0.11.3、01:42 系统修复/漏洞修复、**01:58:06 手动清理 1.2GB 垃圾**），**没有任何"拦截 / 结束进程"记录**；而桥被发现死亡是 02:01，紧跟在 01:58 那次清理之后——"升级或垃圾清理顺带把它带走了"仍是最像的解释，但**没坐实**。已把 `%USERPROFILE%\.kimi-code\exa-bridge` 加进火绒信任区（类型：文件夹及子目录，用 computer-use 工具点界面加的）。**别把信任区当护身符**：它只让病毒扫描跳过这个目录，不等于放行进程行为；下次再被杀，先打开火绒「安全日志」按时间点对一遍（没有条目就说明不是它的主动拦截，往别处查）。

**3. 排错**：`.pyw` 起不来时用 `python.exe`（不是 pythonw）前台跑同一个 `launch.pyw`，日志会同时打到终端（Ctrl+C 退出）；端口被占就在启动器里加一行 `os.environ.setdefault("EXA_BRIDGE_PORT", "8788")`，并同步改 `config.toml` 两处 `base_url`。

**Linux（systemd 用户单元；2026-09-16 在 WSL2 + kimi-code 0.41.0 实测通过）**：

```bash
mkdir -p ~/.config/systemd/user ~/.kimi-code/exa-bridge
cp "$SKILL_DIR/assets/exa-bridge.py" ~/.kimi-code/exa-bridge/
D=$HOME/.kimi-code/exa-bridge
TOKEN=$(python3 -c "import secrets;print(secrets.token_hex(16))")
# 模板必须先 tr -d '\r' 再 sed：CRLF 模板会让生成的每一行结尾多一个 \r，
# EXA_BRIDGE_TOKEN 被带上回车后与 config.toml 里的对不上，打桥直接 401（实测踩过）
tr -d '\r' < "$SKILL_DIR/assets/systemd-user.service.template" | sed \
    -e "s|__PYTHON__|$(command -v python3)|" -e "s|__SCRIPT__|$D/exa-bridge.py|" \
    -e "s|__LOG__|$D/bridge.log|" -e "s|__PORT__|8787|" \
    -e "s|__EXA_API_KEY__|<Exa key>|" -e "s|__EXA_BRIDGE_TOKEN__|$TOKEN|" \
    > ~/.config/systemd/user/ai.kimi.exa-bridge.service
chmod 600 ~/.config/systemd/user/ai.kimi.exa-bridge.service   # 里面有 Exa key
systemctl --user daemon-reload
systemctl --user enable --now ai.kimi.exa-bridge
systemctl --user status ai.kimi.exa-bridge --no-pager | head -15
loginctl enable-linger "$USER"    # 关键：纯 SSH / 不登录图形会话时也让服务常驻（WSL2 免提权通过；要授权时会弹 polkit）
```

- **WSL2 前置**：`systemctl --user` 要先有 systemd——`/etc/wsl.conf` 里写 `[boot]` 段加 `systemd=true`，再 `wsl --shutdown` 重进；否则第一条 `systemctl --user daemon-reload` 就会报 “System has not been booted with systemd as init system”。
- **同一条本地令牌写两处**：`config.toml` 的 `[services.*].api_key`（走 `patch-config.py set`）与 unit 里的 `EXA_BRIDGE_TOKEN`。两边不一致就是"直打桥 401"；`verify.py` 的「常驻定义令牌」一项直接比对这两处——**令牌尾部多了个 `\r` 也认得出来**（就是上面那个 CRLF 坑的症状）。
- 改了 **unit** 要 `systemctl --user daemon-reload` 再 `restart`；只改**脚本**直接 `systemctl --user restart ai.kimi.exa-bridge`。
- 日志：unit 里把 stdout/stderr 写进了 `bridge.log`；systemd 自己的记录用 `journalctl --user -u ai.kimi.exa-bridge -n 50 --no-pager`。
- 环境变量同理**不继承 shell**（`export HTTPS_PROXY=…` 对 systemd 无效），要显式写进 unit 的 `Environment=`。
- WSL2 实测：`enable` 建的软链在 `~/.config/systemd/user/default.target.wants/`；`kill -9` 掉桥后 `Restart=always` 会在几秒内拉起来（新 PID + `/health` 恢复）。macOS/Windows 那套"兜底自愈"在这儿用不上——状态栏脚本里那个探活拉起是 Windows 专属。
- **`KIMI_CODE_HOME` 不在默认位置时要显式写进 unit**：桥不继承 shell 环境变量，自定义过 home 的机器加一行 `Environment=KIMI_CODE_HOME=/your/.kimi-code`，否则桥会去默认 `~/.kimi-code` 找 `mcp.json` 的 key 和 `sessions/`（现象：`/health` 报 `key:false`、`/status` 一直空）。
- **日志别让它无限长**：桥对每个请求写一行，unit 用 `StandardOutput=append:` 只追加不轮转。长期常驻的机器挂一份 logrotate（写日志的进程不会重开文件，所以用 `copytruncate`）：

  ```bash
  # /etc/logrotate.d/kimi-exa-bridge（要 root；不想动系统就定期手工 `: > bridge.log`）
  /home/<你>/.kimi-code/exa-bridge/bridge.log {
      weekly
      rotate 4
      copytruncate
      missingok
      notifempty
  }
  ```

**兜底**：不装常驻，需要时前台 `python3 ~/.kimi-code/exa-bridge/exa-bridge.py`。

Exa key 的读取顺序：环境变量 `EXA_API_KEY` → `~/.kimi-code/mcp.json` 的 `mcpServers.exa.headers.x-api-key`（**每次请求现读**，改 mcp.json 不用重启脚本）。Windows 计划任务不方便配环境变量，把 key 放进 `mcp.json` 最省事；macOS 的 plist 里直接写 `EXA_API_KEY`。

## 4. 验证（三层，缺一层都不算完成）

```bash
# ① 桥活着且拿到 key（key:false 说明 Exa key 没配到）
curl -s http://127.0.0.1:8787/health        # {"ok":true,"port":8787,"results":5,"key":true}

# ② 直接打桥（用 config.toml 里那个本地令牌）
curl -s -X POST http://127.0.0.1:8787/search \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer <本地令牌>' \
  -d '{"text_query":"exa.ai pricing"}'
# 401 = 令牌与脚本不一致；502 = Exa key 错/额度报错，看返回正文
```

③ **端到端**——必须新起一个 kimi 进程（`[services.*]` 在进程里只解析一次）：

```bash
kimi -p "用内置 WebSearch 搜一下 exa.ai 的定价，一句话回答"
tail -3 ~/.kimi-code/exa-bridge/bridge.log     # 应有 POST /search 记录
```

再核对工具清单（做法见 SKILL.md「总验收」）。

**一条命令版**（推荐，只读）：`python3 "$SKILL_DIR/assets/verify.py"` —— 覆盖出网 / 配置 / 桥 / MCP / 工具清单 / CLI doctor / 补丁脚本自测 / 脚本漂移；加 `--e2e` 会再跑一次真实端到端。出网不通时它会把桥的失败降级成告警，先别冤枉桥；端点不是本机 exa-bridge（如 Kimi 托管）时会跳过桥检查，属正常。

## 5. 回滚

先删两段 `[services.*]`——别手改，用补丁脚本（表被删空后表头会自动删掉）：

```bash
S=$SKILL_DIR/assets
python3 "$S/patch-config.py" unset services.moonshot_search.base_url
python3 "$S/patch-config.py" unset services.moonshot_search.api_key
python3 "$S/patch-config.py" unset services.moonshot_fetch.base_url
python3 "$S/patch-config.py" unset services.moonshot_fetch.api_key
```

（或整份还原改动前的备份。）然后停常驻——先杀掉正在跑的桥（PowerShell：`Stop-Process -Id (Get-NetTCPConnection -LocalPort 8787 -State Listen).OwningProcess -Force`），再删自启项：macOS `launchctl bootout gui/$(id -u)/ai.kimi.exa-bridge` 并删 plist；**Windows 按当初走的是哪条路删哪条**——计划任务 `Unregister-ScheduledTask -TaskName "kimi-exa-bridge" -Confirm:$false`、注册表 `reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v kimi-exa-bridge /f`、启动文件夹 `Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'kimi-exa-bridge.lnk')`；Linux `systemctl --user disable --now ai.kimi.exa-bridge` 并删 `~/.config/systemd/user/ai.kimi.exa-bridge.service` → 删 `~/.kimi-code/exa-bridge/` → 新开 kimi 进程生效。内置工具回到 Kimi 托管服务。

## 排错速查

| 症状 | 原因 | 处理 |
|------|------|------|
| `WebSearch` 直接报连接错误 | 桥没在跑 | `curl 127.0.0.1:8787/health`；macOS `launchctl print gui/$(id -u)/ai.kimi.exa-bridge`；**Windows 按当初走的路查**——计划任务 `Get-ScheduledTaskInfo -TaskName kimi-exa-bridge`、注册表 `reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v kimi-exa-bridge`、启动文件夹 `Get-ChildItem ([Environment]::GetFolderPath('Startup'))`；Linux `systemctl --user status ai.kimi.exa-bridge` |
| Windows：计划任务建不了（`Access is denied`，`0x80070005`） | 非管理员账户或被组策略挡住（实测：cmdlet / `schtasks` / COM 三路全拒） | 改用启动文件夹快捷方式（第 3 节 ③），不需要提权 |
| Windows：`HKCU\...\Run` 写入报成功、回读却没有 | 安全软件静默回滚自启项（本机火绒 HIPS 实测） | 加白名单，或直接用启动文件夹；**写完必须回读**——`reg add` 回显的"成功"不可信 |
| 桥活着，但搜索报 `URLError` / `SSL: UNEXPECTED_EOF_WHILE_READING`；体检显示"出网不通" | **代理没把 `api.exa.ai` 放出去**（2026-09 实测过一次：DeepSeek 通、Exa 不通，10s 超时） | 先 `curl -sS -o /dev/null -w '%{http_code}\n' https://api.exa.ai`：`000`/超时 = 网络层 → 打开代理软件——**换节点 / 更新订阅 / 确认规则没把 `api.exa.ai` 和 `mcp.exa.ai` 设成 DIRECT**；401 或 200 = 通的，再查别的原因。恢复后直接重试，**不用改任何配置** |
| 关掉 TUN、改成"只在终端 `export HTTPS_PROXY=…`"之后，后台的桥突然连不上 | launchd / 计划任务 / systemd 拉起的进程**不继承你 shell 里的环境变量** | 在 plist 的 `EnvironmentVariables` 里显式加 `HTTPS_PROXY`（必要时 `HTTP_PROXY`；建议同时加 `NO_PROXY=127.0.0.1,localhost`），再 `bootout` + `bootstrap`；Windows 把启动器模板里那两行注释掉的 `os.environ.setdefault("HTTPS_PROXY", …)` 取消注释（等同 plist 的做法），或设成系统环境变量；Linux 在 unit 里加 `Environment=HTTPS_PROXY=…`（同样建议 `NO_PROXY=127.0.0.1,localhost`），再 `daemon-reload` + `restart` |
| `FetchURL` 报 `WEB_PRIVATE_ADDRESS` | 桥挂了 → CLI 静默回落本地直连，撞 fake-IP 代理 | 先把桥救活；这错误**不代表** Exa 有问题 |
| 桥返回 `401 unauthorized` | `config.toml` 的 `api_key` 与 `EXA_BRIDGE_TOKEN` 不一致 | 两边改成同一个值；或把脚本的 token 留空 |
| 401 之后的请求莫名 `400 Bad request syntax` | 旧脚本没读完 401 的请求体 | 换用 skill 里的 `assets/exa-bridge.py`（已修） |
| **桥 `/health` 正常、直打 `/search` 却 401，两边令牌"看起来一模一样"** | 常驻定义是用 **CRLF 模板**生成的：`sed` 出来的每一行结尾多一个 `\r`，`EXA_BRIDGE_TOKEN` 被带上回车 → 与 `config.toml` 里的值差一个不可见字符（实测踩过，Linux systemd unit） | 重新生成定义，`sed` 之前先 `tr -d '\r' < 模板 \| sed …`（第 3 节 macOS / Linux 两段都已带上）；`verify.py` 的「常驻定义令牌」一项会直接报这个 |
| `/health` 里 `key: false` | 脚本拿不到 Exa key | 设 `EXA_API_KEY`，或在 `mcp.json` 写 `mcpServers.exa.headers.x-api-key` |
| Exa 返回 `402 NO_MORE_CREDITS` / `429` | 额度用尽或限速 | 充值/换 key；换 MCP 通道没用（同一把 key），只能换数据源（如自建 SearXNG 后改 `base_url`） |
| 配置改了没反应 | `[services.*]` 在进程内只解析一次 | 退出并重启 `kimi`（`-r` 恢复会话），别只在同一进程里开新会话 |
| 配置被"篡改"回 Kimi 托管 | 在会话里执行过 `/login`，它会重写 `config.services` | 重新加回两段 `[services.*]`（工具名不变，只是改走会员额度） |
| 端口被占 | 8787 冲突 | 改 `EXA_BRIDGE_PORT` 与 `config.toml` 两处 `base_url` |
| `launchctl kickstart -k` 报 `Could not find service`（但 `launchctl print` 明明能查到该 job） | launchd 偶发查不到 job（2026-09 实测遇到一次，原因不明） | 原样重试一次即可（第二次成功）；仍不行走第 3 节的 `bootout` + `bootstrap` |

## 边界

- 桥只监听 `127.0.0.1`，别的机器访问不到（要共享得改绑定地址 + 防火墙，另说）。
- Exa key 是敏感凭据：plist 权限收到 600，别贴进聊天记录、别提交进 git。
- 内置通道参数固定（`EXA_BRIDGE_NUM_RESULTS` 默认 5，摘要约 400 字符，抓取上限 20 万字符）；要更细的参数走 MCP（见 SKILL.md 第 3 步）。
