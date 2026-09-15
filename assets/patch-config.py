#!/usr/bin/env python3
"""幂等地修补 kimi-code 的 config.toml：只动指定字段，保留注释与排版。

存在理由（实测）：往 config.toml 末尾重复"追加"同一个表（例如
[services.moonshot_search] 已经存在时再加一次）会让 TOML 解析失败，
kimi-code 会丢弃整份配置并报 "No model configured. Run /login ..."，
日志里什么线索都没有——极难定位。所以一律"先查再改"：存在就改值，
不存在才插入；同名表永远不会被写第二遍。

用法：
  patch-config.py set <点分键> <值>
      patch-config.py set services.moonshot_search.base_url http://127.0.0.1:8787/search
      patch-config.py set services.moonshot_search.api_key  <本地令牌>
      patch-config.py set thinking.effort max
      patch-config.py set default_permission_mode yolo
  patch-config.py unset <点分键> [--keep-empty]
      # 删键；表被删空时默认连表头一起删，--keep-empty 则保留空表头
      patch-config.py unset services.moonshot_search.api_key
  patch-config.py ensure-rule <allow|deny|ask> <pattern>
      patch-config.py ensure-rule allow 'mcp__exa__*'
  patch-config.py remove-rule <decision> <pattern>
  patch-config.py ensure-hook <事件> <命令> [--timeout 秒] [--matcher 正则]
      patch-config.py ensure-hook Stop "python3 ~/.kimi-code/hooks/todo-panel-guard.py" --timeout 5
  patch-config.py remove-hook <事件> <命令>
  patch-config.py check

  --file PATH    默认 $KIMI_CODE_HOME/config.toml 或 ~/.kimi-code/config.toml
  --no-backup    不写 .bak-<时间戳> 备份（默认会备份）
  --raw          只影响 set：值按原样写入（数字 / true / false），如
                 `--raw set thinking.enabled true`；默认一律按字符串加引号

写前自动备份；写前复验（重复表扫描 + Python ≥3.11 时用 tomllib 真解析），
不通过就不落盘（文件保持原样）并返回非零码。值里混进控制字符（\r / \n，典型来路
是从 CRLF 模板 sed 出来的令牌）会当场拒绝——那种值写进 TOML 必然解析失败。
"""

import argparse
import datetime
import os
import re
import shutil
import sys
from pathlib import Path

HEADER_RE = re.compile(r"^\s*(\[\[?[^\]]+\]\]?)\s*(?:#.*)?$")


def default_config() -> Path:
    home = os.environ.get("KIMI_CODE_HOME") or (Path.home() / ".kimi-code")
    return Path(home) / "config.toml"


def table_name(raw_header: str) -> str:
    inner = raw_header.strip()
    inner = inner[2:-2] if inner.startswith("[[") else inner[1:-1]
    return inner.strip()


def scan_headers(lines):
    out = []
    for i, line in enumerate(lines):
        m = HEADER_RE.match(line)
        if m:
            raw = m.group(1)
            out.append({"i": i, "raw": raw, "name": table_name(raw),
                        "array": raw.startswith("[[")})
    return out


def table_span(lines, start):
    for i in range(start + 1, len(lines)):
        if HEADER_RE.match(lines[i]):
            return i
    return len(lines)


def find_table(lines, name, array=False):
    for head in scan_headers(lines):
        if head["name"] == name and head["array"] == array:
            return head
    return None


def key_re(key: str) -> re.Pattern:
    bare = re.escape(key)
    return re.compile(r"^\s*(?:\"%s\"|'%s'|%s)\s*=" % (bare, bare, bare))


def format_value(value: str, raw: bool = False) -> str:
    """默认按字符串加引号；raw=True 时把值原样写入（数字 / true / false）。"""
    if raw:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % escaped


CONTROL_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")


def reject_control(value: str, label: str) -> bool:
    """拦下带控制字符的值。\r 的典型来路：从 CRLF 模板 sed 出来的令牌 / 命令。

    不拦的话值照样能写进行里，等到复验才报 Illegal character '\\r'——用户只看到
    一句 TOML 报错，猜不到是行尾符的锅（实测踩过：CRLF 的 systemd 模板）。
    """
    m = CONTROL_RE.search(value)
    if not m:
        return False
    print("拒绝写入 %s：值里第 %d 个字符是控制字符 %s。多半是从 CRLF 模板 sed / 命令替换"
          "出来的——先用 `tr -d '\\r'` 清一遍再写。文件未被修改。"
          % (label, m.start() + 1, repr(m.group(0))), file=sys.stderr)
    return True


