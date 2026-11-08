# exa-bridge 常驻：macOS（launchd）

> `references/web-tools-exa.md` 第 3 节「起常驻」的 macOS 分支。前面的 1~2 节（放脚本、写 `config.toml`）和后面的 4~5 节（三层验证、回滚）是三个平台共用的，仍在 `web-tools-exa.md` 里；**走 DeepSeek 后端时**模板里的 Exa key 留空即可（见 `web-tools-exa.md`「收集参数」第 3 条）。
>
> 下文 **`$SKILL_DIR`** = 这个 skill 所在目录（通常是 `~/.kimi-code/skills/kimi-code-setup`）。

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
