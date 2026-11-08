# 体检结论怎么读

`assets/verify.py`（以及 `patch-config.py check`）的输出按下表查：左列是输出开头的文字，右边是含义与下一步。体检模式**只读**——查完再按 `SKILL.md` 对应步骤去修；表里的「第 N 步」都指 `SKILL.md` 的主流程。

| 结果 | 含义 | 下一步 |
|------|------|--------|
| `出网不通` / `代理出口不通` | 网络 / 代理层问题，**不是 kimi-code 的错**——体检脚本会替你区分"要走代理的域名全超时但直连正常"（=代理出口挂了）和"整机没网" | 代理软件里换节点 / 更新订阅 / 确认选中了可用节点（或 TUN 开着）；恢复后重试即可，不用改配置。细节见 `references/web-tools-exa.md`「排错速查」 |
| `services.*` 缺失或指向 Kimi 托管 | 大概被 `/login` 顶掉了 | 按第 2 步用补丁脚本加回来 |
| `桥 /health 打不通` | 桥没在跑（实测会被静默杀掉：重启后没起来、或中途被杀；日志无 traceback 不代表没挂） | **先只认 `/health`**（别用 `Get-Process pythonw`——真名是 `pythonw3.13`）。**Windows 上先等 30 秒左右**：状态栏脚本的兜底最多 30 秒探活一次，拒连就拉起——**优先跑启动文件夹的 `kimi-exa-bridge.lnk`**（ShellExecute 由 explorer 起、不在我们的进程树里，runner 超时那记 `taskkill /T /F` 杀不到它），没有快捷方式才回退 `Popen`（直接拉 `launch.pyw`）；重试间隔 30 秒（实测 2 秒内自愈），`statusline/bridge-watch.json` 里能看到 `last_ok`/`relaunched`——别按 5~10 秒预期；还不行再手动救活：macOS `launchctl print gui/$(id -u)/ai.kimi.exa-bridge`；**Windows 跑一次 `kimi-exa-bridge.lnk`**（不用 `Get-ScheduledTaskInfo`，本机没建计划任务）；Linux `systemctl --user status ai.kimi.exa-bridge`。细节见 `references/bridge-windows.md` 2.5 |
| `直打桥搜索 401` | `config.toml` 的令牌与桥的 `EXA_BRIDGE_TOKEN` 不一致 | 两边对齐（别靠把桥的 token 留空来绕，见下一行） |
| `EXA_BRIDGE_TOKEN 留空` WARN | 桥不校验令牌：虽然只绑 127.0.0.1，本机任何进程都能免令牌调它、花你的 Exa 额度 | 生成一把令牌，写进常驻定义和 `config.toml` 两处 `services.*.api_key`（`patch-config.py set`），重启桥 |
| `两处 services.*.api_key 不一致` | `moonshot_search` 与 `moonshot_fetch` 的令牌不是同一把——**只错一处时以前查不出来**，但 FetchURL 直打桥会 401 | 两处都该等于桥的 `EXA_BRIDGE_TOKEN`：用补丁脚本 `set` 对齐 |
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

## 自己看工具清单（原始记录）

`verify.py` 的「工具清单」一项读的就是这个；想亲眼看时：

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