def validate(lines):
    """文本级复验：普通表同名出现两次 = 非法 TOML。"""
    seen = {}
    for head in scan_headers(lines):
        if head["array"]:
            continue
        if head["name"] in seen:
            return False, "重复表 [%s]" % head["name"]
        seen[head["name"]] = True
    try:
        import tomllib
    except ImportError:
        return True, "OK（文本级复验；Python <3.11 跳过真解析）"
    import io
    try:
        tomllib.loads("".join(lines))
    except Exception as exc:
        return False, "TOML 解析失败：%s" % exc
    return True, "OK（tomllib 解析通过）"


def write_back(path: Path, lines, backup: bool):
    if backup:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = "%s.bak-%s" % (path, stamp)
        n = 1
        while os.path.exists(target):          # 同一秒内多次写入也别互相覆盖
            target = "%s.bak-%s-%d" % (path, stamp, n)
            n += 1
        shutil.copy2(path, target)
    tmp = "%s.patch-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("".join(lines))
    os.replace(tmp, path)


def cmd_set(path: Path, dotted: str, value: str, backup: bool, raw: bool = False) -> int:
    if not dotted.strip():
        print("键不能为空", file=sys.stderr)
        return 2
    if reject_control(value, "值（键 %s）" % dotted):
        return 2
    parts = dotted.split(".")
    key = parts[-1]
    table = ".".join(parts[:-1])            # 空 = 顶层键（如 default_model）
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    rendered = format_value(value, raw)

    if not table:
        matcher = key_re(key)
        first_table = next((h["i"] for h in scan_headers(lines)), len(lines))
        for i in range(first_table):
            if matcher.match(lines[i]):
                lines[i] = "%s = %s\n" % (key, rendered)
                action = "改值（顶层）"
                break
        else:
            at = 0
            while at < first_table and (not lines[at].strip() or lines[at].lstrip().startswith("#")):
                at += 1
            lines.insert(at, "%s = %s\n" % (key, rendered))
            action = "写入顶层键"
    else:
        head = find_table(lines, table)
        if head is None:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append("\n[%s]\n%s = %s\n" % (table, key, rendered))
            action = "新增表 [%s] 并写入" % table
        else:
            end = table_span(lines, head["i"])
            matcher = key_re(key)
            for i in range(head["i"] + 1, end):
                if matcher.match(lines[i]):
                    lines[i] = "%s = %s\n" % (key, rendered)
                    action = "改值"
                    break
            else:
                lines.insert(head["i"] + 1, "%s = %s\n" % (key, rendered))
                action = "在已有表 [%s] 里补键" % table

    ok, detail = validate(lines)
    if not ok:
        print("复验失败，未写入：%s" % detail, file=sys.stderr)
        return 2
    write_back(path, lines, backup)
    print("%s：%s = %s  （%s）" % (action, dotted, rendered, detail))
    return 0


def cmd_ensure_rule(path: Path, decision: str, pattern: str, backup: bool) -> int:
    if reject_control(pattern, "pattern"):
        return 2
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for head in scan_headers(lines):
        if head["name"] != "permission.rules" or not head["array"]:
            continue
        block = "".join(lines[head["i"]:table_span(lines, head["i"])])
        if re.search(r"decision\s*=\s*\"%s\"" % re.escape(decision), block) and \
           re.search(r"pattern\s*=\s*[\"']%s[\"']" % re.escape(pattern), block):
            print("规则已存在，跳过：%s %s" % (decision, pattern))
            return 0
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.append('\n[[permission.rules]]\ndecision = "%s"\npattern = "%s"\n' % (decision, pattern))
    ok, detail = validate(lines)
    if not ok:
        print("复验失败，未写入：%s" % detail, file=sys.stderr)
        return 2
    write_back(path, lines, backup)
    print("已追加权限规则：%s %s（%s）" % (decision, pattern, detail))
    return 0


HOOK_EVENTS = {
    "UserPromptSubmit", "UserPromptQueued", "PreToolUse", "Stop", "TurnStarted",
    "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionResult",
    "SessionStart", "SessionEnd", "SessionHeartbeat", "SubagentStart", "SubagentStop",
    "TaskStarted", "StopFailure", "Interrupt", "PreCompact", "PostCompact", "Notification",
}


def toml_string(value: str) -> str:
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')


