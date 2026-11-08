# exa-bridge 常驻：Linux（systemd 用户单元）

> `references/web-tools-exa.md` 第 3 节「起常驻」的 Linux 分支。前面的 1~2 节（放脚本、写 `config.toml`）和后面的 4~5 节（三层验证、回滚）是三个平台共用的，仍在 `web-tools-exa.md` 里；**走 DeepSeek 后端时**模板里的 Exa key 留空即可（见 `web-tools-exa.md`「收集参数」第 3 条）。
>
> 下文 **`$SKILL_DIR`** = 这个 skill 所在目录（通常是 `~/.kimi-code/skills/kimi-code-setup`）。

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
