#!/usr/bin/env python3
"""Stop 钩子：Todo 面板上的任务全部 done 但面板没清空时，阻断本次结束。

kimi-code 在 Stop 事件通过 stdin 传会话信息；退出码 2 = 阻断，
stderr 内容写回上下文，模型看到后应先清空面板再收尾。
其余情况（没面板、面板里有未完成项、读不到状态）一律放行（fail-open）。

跨回合：全 done 的面板若是**之前的回合**留下、本回合没碰过，只拦**一次**
（记在 hooks/todo-panel-guard.state.json，按 session + 留下面板的那个回合），
拦过就放行——既不让面板烂尾，也不会每个回合都唠叨、更不会卡死。
"""
import json
import os
import sys

TAIL_BYTES = 1 << 20  # 最近的事件都在文件末尾，只看尾部即可
STATE_MAX = 50        # 状态文件最多记这么多个会话


def home_dir():
    return os.environ.get("KIMI_CODE_HOME") or os.path.expanduser("~/.kimi-code")


def find_session_dir(session_id):
    index = os.path.join(home_dir(), "session_index.jsonl")
    found = None
    try:
        with open(index, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("sessionId") == session_id and rec.get("sessionDir"):
                    found = rec["sessionDir"]
    except OSError:
        return None
    return found


def tail_lines(path):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > TAIL_BYTES:
                fh.seek(size - TAIL_BYTES)
                fh.readline()  # 丢掉截断的半行
            for raw in fh:
                yield raw.decode("utf-8", "replace")
    except OSError:
        return


def last_todos(path):
    """尾部里最后一次 TodoList 调用：(todos, 它所在的回合, 当前回合)。没调用过 todos 为 None。"""
    current = None
    todos, todo_turn = None, None
    for line in tail_lines(path):
        if "turnId" not in line:
            continue
        try:
            event = json.loads(line).get("event") or {}
        except ValueError:
            continue
        turn_id = event.get("turnId")
        if turn_id:
            current = turn_id
        if event.get("type") == "tool.call" and event.get("name") == "TodoList":
            args = event.get("args") or {}
            if isinstance(args.get("todos"), list):
                todos, todo_turn = args["todos"], turn_id
    return todos, todo_turn, current


def state_path():
    return os.path.join(home_dir(), "hooks", "todo-panel-guard.state.json")


def already_nagged(session_id, todo_turn):
    """跨回合的旧面板是否已经拦过一次；没拦过就记下来（写失败不影响判定）。"""
    path = state_path()
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    if state.get(session_id) == todo_turn:
        return True
    state.pop(session_id, None)
    state[session_id] = todo_turn
    while len(state) > STATE_MAX:          # dict 保持插入顺序：最早的先丢
        state.pop(next(iter(state)))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, path)
    except OSError:
        pass
    return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    session_id = payload.get("session_id") or ""
    session_dir = find_session_dir(session_id)
    if not session_dir:
        return 0
    wire = os.path.join(session_dir, "agents", "main", "wire.jsonl")
    if not os.path.exists(wire):
        return 0

    todos, todo_turn, current = last_todos(wire)
    if not todos:  # 没调用过，或已经清空（todos: []）
        return 0

    statuses = [str(item.get("status", "")).lower() for item in todos if isinstance(item, dict)]
    if statuses and all(status == "done" for status in statuses):
        if todo_turn != current and already_nagged(session_id, todo_turn):
            return 0              # 之前回合留下的旧面板，已经拦过一次：不再唠叨
        sys.stderr.write(
            "Todo 面板上的任务都已 done，但面板还没清空："
            "请先调用 TodoList（todos: []）清空面板，再结束本回合。\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
