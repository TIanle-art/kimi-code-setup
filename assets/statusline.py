#!/usr/bin/env python3
"""kimi-code 自定义状态栏：整个会话的缓存命中率 + 当前 provider 的 API 余额。

由 ~/.kimi-code/tui.toml 的 [status_line] command 调用。kimi-code 通过 stdin
传入 JSON 快照（model / cwd / gitBranch / permissionMode / planMode / sessionId
/ contextTokens ...），本脚本的第一行 stdout 替换 footer 第一行。

kimi-code 只给 300ms，因此：
- 会话用量从 wire.jsonl 增量读取，偏移量与累计值存在 statusline/usage-*.json，
  单次最多花 USAGE_BUDGET_S 秒；大文件会被分成多次读，数字逐步收敛而不卡住渲染；
- 余额走本地缓存，真实请求交给 detached 子进程（--refresh-balance），主路径不联网；
- 顶部只导入轻量模块：urllib.request 与 subprocess 都在真正用到时才导入。Windows 上
  这两个模块合计要烧掉约 130ms 启动时间，惰性导入后主路径从 ~200ms 降到 ~110ms。
- Windows 附加：同一条命令顺手给 exa-bridge 探活（见 watch_bridge()）——桥被杀过两次，
  而启动文件夹的自启不会拉活（launchd / systemd 会）；只在 runner 调用时生效、30 秒最多
  一次、只做 TCP connect，不占 300ms 预算的大头。

命令行：python3 ~/.kimi-code/statusline.py [--refresh-balance <provider>]
"""

import glob
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
KIMI_HOME = os.environ.get("KIMI_CODE_HOME") or os.path.join(HOME, ".kimi-code")
STATE_DIR = os.path.join(KIMI_HOME, "statusline")
CONFIG_PATH = os.path.join(KIMI_HOME, "config.toml")

USAGE_BUDGET_S = 0.15
READ_CHUNK = 1 << 18
BALANCE_TTL_S = 300
BALANCE_RETRY_S = 60

# host 子串 -> (余额接口路径, 解析方式)
BALANCE_APIS = (
    ("deepseek", "/user/balance", "deepseek"),
    ("moonshot", "/users/me/balance", "moonshot"),
)


def bold(text):
    return "\x1b[1m" + text + "\x1b[22m"


def dim(text):
    return "\x1b[2m" + text + "\x1b[22m"


def color(code, text):
    return "\x1b[%dm%s\x1b[39m" % (code, text)


