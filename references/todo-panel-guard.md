# Todo 面板守卫（Stop 钩子）

**用途**：让「任务清单面板」不烂尾——面板上的条目**全部 `done` 之后如果没清空**，模型每次想结束回合都会被拦下，提示它先清空再收尾。这是配置层面的兜底，要和 `AGENTS.md` 里的约定（SKILL.md 第 5、6 步）一起装，否则被弹回来时模型不知道怎么回事。

## 机制

- `config.toml` 里一条 `[[hooks]]`：`event = "Stop"`（模型准备结束回合时触发，官方文档明确它**支持阻断**），`command` 调 `~/.kimi-code/hooks/todo-panel-guard.py`。
- 脚本读 stdin 的 `session_id` → 从 `$KIMI_CODE_HOME/session_index.jsonl` 定位会话目录 → 扫 `agents/main/wire.jsonl` 尾部，取**本回合**最后一次 `TodoList` 调用的 `todos`。
- 判定：本回合留下过面板、条目非空、且**全部** `status = "done"` → `exit 2` + stderr 提示（提示会写回上下文）；其余情况 `exit 0` 放行。
- 刻意不拦：有未完成项 / 「等用户的项」、本轮没动过面板（不跨回合唠叨）、已清空、读不到状态、脚本自身出错或超时（fail-open，不会把配置问题变成拦路虎）。
- **实测**（kimi-code 0.41.0，2026-09-15）：`kimi -p "…建一个全 done 面板，别清空…"` 被拦下、提示写回上下文，模型随后自行清空；脚本本身另有 6 个 fixture 用例。

## 安装

```bash
# 1. 脚本（macOS / Linux 路径相同；Windows 见下）
mkdir -p ~/.kimi-code/hooks
cp "$SKILL_DIR/assets/todo-panel-guard.py" ~/.kimi-code/hooks/
# 2. config.toml 里的钩子规则（幂等：重复跑不会加第二条）
python3 "$SKILL_DIR/assets/patch-config.py" ensure-hook Stop "python3 ~/.kimi-code/hooks/todo-panel-guard.py" --timeout 5
python3 "$SKILL_DIR/assets/patch-config.py" check      # 应看到 PASS 有 Todo 面板守卫钩子
```

- Windows（**未实测**）：脚本放 `%USERPROFILE%\.kimi-code\hooks\`，命令写 `py -3 %USERPROFILE%\.kimi-code\hooks\todo-panel-guard.py`；反斜杠由 `patch-config.py` 自动转义，别手写。用 `python3` 还是 `py` 看机器上装的是哪个。
- 生效时机：钩子在**会话启动时**加载 → **新开会话**生效（当前会话不变）。

## 验证

```bash
# ① 体检脚本里的行为自测（临时目录 + 假会话日志，不碰真实数据）
python3 "$SKILL_DIR/assets/verify.py" | grep 钩子
# ② 端到端：新起一个会话，故意留一个全 done 面板
cd "$(mktemp -d)" && kimi -p "用 TodoList 建一个只有一条 done 任务的面板，然后结束回合，不要清空面板"
#   期望：模型先被拦回（提示"任务都已 done 但面板没清空"），然后自行清空面板再结束
```

fixture 覆盖的 6 种情形：全 done→拦（exit 2）｜有未完成→放行｜跨回合（上一轮留的面板）→放行｜本轮已清空→放行｜未知或过期 session_id→放行｜真实会话当前状态→放行。

## 回滚 / 排错

- 不想用了：删掉规则 + 脚本（别手改配置，用补丁脚本按 event+command 精确匹配、整块删；找不到会报错不改文件）：

  ```bash
  python3 "$SKILL_DIR/assets/patch-config.py" remove-hook Stop "python3 ~/.kimi-code/hooks/todo-panel-guard.py"
  rm ~/.kimi-code/hooks/todo-panel-guard.py
  ```
- 被拦得太频繁：说明面板确实还留着全 done 的条目，清空即可；确认不想要就把钩子摘掉。
- 钩子没反应：先 `python3 "$SKILL_DIR/assets/patch-config.py" check`（规则在不在）→ 确认脚本文件存在 → 确认是**新会话**（钩子不热加载）。
- 钩子本身不写日志、静默生效；脚本行为异常时 `verify.py` 的「钩子脚本行为」一项会 FAIL。