def cmd_ensure_hook(path: Path, event: str, command: str, timeout, matcher, backup: bool) -> int:
    """按 event+command 去重地追加 [[hooks]] 规则（数组表，同名表可以出现多次）。"""
    if event not in HOOK_EVENTS:
        print("未知事件 %s；已知取值：%s（以官方文档 hooks 页为准）"
              % (event, "、".join(sorted(HOOK_EVENTS))), file=sys.stderr)
        return 2
    if reject_control(command, "command"):
        return 2
    if matcher and reject_control(matcher, "matcher"):
        return 2
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for head in scan_headers(lines):
        if head["name"] != "hooks" or not head["array"]:
            continue
        block = "".join(lines[head["i"]:table_span(lines, head["i"])])
        if re.search(r"event\s*=\s*[\"']%s[\"']" % re.escape(event), block) and \
           re.search(r"command\s*=\s*[\"']%s[\"']" % re.escape(command), block):
            print("钩子已存在，跳过：%s → %s" % (event, command))
            return 0
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.append("\n[[hooks]]\nevent = %s\n" % toml_string(event))
    if matcher:
        lines.append("matcher = %s\n" % toml_string(matcher))
    lines.append("command = %s\n" % toml_string(command))
    if timeout:
        lines.append("timeout = %d\n" % timeout)
    ok, detail = validate(lines)
    if not ok:
        print("复验失败，未写入：%s" % detail, file=sys.stderr)
        return 2
    write_back(path, lines, backup)
    print("已追加钩子：%s → %s（%s）" % (event, command, detail))
    return 0


def _commit(path: Path, lines, backup: bool, message: str) -> int:
    ok, detail = validate(lines)
    if not ok:
        print("复验失败，未写入：%s" % detail, file=sys.stderr)
        return 2
    write_back(path, lines, backup)
    print("%s（%s）" % (message, detail))
    return 0


def cmd_unset(path: Path, dotted: str, backup: bool, keep_empty: bool) -> int:
    """删掉一个点分键；表被删空后默认连表头一起删。找不到则不改任何东西。"""
    parts = dotted.split(".")
    key, table = parts[-1], ".".join(parts[:-1])
    if not key.strip():
        print("键不能为空", file=sys.stderr)
        return 2
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    matcher = key_re(key)

    if not table:
        first_table = next((h["i"] for h in scan_headers(lines)), len(lines))
        hits = [i for i in range(first_table) if matcher.match(lines[i])]
        if not hits:
            print("找不到顶层键 %s，未修改" % key, file=sys.stderr)
            return 2
        for i in reversed(hits):
            del lines[i]
        message = "已删除顶层键 %s" % key
        if len(hits) > 1:
            message += "（%d 处）" % len(hits)
        return _commit(path, lines, backup, message)

    head = find_table(lines, table)
    if head is None:
        print("找不到表 [%s]，未修改" % table, file=sys.stderr)
        return 2
    end = table_span(lines, head["i"])
    hits = [i for i in range(head["i"] + 1, end) if matcher.match(lines[i])]
    if not hits:
        print("表 [%s] 里找不到键 %s，未修改" % (table, key), file=sys.stderr)
        return 2
    for i in reversed(hits):
        del lines[i]
    body = lines[head["i"] + 1:table_span(lines, head["i"])]
    has_key = any(line.strip() and not line.lstrip().startswith("#") for line in body)
    message = "已删除 [%s] 的键 %s" % (table, key)
    if not has_key and not keep_empty:
        del lines[head["i"]]
        message += "，并删掉已空的表头"
    return _commit(path, lines, backup, message)


