#!/usr/bin/env python3
"""Stop 钩子：Todo 面板上的任务全部 done 但面板没清空时，阻断本次结束。

kimi-code 在 Stop 事件通过 stdin 传会话信息；退出码 2 = 阻断，
stderr 内容写回上下文，模型看到后应先清空面板再收尾。
其余情况（没面板、面板里有未完成项、读不到状态）一律放行（fail-open）。
"""
import json
import os
import sys

TAIL_BYTES = 1 << 20  # 当前回合的事件都在文件末尾，只看尾部即可


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


def todos_of_current_turn(path):
    """当前回合里最后一次 TodoList 调用留下的 todos；没调用过返回 None。"""
    turn = None
    todos = None
    for line in tail_lines(path):
        if "turnId" not in line:
            continue
        try:
            event = json.loads(line).get("event") or {}
        except ValueError:
            continue
        turn_id = event.get("turnId")
        if turn_id and turn_id != turn:
            turn, todos = turn_id, None  # 新回合，上一回合的记录作废
        if event.get("type") == "tool.call" and event.get("name") == "TodoList":
            args = event.get("args") or {}
            if isinstance(args.get("todos"), list):
                todos = args["todos"]
    return todos


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    session_dir = find_session_dir(payload.get("session_id") or "")
    if not session_dir:
        return 0
    wire = os.path.join(session_dir, "agents", "main", "wire.jsonl")
    if not os.path.exists(wire):
        return 0

    todos = todos_of_current_turn(wire)
    if not todos:  # 没调用过，或已经清空（todos: []）
        return 0

    statuses = [str(item.get("status", "")).lower() for item in todos if isinstance(item, dict)]
    if statuses and all(status == "done" for status in statuses):
        sys.stderr.write(
            "Todo 面板上的任务都已 done，但面板还没清空："
            "请先调用 TodoList（todos: []）清空面板，再结束本回合。\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