def read_state(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_state(path, data):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except Exception:
        pass


def state_path(name):
    return os.path.join(STATE_DIR, re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".json")


def format_tokens(n):
    n = int(n or 0)
    if n >= 1024 * 1024:
        return _trim(n / (1024.0 * 1024)) + "M"
    if n >= 1024:
        k = n / 1024.0
        return (str(int(round(k))) if k >= 100 else _trim(k)) + "k"
    return str(n)


def _trim(value):
    text = "%.1f" % value
    return text[:-2] if text.endswith(".0") else text


# ---------------------------------------------------------------- session usage


def find_wire(session_id):
    if not session_id:
        return None
    pattern = os.path.join(
        KIMI_HOME, "sessions", "*", session_id, "agents", "main", "wire.jsonl"
    )
    hits = glob.glob(pattern)
    return hits[0] if hits else None


def session_usage(session_id):
    """累计 main agent 会话日志里的 usage.record（与 /usage 面板同源）。"""
    path = find_wire(session_id)
    if path is None:
        return None
    cache_path = state_path("usage-" + session_id)
    zero = {"read": 0, "write": 0, "other": 0, "out": 0, "requests": 0}
    state = read_state(cache_path)
    if state.get("path") != path or not isinstance(state.get("totals"), dict):
        state = {"path": path, "offset": 0, "totals": dict(zero)}
    else:
        for key, value in zero.items():
            state["totals"].setdefault(key, value)

    try:
        size = os.path.getsize(path)
        if size < int(state.get("offset") or 0):
            state["offset"] = 0
            state["totals"] = dict(zero)
        if size <= int(state.get("offset") or 0):
            return state["totals"]

        totals = state["totals"]
        offset = int(state["offset"])
        start_offset = offset          # 只有真读到新行才值得落盘（否则每秒白写一次状态文件）
        deadline = time.monotonic() + USAGE_BUDGET_S
        with open(path, "rb") as fh:
            fh.seek(offset)
            pending = b""
            while time.monotonic() < deadline:
                chunk = fh.read(READ_CHUNK)
                if not chunk:
                    break
                pending += chunk
                cut = pending.rfind(b"\n") + 1
                if cut <= 0:
                    continue
                for line in pending[:cut].split(b"\n"):
                    if b'"usage.record"' in line:
                        _add_usage(totals, line)
                offset += cut
                pending = pending[cut:]
        state["offset"] = offset
        state["totals"] = totals
        if offset != start_offset:
            write_state(cache_path, state)
        return totals
    except Exception:
        return state.get("totals")


def _add_usage(totals, line):
    try:
        record = json.loads(line)
    except Exception:
        return
    if record.get("type") != "usage.record":
        return
    usage = record.get("usage") or {}
    totals["read"] += int(usage.get("inputCacheRead") or 0)
    totals["write"] += int(usage.get("inputCacheCreation") or 0)
    totals["other"] += int(usage.get("inputOther") or 0)
    totals["out"] += int(usage.get("output") or 0)
    totals["requests"] += 1


# -------------------------------------------------------------------- balance


def load_config():
    try:
        import tomllib

        with open(CONFIG_PATH, "rb") as fh:
            return tomllib.load(fh)
    except Exception:
        pass
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return _parse_config(fh.read())
    except Exception:
        return {}


def _parse_config(text):
    """tomllib 不可用时的兜底：只认 [providers.x] / [models."y"] 里的字符串字段。"""
    config = {"providers": {}, "models": {}}
    section = config
    for raw in text.splitlines():
        line = raw.strip()
        header = re.match(r"^\[(.+)\]$", line)
        if header:
            parts = [p.strip() for p in header.group(1).replace('"', "").split(".")]
            section = None
            if parts[0] == "providers" and len(parts) >= 2:
                section = config["providers"].setdefault(parts[1], {})
            elif parts[0] == "models" and len(parts) >= 2:
                section = config["models"].setdefault(parts[1], {})
            continue
        if section is None:
            continue
        field = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*"(.*)"\s*$', line)
        if field:
            section[field.group(1)] = field.group(2)
    return config


def resolve_provider(config, display_name):
    models = config.get("models") or {}
    entry = None
    for model in models.values():
        if isinstance(model, dict) and display_name and model.get("display_name") == display_name:
            entry = model
            break
    if entry is None:
        default = models.get(config.get("default_model"))
        entry = default if isinstance(default, dict) else None
    if entry is None:
        return None, None
    name = entry.get("provider")
    provider = (config.get("providers") or {}).get(name)
    return name, provider if isinstance(provider, dict) else None


def balance_api(base_url):
    host = re.sub(r"^https?://", "", base_url or "").split("/")[0].lower()
    for needle, path, flavor in BALANCE_APIS:
        if needle in host:
            return path, flavor
    return None, None


def balance_label(provider_name, payload):
    config = load_config()
    name, provider = resolve_provider(config, payload.get("model"))
    if provider is None:
        return None
    name = name or provider_name or "provider"
    path, flavor = balance_api(provider.get("base_url"))
    if path is None:
        return None

    cache_path = state_path("balance-" + name)
    state = read_state(cache_path)
    now = time.time()
    attempted = float(state.get("attempted") or 0)
    wait = BALANCE_RETRY_S if state.get("error") else BALANCE_TTL_S
    if now - attempted > wait:
        # 先落盘再把请求丢给后台，避免请求期间每秒重开一个子进程
        state["attempted"] = now
        write_state(cache_path, state)
        spawn_balance_refresh(name)
    state = read_state(cache_path)

    amount = state.get("amount")
    if amount is None:
        return None
    currency = state.get("currency") or ""
    symbol = {"CNY": "\u00a5", "USD": "$"}.get(currency.upper(), "")
    text = "%s%.2f" % (symbol, amount) if symbol else "%.2f %s" % (amount, currency)
    age = now - float(state.get("ts") or 0)
    if state.get("error") and age > BALANCE_TTL_S:
        text += dim(" (stale)")
    return dim("bal ") + bold(text)


def spawn_balance_refresh(provider_name):
    import subprocess          # 惰性导入：主路径（每秒一次）不该为它付启动成本

    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--refresh-balance", provider_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # 脱离进程组：kimi-code 超时会 SIGKILL 整个进程组，不能连累后台刷新
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        pass


def refresh_balance(provider_name):
    import urllib.request      # 只在后台刷新子进程里用到，别拖慢主路径

    config = load_config()
    provider = (config.get("providers") or {}).get(provider_name)
    cache_path = state_path("balance-" + provider_name)
    state = read_state(cache_path)
    state["attempted"] = time.time()
    if not isinstance(provider, dict):
        state["error"] = "provider %s not found" % provider_name
        write_state(cache_path, state)
        return
    base = (provider.get("base_url") or "").rstrip("/")
    path, flavor = balance_api(base)
    try:
        request = urllib.request.Request(
            base + path,
            headers={
                "Authorization": "Bearer " + (provider.get("api_key") or ""),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
        amount, currency = _extract_balance(flavor, data)
        state.update({"amount": amount, "currency": currency, "ts": time.time()})
        state.pop("error", None)
    except Exception as exc:
        state["error"] = str(exc)[:120]
    write_state(cache_path, state)


def _extract_balance(flavor, data):
    if flavor == "deepseek":
        info = (data.get("balance_infos") or [{}])[0]
        return float(info.get("total_balance") or 0), info.get("currency") or "CNY"
    if flavor == "moonshot":
        info = data.get("data") or {}
        return float(info.get("available_balance") or 0), info.get("currency") or "CNY"
    raise ValueError("unsupported provider")


# ---------------------------------------------------------------------- render


def mode_badge(payload):
    parts = []
    permission = payload.get("permissionMode")
    if permission == "manual":                      # 显示名取自 CLI 的 PERMISSION_MODE_DISPLAY_NAMES
        parts.append(color(33, bold("Always Ask")))
    elif permission == "yolo":
        parts.append(color(33, bold("Ask When Needed")))
    elif permission == "auto":
        parts.append(color(33, bold("Never Ask")))
    if payload.get("planMode"):
        parts.append(color(34, bold("plan")))
    return " ".join(parts)


def usage_totals(totals):
    if not totals:
        return None
    read = int(totals.get("read") or 0)
    write = int(totals.get("write") or 0)
    other = int(totals.get("other") or 0)
    total = read + write + other
    if total <= 0:
        return None
    return read, write, other, total


def cache_segment(totals):
    """命中率排在余额之前——窄终端截断时先保住这两个数字。"""
    values = usage_totals(totals)
    if values is None:
        return None
    read, _write, _other, total = values
    rate = int(round(read * 100.0 / total))
    tone = 32 if rate >= 80 else (33 if rate >= 50 else 31)
    return "%s %s" % (dim("cache"), color(tone, bold("%d%%" % rate)))


def token_detail(totals):
    values = usage_totals(totals)
    if values is None:
        return None
    read, write, other, _total = values
    detail = ["cached " + format_tokens(read)]
    if write > 0:
        detail.append("written " + format_tokens(write))
    detail.append("uncached " + format_tokens(other))
    return dim(" \u00b7 ".join(detail))


def location_segment(payload):
    cwd = payload.get("cwd") or ""
    if not cwd:
        return None
    shown = cwd
    if cwd == HOME:
        shown = "~"
    elif cwd.startswith(HOME + os.sep):
        shown = "~" + cwd[len(HOME):]
    segments = [part for part in shown.split(os.sep) if part]
    if len(segments) > 3:
        shown = "\u2026/" + "/".join(segments[-2:])
    branch = payload.get("gitBranch")
    return shown + (dim(" " + branch) if branch else "")


def build_line(payload):
    parts = []
    badge = mode_badge(payload)
    if badge:
        parts.append(badge)
    if payload.get("model"):
        parts.append(payload["model"])
    totals = session_usage(payload.get("sessionId"))
    segment = cache_segment(totals)
    if segment:
        parts.append(segment)
    segment = balance_label(None, payload)
    if segment:
        parts.append(segment)
    segment = token_detail(totals)
    if segment:
        parts.append(segment)
    segment = location_segment(payload)
    if segment:
        parts.append(segment)
    return "  ".join(parts)


# --- exa-bridge 兜底（Windows）------------------------------------------------
# 桥被杀过两次（见 skill 的 references/web-tools-exa.md 2.5），而启动文件夹的自启不会把
# 它拉活（macOS 的 launchd / Linux 的 systemd 都会）。这条命令在会话里每秒跑一次，顺手
# 探活最省事：只做 TCP connect（不发请求、不读响应），拒连就 detached 拉起。
BRIDGE_WATCH_INTERVAL_S = 30
BRIDGE_RELAUNCH_COOLDOWN_S = 60
BRIDGE_PROBE_TIMEOUT_S = 0.05


def bridge_endpoint():
    """桥的 host:port 取自 config.toml 的 services.moonshot_search.base_url，取不到用默认。"""
    services = load_config().get("services") or {}
    url = (services.get("moonshot_search") or {}).get("base_url") or ""
    match = re.search(r"//([^/\s]+)", url)
    host, _, port = (match.group(1) if match else "127.0.0.1:8787").partition(":")
    return host or "127.0.0.1", int(port or 8787)


def relaunch_bridge():
    """拉起桥：优先直接跑 launch.pyw，没有才退回启动文件夹里的快捷方式。

    两条路等价（快捷方式就是 pythonw.exe 跑同一个 launch.pyw），但 ShellExecute 走快捷
    方式实测 ~240ms、Popen 只要 ~34ms——这条命令一秒一次、总共只有 300ms 预算，能省就省。
    """
    import subprocess

    launch = os.path.join(KIMI_HOME, "exa-bridge", "launch.pyw")
    try:
        if os.path.exists(launch):
            subprocess.Popen([sys.executable, launch],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return "launch.pyw"
        lnk = os.path.join(os.environ.get("APPDATA") or "", "Microsoft", "Windows",
                           "Start Menu", "Programs", "Startup", "kimi-exa-bridge.lnk")
        if os.path.exists(lnk):
            os.startfile(lnk)                       # 退路：等价于双击那个快捷方式
            return "shortcut"
    except Exception:
        pass
    return None


def watch_bridge():
    """Windows 兜底：桥挂了就拉起来。节流，且只在 runner 调用时生效——手动跑不误触发。

    门闩用 KIMI_CODE_STATUS_LINE：那是 kimi-code 的 status line runner 给子进程注入的
    环境变量，所以 verify.py 的状态栏行为自测、手工调试都不会顺带把桥拉起来。
    """
    if os.name != "nt" or os.environ.get("KIMI_CODE_STATUS_LINE") != "1":
        return
    import socket

    now = time.time()
    path = state_path("bridge-watch")
    state = read_state(path)
    if now - float(state.get("checked") or 0) < BRIDGE_WATCH_INTERVAL_S:
        return
    state["checked"] = now
    try:
        host, port = bridge_endpoint()
    except Exception:
        host, port = "127.0.0.1", 8787
    try:
        socket.create_connection((host, port), timeout=BRIDGE_PROBE_TIMEOUT_S).close()
        state["last_ok"] = now
        state.pop("last_error", None)
        state.pop("relaunched", None)
        write_state(path, state)
        return
    except Exception as exc:
        state["last_error"] = "%s: %s" % (type(exc).__name__, exc)
    relaunch = now - float(state.get("relaunched") or 0) >= BRIDGE_RELAUNCH_COOLDOWN_S
    if relaunch:
        state["relaunched"] = now
    write_state(path, state)        # 先落盘：拉起动作可能被 runner 的 300ms 超时打断，
    if relaunch:                    # 冷却时间写不进去就会变成每秒重试拉起
        state["relaunch_mode"] = relaunch_bridge()
        write_state(path, state)


def main():
    if "--refresh-balance" in sys.argv:
        index = sys.argv.index("--refresh-balance")
        if index + 1 < len(sys.argv):
            refresh_balance(sys.argv[index + 1])
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    if not isinstance(payload, dict) or not payload:
        return 0
    try:
        line = build_line(payload)
    except Exception:
        return 0
    if line:
        sys.stdout.write(line + "\n")
        try:
            sys.stdout.flush()                      # 先把第一行送出去，再做兜底探活
        except Exception:
            pass
    watch_bridge()
    return 0


if __name__ == "__main__":
    sys.exit(main())