def cmd_remove_block(path: Path, table: str, required: dict, backup: bool, label: str) -> int:
    """删掉匹配 required（字段=值）的数组表块，如 [[permission.rules]] / [[hooks]]。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    spans = []
    for head in scan_headers(lines):
        if head["name"] != table or not head["array"]:
            continue
        end = table_span(lines, head["i"])
        block = "".join(lines[head["i"]:end])
        if all(re.search(r"%s\s*=\s*[\"']%s[\"']" % (field, re.escape(str(value))), block)
               for field, value in required.items()):
            spans.append((head["i"], end))
    if not spans:
        print("没找到匹配的 [[%s]] 块（%s），未修改"
              % (table, "、".join("%s=%s" % pair for pair in required.items())), file=sys.stderr)
        return 2
    for start, end in reversed(spans):
        del lines[start:end]
    return _commit(path, lines, backup, "已删除 %d 个 %s" % (len(spans), label))


def cmd_remove_rule(path: Path, decision: str, pattern: str, backup: bool) -> int:
    return cmd_remove_block(path, "permission.rules",
                            {"decision": decision, "pattern": pattern}, backup, "权限规则")


def cmd_remove_hook(path: Path, event: str, command: str, backup: bool) -> int:
    return cmd_remove_block(path, "hooks",
                            {"event": event, "command": command}, backup, "钩子")


def cmd_check(path: Path) -> int:
    if not path.exists():
        print("FAIL 找不到 %s" % path)
        return 2
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    heads = scan_headers(lines)
    seen, dups = set(), []
    for head in heads:
        if head["array"]:
            continue
        if head["name"] in seen:
            dups.append(head["name"])
        seen.add(head["name"])
    print("文件：%s（%d 行）" % (path, len(lines)))
    print("表：%s" % (", ".join(sorted(seen)) or "（无）"))
    if dups:
        print("FAIL 重复表：%s —— 这会让整份配置失效（kimi-code 会报 No model configured）"
              % ", ".join(sorted(set(dups))))
    ok, detail = validate(lines)
    print(("PASS " if ok else "FAIL ") + detail)
    for probe in ("services.moonshot_search", "services.moonshot_fetch"):
        print(("PASS 有 " if find_table(lines, probe) else "WARN 缺 ") + probe)
    hook_blocks = ["".join(lines[h["i"]:table_span(lines, h["i"])])
                   for h in scan_headers(lines) if h["name"] == "hooks" and h["array"]]
    if hook_blocks:
        events = []
        for block in hook_blocks:
            m = re.search(r"event\s*=\s*[\"']([^\"']+)[\"']", block)
            if m:
                events.append(m.group(1))
        print("PASS 钩子：%d 条（%s）" % (len(hook_blocks), "、".join(events) or "（事件没读懂）"))
        if any("todo-panel-guard.py" in block for block in hook_blocks):
            print("PASS 有 Todo 面板守卫钩子")
        else:
            print("WARN 没有 Todo 面板守卫钩子（见 SKILL.md 第 6 步）")
    else:
        print("WARN 没有 [[hooks]] —— Todo 面板守卫未装（见 SKILL.md 第 6 步）")
    return 2 if dups or not ok else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="幂等修补 kimi-code 的 config.toml")
    ap.add_argument("--file")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--raw", action="store_true",
                    help="只影响 set：值按原样写入（数字 / true / false）；默认按字符串加引号")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_set = sub.add_parser("set", help="设置 表.字段 = 值（存在就改，不存在才插）")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_unset = sub.add_parser("unset", help="删除 表.字段（表删空后默认连表头一起删）")
    p_unset.add_argument("key")
    p_unset.add_argument("--keep-empty", action="store_true", help="表删空后保留空表头")
    p_rule = sub.add_parser("ensure-rule", help="按 decision+pattern 去重地追加权限规则")
    p_rule.add_argument("decision", choices=["allow", "deny", "ask"])
    p_rule.add_argument("pattern")
    p_rdel = sub.add_parser("remove-rule", help="按 decision+pattern 删除权限规则")
    p_rdel.add_argument("decision", choices=["allow", "deny", "ask"])
    p_rdel.add_argument("pattern")
    p_hook = sub.add_parser("ensure-hook", help="按 event+command 去重地追加 [[hooks]] 规则")
    p_hook.add_argument("event", help="钩子事件，如 Stop（取值见官方文档 hooks 页）")
    p_hook.add_argument("command")
    p_hook.add_argument("--timeout", type=int, default=None, help="超时秒数（1–600）")
    p_hook.add_argument("--matcher", default=None, help="正则；不填=匹配全部")
    p_hdel = sub.add_parser("remove-hook", help="按 event+command 删除 [[hooks]] 规则")
    p_hdel.add_argument("event")
    p_hdel.add_argument("command")
    sub.add_parser("check", help="只体检：重复表 / 解析 / services 段 / 钩子")
    args = ap.parse_args()

    path = Path(args.file) if args.file else default_config()
    backup = not args.no_backup
    creating = args.cmd in ("set", "ensure-rule", "ensure-hook")
    if creating and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        print("已创建 %s" % path)
    if args.cmd in ("unset", "remove-rule", "remove-hook") and not path.exists():
        print("FAIL 找不到 %s" % path, file=sys.stderr)
        return 2
    if args.cmd == "set":
        return cmd_set(path, args.key, args.value, backup, args.raw)
    if args.cmd == "unset":
        return cmd_unset(path, args.key, backup, args.keep_empty)
    if args.cmd == "ensure-rule":
        return cmd_ensure_rule(path, args.decision, args.pattern, backup)
    if args.cmd == "remove-rule":
        return cmd_remove_rule(path, args.decision, args.pattern, backup)
    if args.cmd == "ensure-hook":
        return cmd_ensure_hook(path, args.event, args.command, args.timeout, args.matcher, backup)
    if args.cmd == "remove-hook":
        return cmd_remove_hook(path, args.event, args.command, backup)
    return cmd_check(path)


if __name__ == "__main__":
    sys.exit(main())
