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
- Windows（**未实测**）：脚本放 `%USERPROFILE%\.kimi-code\`，命令写 `py -3 %USERPROFILE%\.kimi-code\statusline.py`——`~` 在 `cmd.exe` 里不展开，反斜杠交给 `patch-config.py` 转义。
- 生效：`/reload-tui`（只重载 tui.toml）或新开会话。`tui.toml` 写坏了 kimi-code 会回落默认布局并提示，不会起不来。

## 验证

```bash
python3 "$SKILL_DIR/assets/verify.py" | grep 状态栏     # 体检里的状态栏几项
echo '{"model":"X","cwd":"'$HOME'","permissionMode":"yolo","sessionId":"session_x"}' \
  | python3 ~/.kimi-code/statusline.py                   # 手工喂一份快照看输出
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
- 本机实测（kimi-code 0.41.0，2026-09-15）：footer 渲染正常（另起临时实例截屏确认）、余额 ¥44.50 正常、脚本热路径 44ms（预算 300ms）。

## 回滚

- 只关掉：把 `tui.toml` 里 `[status_line]` 的 `command` 注释掉（下面一行 `items = [...]` 是内置槽位写法）。
- 彻底删：用补丁脚本删掉 `command`（同表还有 `items = [...]` 时只删 command，表空了会连表头一起删），再删脚本与缓存目录：

  ```bash
  python3 "$SKILL_DIR/assets/patch-config.py" --file "${KIMI_CODE_HOME:-$HOME/.kimi-code}/tui.toml" unset status_line.command
  rm ~/.kimi-code/statusline.py
  rm -rf ~/.kimi-code/statusline/
  ```
