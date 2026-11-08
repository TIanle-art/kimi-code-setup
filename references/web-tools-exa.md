# 内置联网工具（WebSearch / FetchURL）→ 自己的 Exa 账号

> 主流程第 2 步的细则。目标：kimi-code 的 `WebSearch` / `FetchURL` 不再走 Kimi 托管服务，而是记在**你自己的 exa.ai 额度**上，工具名不变。
>
> 下文 **`$SKILL_DIR`** = 这个 skill 所在目录（通常是 `~/.kimi-code/skills/kimi-code-setup`）。

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
| 本地令牌 | `python3 -c "import secrets;print(secrets.token_hex(16))"`（跨平台）或 `openssl rand -hex 16`；技术上可留空跳过校验，但本机任何进程都能免令牌调桥、花你的 Exa 额度，`verify.py` 会报 WARN——**别留空** |
| 端口 | 默认 `8787`，被占用就换（`EXA_BRIDGE_PORT`） |
| Python | ≥ 3.9，纯标准库。macOS `command -v python3`；Windows `where pythonw` |

**既没有 Exa key、也不走下面第 3 条（DeepSeek）就别往下做这一节**：桥调 `api.exa.ai` 必须要 key，否则调不通。三条退路，按用户情况挑（这是 `SKILL.md` 第 0 步「用户说"我没有 Exa key"时给他三条路挑」那张小表的细则版；**key 别回显在回复正文里**）：

1. **去注册**（推荐）：dashboard.exa.ai 注册即得 key——**2026-09 时**新账号送 $20（约 2,800 次搜索），之后 Free Tier 每月再送 $10（营销数字会变，以 dashboard 为准）；两条通道都能建（内置 + MCP），花的也是他自己的额度。拿到 key 再回来做这一节。
2. **先不建桥，只挂匿名 MCP**：`mcp.json` 里只写 `{"url": "https://mcp.exa.ai/mcp"}`、**不要 `headers`**——实测（2026-09）不带任何 key 也能 `web_search_exa` / `web_fetch_exa`。代价：只有 MCP 通道可用（额度与速率由 Exa 服务端限制，上限未测）；内置 `WebSearch` / `FetchURL` 用不了（它们会回落到需要 `/login` 的 Kimi 托管服务），联网只能走 MCP 工具。**选了 ② 之后想升级**：注册拿 key → 填 plist 的 `EXA_API_KEY`（或 `mcp.json` 的 `x-api-key`）→ 按第 1~3 节建桥 → 重启。
3. **不用 Exa，改用 DeepSeek 的 Search / Fetch API**（✅ **2026-11 Windows 11 真机实测通过**；官方文档 https://api-docs.deepseek.com/guides/search/ ）：
   - **是什么**：DeepSeek 2026-10-17 上线的两个独立接口——`POST https://api.deepseek.com/v1/tools/search`（`{"query": ≤128 字符, "count": 1–50}` → `results[]`，每条有标题、URL、正文/摘要）与 `POST https://api.deepseek.com/v1/tools/fetch`（抓单页，返回清洗后的 Markdown）；`Authorization: Bearer <DeepSeek key>`，**与对话用的是同一把 key**。**价格与限额（2026-11 按官方文档核对）**：Search、Fetch 各 **$0.75 / 千次成功请求**——只有 HTTP 200 且有结果才计费，失败、空结果、超时不计费，`count` 多少不影响单价；限流两者独立、按账号算：**Search 100 QPS、Fetch 25 QPS**，Fetch 另有**按目标域名**的 QPS 上限，超了回 HTTP 429（桥会把它写进抓取正文：`[exa-bridge] fetch failed: DeepSeek HTTP 429 …`，隔一会儿重试即可）。官方页：[Search & Fetch 指南](https://api-docs.deepseek.com/guides/search/)、[Rate Limit](https://api-docs.deepseek.com/quick_start/rate_limit/)；数字会变，以官方为准。
   - **怎么接**：第 1~3 节照做，只有两处不同：① 常驻定义里 `EXA_API_KEY` **留空**（模板不用改）；② 确认 `config.toml` 的 `[providers.deepseek].api_key` 有值（对话 provider 是 DeepSeek 的机器天然满足），或在常驻定义里另加 `DEEPSEEK_API_KEY`。桥启动时发现没有 Exa key、有 DeepSeek key，就**自动改走 DeepSeek**（日志里 `backend=deepseek`，`/health` 也带 `"backend": "deepseek"`）；想强制就设 `EXA_BRIDGE_BACKEND=deepseek`。
   - **名字沿用 exa-bridge**：走 DeepSeek 时脚本名、目录、服务名、`EXA_BRIDGE_*` 环境变量都不改（改名要所有老机器重新部署常驻定义），看 `/health` 的 `backend` 字段就知道实际走哪家。
   - **代价**：没有 exa MCP（`mcp.json` 不写 exa），批量抓取、`maxCharacters`、`agent_run` 这些超集能力没有；AGENTS.md 用 `SKILL.md` 第 5 步的 **B 段**（不提 `mcp__exa__*`），桥挂了就只剩 Bash curl。
   - **实测与容错**：2026-11 真机跑 `verify.py --e2e`，搜索 / 抓取都返回正文。桥对响应字段做了多写法容错（`content`/`snippet`/`summary`、外面多包一层 `data` 都认），DeepSeek 以后改了响应形状时 `/search` 会回空结果、`/fetch` 回 `[exa-bridge] no content returned … (deepseek)`——照着官方文档改 `deepseek_search` / `deepseek_fetch` 两个函数即可。
   - **兜底**：DeepSeek 也不想用，就退回"用 Bash curl 抓指定页面"（没有搜索能力，只有抓取）。

非交互场景（`kimi -p "调试 kimi-code"`）没有提问通道：要在提示词里一次把平台、key、要不要 MCP 说全，或让用户改用交互会话。

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

按平台读对应文件，**只读你这台机器的那一份**：

| 平台 | 常驻方式 | 细则 |
|------|----------|------|
| macOS | launchd LaunchAgent（模板 `assets/launchagent.plist.template`） | `references/bridge-macos.md` |
| Windows 11 | `launch.pyw` 启动器 + 计划任务 / `HKCU\...\Run` / **启动文件夹快捷方式**（非管理员机器上只有最后一条可靠） | `references/bridge-windows.md` |
| Linux | systemd 用户单元（模板 `assets/systemd-user.service.template`；WSL2 要先开 systemd） | `references/bridge-linux.md` |

三个平台的共同点：**模板先 `tr -d '\r'` 再 `sed`**（CRLF 会把 `\r` 带进令牌 → 桥 401）；同一把本地令牌写两处（常驻定义的 `EXA_BRIDGE_TOKEN` 与 `config.toml` 两处 `api_key`）；后台进程**不继承 shell 的环境变量**（代理、`KIMI_CODE_HOME` 都要显式写进定义）。

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

再核对工具清单（`verify.py` 的「工具清单」一项；想亲眼看见 `references/health-check.md` 末尾）。

**一条命令版**（推荐，只读）：`python3 "$SKILL_DIR/assets/verify.py"`——**覆盖清单只维护在 `SKILL.md`「assets 里有什么」的 `verify.py` 一行**，这里不再重复枚举；加 `--e2e` 会再跑一次真实端到端。出网不通时它会把桥的失败降级成告警，先别冤枉桥；端点不是本机 exa-bridge（如 Kimi 托管）时会跳过桥检查，属正常。

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
| Windows：计划任务建不了（`Access is denied`，`0x80070005`） | 非管理员账户或被组策略挡住（实测：cmdlet / `schtasks` / COM 三路全拒） | 改用启动文件夹快捷方式（`references/bridge-windows.md` ③），不需要提权 |
| Windows：`HKCU\...\Run` 写入报成功、回读却没有 | 安全软件静默回滚自启项（本机火绒 HIPS 实测） | 加白名单，或直接用启动文件夹；**写完必须回读**——`reg add` 回显的"成功"不可信 |
| 桥活着，但搜索报 `URLError` / `SSL: UNEXPECTED_EOF_WHILE_READING`；体检显示"出网不通" | **代理没把 `api.exa.ai` 放出去**（2026-09 实测过一次：DeepSeek 通、Exa 不通，10s 超时） | 先 `curl -sS -o /dev/null -w '%{http_code}\n' https://api.exa.ai`：`000`/超时 = 网络层 → 打开代理软件——**换节点 / 更新订阅 / 确认规则没把 `api.exa.ai` 和 `mcp.exa.ai` 设成 DIRECT**；401 或 200 = 通的，再查别的原因。恢复后直接重试，**不用改任何配置** |
| 关掉 TUN、改成"只在终端 `export HTTPS_PROXY=…`"之后，后台的桥突然连不上 | launchd / 计划任务 / systemd 拉起的进程**不继承你 shell 里的环境变量** | 在 plist 的 `EnvironmentVariables` 里显式加 `HTTPS_PROXY`（必要时 `HTTP_PROXY`；建议同时加 `NO_PROXY=127.0.0.1,localhost`），再 `bootout` + `bootstrap`；Windows 把启动器模板里那两行注释掉的 `os.environ.setdefault("HTTPS_PROXY", …)` 取消注释（等同 plist 的做法），或设成系统环境变量；Linux 在 unit 里加 `Environment=HTTPS_PROXY=…`（同样建议 `NO_PROXY=127.0.0.1,localhost`），再 `daemon-reload` + `restart` |
| `FetchURL` 报 `WEB_PRIVATE_ADDRESS` | 桥挂了 → CLI 静默回落本地直连，撞 fake-IP 代理 | 先把桥救活；这错误**不代表** Exa 有问题 |
| 桥返回 `401 unauthorized` | `config.toml` 的 `api_key` 与 `EXA_BRIDGE_TOKEN` 不一致 | 两边改成同一个值；或把脚本的 token 留空 |
| 401 之后的请求莫名 `400 Bad request syntax` | 旧脚本没读完 401 的请求体 | 换用 skill 里的 `assets/exa-bridge.py`（已修） |
| **桥 `/health` 正常、直打 `/search` 却 401，两边令牌"看起来一模一样"** | 常驻定义是用 **CRLF 模板**生成的：`sed` 出来的每一行结尾多一个 `\r`，`EXA_BRIDGE_TOKEN` 被带上回车 → 与 `config.toml` 里的值差一个不可见字符（实测踩过，Linux systemd unit） | 重新生成定义，`sed` 之前先 `tr -d '\r' < 模板 \| sed …`（`bridge-macos.md` / `bridge-linux.md` 的命令都已带上）；`verify.py` 的「常驻定义令牌」一项会直接报这个 |
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
