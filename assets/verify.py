#!/usr/bin/env python3
"""kimi-code 落地体检（只读）：一条命令跑完 Exa 通道 + 配置 + MCP + 工具清单 + 钩子 / 状态栏 / 补丁脚本行为自测 + kimi doctor + 资产一致性。

用法：
  python3 verify.py                 # 体检本机（~/.kimi-code 或 $KIMI_CODE_HOME）
  python3 verify.py --e2e           # 额外起一个 kimi -p 做端到端（慢，20–60s）
  python3 verify.py --skill-dir ~/Desktop/kimi-code-setup
                                    # 指定 skill 目录以比对 assets/exa-bridge.py 是否漂移
退出码：0 全通过 / 1 有告警 / 2 有失败

这个脚本只读：不改任何配置文件（--e2e 除外，它会新起一个会话，产生 session 文件）。
永不打印密钥明文。出网不通时会把"桥失败"降级为告警——先分清是网络问题还是配置问题。
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HEADER_RE = re.compile(r"^\s*(\[\[?[^\]]+\]\]?)\s*(?:#.*)?$")
RESULTS = []
NET_UP = True


def add(level, text):
    RESULTS.append((level, text))
    print("[%s] %s" % (level, text))


def mask(secret):
    s = (secret or "").strip()
    return "（空）" if not s else "%s…（%d 字符）" % (s[:6], len(s))


def home_dir():
    return Path(os.environ.get("KIMI_CODE_HOME") or (Path.home() / ".kimi-code"))


def load_toml(path):
    try:
        import tomllib
    except ImportError:
        return None, "Python <3.11：跳过真解析，只做文本级检查"
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh), ""
    except Exception as exc:
        return None, "TOML 解析失败：%s" % exc


def duplicate_tables(text):
    seen, dups = set(), []
    for line in text.splitlines():
        m = HEADER_RE.match(line)
        if not m:
            continue
        raw = m.group(1)
        if raw.startswith("[["):
            continue
        name = raw[1:-1].strip()
        if name in seen:
            dups.append(name)
        seen.add(name)
    return sorted(set(dups))


def http_get(url, timeout=8):
    with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def http_post_json(url, payload, token=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, "%s: %s" % (type(exc).__name__, exc)


def recent_wires(home, limit=5):
    files = glob.glob(str(home / "sessions" / "*" / "session_*" / "agents" / "main" / "wire.jsonl"))
    return sorted(files, key=os.path.getmtime, reverse=True)[:limit]


def last_tools(wire):
    names = None
    with open(wire, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"llm.tools_snapshot"' not in line:
                continue
            try:
                names = [t["name"] for t in json.loads(line)["tools"]]
            except Exception:
                pass
    return names


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def probe(url, timeout=6):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as exc:          # 4xx/5xx 也算通：TLS+HTTP 走通了
        return exc.code
    except Exception:
        return 0


def check_network():
    """先探出网，并区分"代理出口挂了"和"整机没网"——桥的失败不该被算成 kimi-code 配置错。"""
    global NET_UP
    need_proxy = ["https://api.exa.ai", "https://mcp.exa.ai/mcp"]
    proxy_status = [(u, probe(u, 8)) for u in need_proxy]
    hit = [u for u, code in proxy_status if code]
    if hit:
        add("PASS", "出网：%s 可达" % hit[0])
        return
    NET_UP = False
    direct = ["https://api.deepseek.com", "https://www.baidu.com"]
    direct_hit = [u for u in direct if probe(u, 6)]
    if direct_hit:
        add("FAIL", "代理出口不通：要走代理的域名（%s）全部超时，直连的 %s 却正常 —— "
                    "去代理软件里换节点 / 更新订阅 / 确认选中了可用节点（或 TUN 模式开着）；"
                    "这不是 kimi-code 的配置问题" % ("、".join(need_proxy), "、".join(direct_hit)))
    else:
        add("FAIL", "整机出网不通：连直连域名（%s）也全超时 —— 先查 Wi-Fi / 网线 / DNS，再复检"
            % "、".join(direct))


def check_config(home):
    cfg_path = home / "config.toml"
    if not cfg_path.exists():
        add("FAIL", "配置：找不到 %s" % cfg_path)
        return {}
    text = cfg_path.read_text(encoding="utf-8", errors="replace")
    dups = duplicate_tables(text)
    if dups:
        add("FAIL", "配置：重复表 %s —— 这会让整份 config.toml 失效，"
                    "kimi-code 会报 “No model configured”" % ", ".join(dups))
    cfg, err = load_toml(cfg_path)
    if cfg is None:
        add("FAIL", "配置：%s" % err)
        return {}
    add("PASS", "配置：%s 可解析（%d 行）" % (cfg_path, len(text.splitlines())))

    model = cfg.get("default_model") or "（未设置）"
    add("PASS" if cfg.get("default_model") else "WARN", "默认模型：%s" % model)
    providers = sorted((cfg.get("providers") or {}).keys())
    add("PASS" if providers else "WARN", "provider：%s" % (", ".join(providers) or "（无）"))

    thinking = cfg.get("thinking") or {}
    effort = thinking.get("effort") or "（未设置）"
    add("PASS" if thinking.get("effort") else "WARN", "思考强度：%s" % effort)
    mode = cfg.get("default_permission_mode") or "（未设置）"
    add("PASS" if mode != "（未设置）" else "WARN", "默认权限模式：%s" % mode)

    disabled = (cfg.get("tools") or {}).get("disabled") or []
    bad = [n for n in disabled if str(n).lower() in ("websearch", "fetchurl")]
    add("FAIL" if bad else "PASS",
        "工具开关：disabled=%s%s" % (disabled or "[]", "（把内置联网工具关了）" if bad else ""))
    return cfg


def is_local_endpoint(url):
    """本机 exa-bridge 端点判定：127.0.0.1 / localhost / [::1]。"""
    text = (url or "").lower()
    return "127.0.0.1" in text or "localhost" in text or "[::1]" in text


def check_services(cfg):
    services = cfg.get("services") or {}
    search = services.get("moonshot_search") or {}
    fetch = services.get("moonshot_fetch") or {}
    base_url = search.get("base_url") or ""
    token = search.get("api_key") or ""
    if not search:
        add("WARN", "services.moonshot_search 缺失 —— 内置 WebSearch 会走 Kimi 托管服务（需 /login）")
        return "", ""
    add("PASS", "services.moonshot_search：%s（令牌 %s）" % (base_url, mask(token)))
    add("PASS" if fetch else "WARN",
        "services.moonshot_fetch：%s" % (fetch.get("base_url") or "缺失"))
    if not is_local_endpoint(base_url):
        add("WARN", "内置联网工具的端点不是本机 exa-bridge（当前 %s）—— 跳过桥检查；"
                    "若确为自建远端桥，请用 curl 单独验证" % base_url)
    return base_url, token


def check_bridge(base_url, token):
    base = base_url.rstrip("/")
    root = base[: -len("/search")] if base.endswith("/search") else base
    port = re.search(r":(\d+)", root)
    health_url = "%s/health" % root
    try:
        status, body = http_get(health_url)
    except Exception as exc:
        add("FAIL", "桥 /health 打不通（%s）：%s —— 先把它救活（见 references/web-tools-exa.md 第 3 步）"
            % (health_url, exc))
        return
    try:
        info = json.loads(body)
    except Exception:
        add("FAIL", "桥 /health 返回了非 JSON：%s" % body[:120])
        return
    add("PASS", "桥在跑：%s（端口 %s，每次搜 %s 条）" % (health_url, port.group(1) if port else "?", info.get("results")))
    if info.get("key"):
        add("PASS", "桥已拿到 Exa key")
    else:
        add("WARN", "桥没拿到 Exa key（设 EXA_API_KEY，或在 mcp.json 写 mcpServers.exa.headers.x-api-key）")
    if not info.get("status"):
        add("WARN", "桥没有 /status 端点（旧版脚本）—— kimi web 端的小面板用不了；"
                    "部署 assets/exa-bridge.py 后重启桥（macOS: launchctl kickstart -k）")
    else:
        try:
            _, status_body = http_get("%s/status" % root, timeout=15)
            data = json.loads(status_body)
            if not data.get("ok"):
                add("WARN", "桥 /status 返回 ok=false：%s（web 端面板会显示不出来）"
                    % str(data.get("error"))[:110])
            else:
                bits = []
                if data.get("cache") is not None:
                    bits.append("cache %d%%" % data["cache"])
                if data.get("balance"):
                    bits.append("bal %s" % data["balance"])
                add("PASS" if bits else "WARN",
                    "桥 /status：%s" % ("，".join(bits) or "暂无数据（新会话还没用量？）"))
        except Exception as exc:
            add("WARN", "桥 /status 打不通：%s" % exc)
    if not base.endswith("/search"):
        return
    status, body = http_post_json(base, {"text_query": "exa.ai pricing"}, token=token, timeout=35)
    if status == 401:
        add("FAIL", "直打桥搜索 → 401：config.toml 的 api_key 与桥的 EXA_BRIDGE_TOKEN 不一致")
    elif status == 200 and '"search_results"' in body:
        try:
            n = len(json.loads(body).get("search_results") or [])
        except Exception:
            n = -1
        add("PASS" if n > 0 else "WARN", "直打桥搜索 → 200，返回 %d 条" % n)
    elif not NET_UP:
        add("WARN", "直打桥搜索失败（HTTP %s），但当前出网不通 —— 先按网络问题处理，"
                    "网络恢复后再跑一次本脚本就知道桥是否无辜" % status)
    else:
        add("FAIL", "直打桥搜索 → HTTP %s：%s" % (status, body[:200]))


def check_mcp(home):
    path = home / "mcp.json"
    if not path.exists():
        add("WARN", "MCP：没有 %s（MCP 通道未配置）" % path)
        return
    try:
        servers = json.loads(path.read_text(encoding="utf-8")).get("mcpServers") or {}
    except Exception as exc:
        add("FAIL", "MCP：mcp.json 解析失败 %s" % exc)
        return
    add("PASS", "MCP：已配置 %s" % (", ".join(sorted(servers)) or "（无）"))
    exa = servers.get("exa")
    if exa:
        has_key = any(k.lower() == "x-api-key" for k in (exa.get("headers") or {}))
        add("PASS", "MCP exa：%s（%s）" % (exa.get("url"),
            "带 key，走自己的额度" if has_key else "匿名模式，不带 key"))
    else:
        add("WARN", "MCP exa 缺失 —— 需要批量抓取/agent_run 时用不了")
    cu = servers.get("kimi-cu")
    if cu:
        cmd = cu.get("command") or ""
        ok = (not cmd) or Path(cmd).exists()
        add("PASS" if ok else "WARN",
            "MCP kimi-cu：%s%s" % (cmd or cu.get("url"),
                                   "" if ok else "（文件不存在，KimiCU 装了没？）"))
    else:
        add("WARN", "MCP kimi-cu 缺失 —— 无法操作本机浏览器 / App 界面")


def check_tools(home):
    wires = recent_wires(home, 5)
    if not wires:
        add("WARN", "工具清单：还没找到会话日志，先跑一次 kimi 再看")
        return
    # 单个新会话（尤其 kimi -p）可能在 MCP 握手完成前就拍了快照，只认最新一个会误报；
    # 取最近几个带快照会话的并集，覆盖的是"这台机器现在能用哪些工具"。
    names, used = [], 0
    for wire in wires:
        found = last_tools(wire) or []
        if not found:
            continue
        used += 1
        for name in found:
            if name not in names:
                names.append(name)
        if used >= 3:
            break
    if not names:
        add("WARN", "工具清单：最近 %d 个会话里都没有 tools_snapshot 记录" % len(wires))
        return
    for label, prefix, level in (("WebSearch", "WebSearch", "FAIL"),
                                 ("FetchURL", "FetchURL", "FAIL"),
                                 ("mcp__exa__", "mcp__exa__", "WARN"),
                                 ("mcp__kimi-cu__", "mcp__kimi-cu__", "WARN")):
        found = [n for n in names if n.startswith(prefix)]
        add("PASS" if found else level, "工具 %s：%s" % (label, "%d 个" % len(found) if found else "缺失"))
    add("PASS", "工具总数：%d（最近 %d 个会话快照的并集）" % (len(names), used))


LOG_RE = re.compile(r"^(\S+)\s+(WARN|ERROR|INFO)\s+(.*)$")


def check_logs(home):
    """扫最近日志：重复出现的 WARN 往往是"后台在空转"的信号，别让它悄悄烂着。"""
    import collections
    import datetime
    log = home / "logs" / "kimi-code.log"
    if not log.exists():
        add("WARN", "日志：找不到 %s" % log)
        return
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-3000:]
    except Exception as exc:
        add("WARN", "日志：读不动 %s（%s）" % (log, exc))
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    recent = []
    for line in lines:
        m = LOG_RE.match(line)
        if not m:
            continue
        try:
            when = datetime.datetime.strptime(
                m.group(1)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        recent.append((when, m.group(2), m.group(3)))
    last10 = [r for r in recent if (now - r[0]).total_seconds() <= 600]
    errs = [r for r in last10 if r[1] == "ERROR"]
    warns = [r for r in last10 if r[1] == "WARN"]
    if errs:
        add("WARN", "日志：最近 10 分钟 %d 条 ERROR，最后一条：%s" % (len(errs), errs[-1][2][:110]))
    dupes = collections.Counter(re.sub(r"\d+", "#", w[2])[:80] for w in warns)
    hot, n = (dupes.most_common(1)[0] if dupes else ("", 0))
    if n >= 3:
        age = int((now - max(w[0] for w in warns)).total_seconds())
        text = "日志：最近 10 分钟 %d 条重复警告「%s」" % (n, hot)
        if age <= 180:
            add("WARN", text + ("—— 最后一条 %d 秒前，仍在发生：后台任务在空转。最常见是会话索引重建失败"
                                "（`session index reconciliation failed`，实验特性 minidb read-model）；"
                                "它只是加速用的读模型，不影响正常干活，成功一次会打印 `repaired drift` 自愈；"
                                "持续刷屏可设 `KIMI_CODE_EXPERIMENTAL_PERSISTENCE_MINIDB_READMODEL=false` 关掉（实测有效）" % age))
        else:
            add("INFO", text + "，但最后一条在 %d 分钟前——已经停了（通常重启或自愈后恢复）" % (age // 60))
    elif not warns and not errs:
        add("PASS", "日志：最近 10 分钟 0 条 WARN / 0 条 ERROR")


def hook_blocks_correctly(script):
    """用临时 KIMI_CODE_HOME + 假会话日志验证守卫脚本：全 done 拦、清空放行。不碰真实数据。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        probe_home = Path(tmp) / "home"
        wire_dir = Path(tmp) / "sess" / "agents" / "main"
        wire_dir.mkdir(parents=True)
        probe_home.mkdir()
        (probe_home / "session_index.jsonl").write_text(
            json.dumps({"sessionId": "probe", "sessionDir": str(wire_dir.parent.parent)}) + "\n",
            encoding="utf-8")
        wire = wire_dir / "wire.jsonl"

        def run(todos):
            wire.write_text(
                json.dumps({"created_at": 1, "event": {"type": "step.begin", "turnId": "t1"}}) + "\n"
                + json.dumps({"created_at": 2, "event": {"type": "tool.call", "name": "TodoList",
                                                         "turnId": "t1", "args": {"todos": todos}}}) + "\n",
                encoding="utf-8")
            env = dict(os.environ, KIMI_CODE_HOME=str(probe_home))
            proc = subprocess.run([sys.executable, str(script)], input='{"session_id": "probe"}',
                                  capture_output=True, text=True, timeout=15, env=env)
            return proc.returncode

        blocked = run([{"title": "a", "status": "done"}])
        cleared = run([])
    if blocked == 2 and cleared == 0:
        return True, "全 done → 拦住（exit 2），清空 → 放行（exit 0）"
    return False, "行为不符：全 done → exit %s（期望 2），清空 → exit %s（期望 0）" % (blocked, cleared)


def check_hooks(home, cfg):
    hooks = (cfg or {}).get("hooks") or []
    if not hooks:
        add("WARN", "钩子：config.toml 里没有 [[hooks]] —— Todo 面板守卫未装（见 SKILL.md 第 6 步）")
        return
    add("PASS", "钩子：%d 条（%s）" % (len(hooks), "、".join(sorted(str(h.get("event")) for h in hooks))))
    if not [h for h in hooks if "todo-panel-guard.py" in str(h.get("command", ""))]:
        add("WARN", "钩子：没装 Todo 面板守卫 —— 面板烂尾没人拦（见 SKILL.md 第 6 步）")
        return
    script = home / "hooks" / "todo-panel-guard.py"
    if not script.exists():
        add("FAIL", "钩子：规则指向 todo-panel-guard.py，但 %s 不存在" % script)
        return
    ok, detail = hook_blocks_correctly(script)
    add("PASS" if ok else "FAIL", "钩子脚本行为：%s" % detail)


def statusline_behaves(script):
    """用临时 KIMI_CODE_HOME + 假会话日志验证状态栏脚本：read 900 / uncached 100 → cache 90%。

    临时 home 里没有 config.toml，所以脚本不会去找 provider、也就不会触发余额联网请求。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        probe_home = Path(tmp) / "home"
        wire_dir = probe_home / "sessions" / "wd_probe" / "session_probe" / "agents" / "main"
        wire_dir.mkdir(parents=True)
        (wire_dir / "wire.jsonl").write_text(
            "".join(json.dumps({
                "type": "usage.record", "agentId": "main", "model": "probe/model",
                "usage": {"inputOther": other, "output": 7,
                          "inputCacheRead": cached, "inputCacheCreation": 0},
            }) + "\n" for cached, other in ((500, 60), (400, 40))),
            encoding="utf-8")
        payload = json.dumps({"model": "Probe Model", "cwd": "/tmp", "permissionMode": "yolo",
                              "planMode": False, "sessionId": "session_probe"})
        proc = subprocess.run([sys.executable, str(script)], input=payload, capture_output=True,
                              text=True, timeout=15, env=dict(os.environ, KIMI_CODE_HOME=str(probe_home)))
    plain = re.sub(r"\x1b\[[0-9;]*m", "", proc.stdout or "")
    first = plain.strip().splitlines()[0] if plain.strip() else ""
    if proc.returncode == 0 and "cache 90%" in plain:
        return True, "输出含 cache 90%（read 900 / uncached 100）"
    return False, "退出码 %s，第一行：%s" % (proc.returncode, first[:90] or "（空）")


def check_statusline(home):
    tui = home / "tui.toml"
    if not tui.exists():
        add("WARN", "状态栏：没有 %s（还没启动过 kimi？见 SKILL.md 第 7 步）" % tui)
        return
    cfg, err = load_toml(tui)
    if cfg is None:
        text = tui.read_text(encoding="utf-8", errors="replace")
        if err.startswith("TOML 解析失败"):
            add("FAIL", "状态栏：tui.toml %s" % err)
        elif "statusline.py" in text:
            add("PASS", "状态栏：tui.toml 里配了 statusline.py（%s）" % err)
        else:
            add("WARN", "状态栏：tui.toml 里没有 [status_line] 配置（%s）" % err)
        return
    add("PASS", "状态栏：tui.toml 可解析")
    command = str(((cfg.get("status_line") or {}).get("command")) or "").strip()
    if not command:
        add("WARN", "状态栏：没配 [status_line].command —— footer 走内置布局（见 SKILL.md 第 7 步）")
        return
    if "statusline.py" not in command:
        add("INFO", "状态栏：command 指向别的脚本：%s" % command[:90])
        return
    add("PASS", "状态栏：command = %s" % command)
    script = home / "statusline.py"
    if not script.exists():
        add("FAIL", "状态栏：command 指向 statusline.py，但 %s 不存在" % script)
        return
    ok, detail = statusline_behaves(script)
    add("PASS" if ok else "FAIL", "状态栏脚本行为：%s" % detail)


def check_doctor():
    """kimi 自带的配置校验：config.toml / tui.toml 能否被 CLI 读进去。"""
    exe = shutil.which("kimi")
    if not exe:
        return
    try:
        proc = subprocess.run([exe, "doctor"], capture_output=True, text=True, timeout=40)
    except Exception as exc:
        add("WARN", "kimi doctor：跑不起来 %s" % exc)
        return
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    last = text.splitlines()[-1] if text else "（无输出）"
    add("PASS" if proc.returncode == 0 else "FAIL",
        "kimi doctor：退出码 %s（%s）" % (proc.returncode, last[:120]))


def patch_script_behaves(script):
    """临时文件上验证 patch-config：set 新增/改值、ensure-hook 幂等、unset 删键与清空表头。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.toml"
        cfg.write_text('[services.moonshot_search]\nbase_url = "http://127.0.0.1:8787/search"\n',
                       encoding="utf-8")

        def run(*args):
            return subprocess.run([sys.executable, str(script), "--file", str(cfg), *args],
                                  capture_output=True, text=True, timeout=15)

        results = {}
        results["set 新增"] = run("set", "services.moonshot_search.api_key", "abc").returncode == 0 \
            and 'api_key = "abc"' in cfg.read_text(encoding="utf-8")
        results["set 改值"] = run("set", "services.moonshot_search.api_key", "def").returncode == 0 \
            and cfg.read_text(encoding="utf-8").count("api_key") == 1
        results["ensure-hook 幂等"] = run("ensure-hook", "Stop", "python3 /tmp/guard.py").returncode == 0 \
            and run("ensure-hook", "Stop", "python3 /tmp/guard.py").returncode == 0 \
            and cfg.read_text(encoding="utf-8").count("[[hooks]]") == 1
        results["unset 删键"] = run("unset", "services.moonshot_search.api_key").returncode == 0 \
            and "api_key" not in cfg.read_text(encoding="utf-8")
        results["unset 清空表头"] = run("unset", "services.moonshot_search.base_url").returncode == 0 \
            and "[services.moonshot_search]" not in cfg.read_text(encoding="utf-8")
        bad = [name for name, ok in results.items() if not ok]
    if bad:
        return False, "失败步骤：%s" % "、".join(bad)
    return True, "set 新增/改值、ensure-hook 幂等、unset 删键与清空表头 全过"


def check_patch_script(skill_dir):
    script = Path(skill_dir) / "assets" / "patch-config.py"
    if not script.exists():
        add("WARN", "补丁脚本：skill 里没有 %s" % script)
        return
    ok, detail = patch_script_behaves(script)
    add("PASS" if ok else "FAIL", "补丁脚本行为：%s" % detail)


def check_assets(skill_dir, home):
    if not skill_dir:
        add("WARN", "资产比对：没给 --skill-dir，跳过")
        return
    src = Path(skill_dir) / "assets" / "exa-bridge.py"
    dst = home / "exa-bridge" / "exa-bridge.py"
    if not src.exists():
        add("WARN", "资产比对：skill 里没有 %s" % src)
        return
    if not dst.exists():
        add("WARN", "资产比对：本机没有 %s（第 2 步还没做？）" % dst)
        return
    a, b = sha12(src), sha12(dst)
    add("PASS" if a == b else "WARN",
        "桥脚本一致性：skill=%s 本机=%s%s" % (a, b, "" if a == b else " —— 有漂移，改完记得两边同步"))
    gsrc = Path(skill_dir) / "assets" / "todo-panel-guard.py"
    gdst = home / "hooks" / "todo-panel-guard.py"
    if gsrc.exists() and gdst.exists():
        ga, gb = sha12(gsrc), sha12(gdst)
        add("PASS" if ga == gb else "WARN",
            "守卫脚本一致性：skill=%s 本机=%s%s" % (ga, gb, "" if ga == gb else " —— 有漂移，改完记得两边同步"))
    elif gsrc.exists() and not gdst.exists():
        add("WARN", "守卫脚本：本机没装 %s（SKILL.md 第 6 步还没做？）" % gdst)
    ssrc = Path(skill_dir) / "assets" / "statusline.py"
    sdst = home / "statusline.py"
    if ssrc.exists() and sdst.exists():
        sa, sb = sha12(ssrc), sha12(sdst)
        add("PASS" if sa == sb else "WARN",
            "状态栏脚本一致性：skill=%s 本机=%s%s" % (sa, sb, "" if sa == sb else " —— 有漂移，改完记得两边同步"))
    elif ssrc.exists() and not sdst.exists():
        add("WARN", "状态栏脚本：本机没装 %s（SKILL.md 第 7 步还没做？）" % sdst)


def check_trigger_chain(home):
    """skill 若不在自动发现路径，就得靠 AGENTS.md 指路；这条链断了会表现为"skill 突然不生效"。"""
    installed = home / "skills" / "kimi-code-setup" / "SKILL.md"
    agents = home / "AGENTS.md"
    if installed.exists():
        add("PASS", "触发链：skill 已在 %s（新会话会自动发现）" % installed.parent)
        return
    text = agents.read_text(encoding="utf-8", errors="replace") if agents.exists() else ""
    if "kimi-code-setup" in text:
        add("PASS", "触发链：skill 不在 skills/ 里，靠 %s 的指路（说「调试 kimi-code」仍能找到）" % agents)
    else:
        add("WARN", "触发链：skill 既不在 %s，%s 里也没有指路 —— 会话不会自动找到它；"
                    "把目录拷进 skills/，或在 AGENTS.md 里加一条触发约定" % (home / "skills", agents))


def run_e2e(prompt, timeout):
    exe = shutil.which("kimi")
    if not exe:
        add("WARN", "端到端：PATH 里找不到 kimi")
        return
    add("INFO", "端到端：正在跑 `kimi -p`（最长 %ds）…" % timeout)
    log = home_dir() / "exa-bridge" / "bridge.log"
    before = log.stat().st_size if log.exists() else 0
    try:
        proc = subprocess.run([exe, "-p", prompt], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        add("FAIL", "端到端：超时")
        return
    out = (proc.stdout or "").strip().splitlines()
    add("PASS" if proc.returncode == 0 else "FAIL",
        "端到端：退出码 %s，回答末行：%s" % (proc.returncode, out[-1][:100] if out else "（空）"))
    after = log.stat().st_size if log.exists() else 0
    add("PASS" if after > before else "WARN",
        "端到端：bridge.log %s（%d → %d 字节）%s" % ("有新增" if after > before else "没变化",
                                                    before, after,
                                                    "" if after > before else " —— 内置工具可能没走桥"))


def main():
    ap = argparse.ArgumentParser(description="kimi-code 落地体检（只读）")
    ap.add_argument("--skill-dir", default=str(Path(__file__).resolve().parent.parent),
                    help="skill 目录，用于比对 assets/exa-bridge.py（默认取本脚本的上级目录）")
    ap.add_argument("--e2e", action="store_true", help="额外跑一次端到端（慢）")
    ap.add_argument("--timeout", type=int, default=120, help="端到端超时秒数，默认 120")
    ap.add_argument("--skip-net", action="store_true", help="跳过出网探测")
    args = ap.parse_args()

    home = home_dir()
    add("INFO", "体检目录：%s" % home)
    exe = shutil.which("kimi")
    if exe:
        try:
            ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
            add("PASS", "CLI：%s" % (ver.stdout.strip() or ver.stderr.strip() or "（无输出）"))
        except Exception as exc:
            add("WARN", "CLI：版本查询失败 %s" % exc)
    else:
        add("FAIL", "PATH 里找不到 kimi —— 先装：见 SKILL.md 第 0 步")

    check_doctor()
    if not args.skip_net:
        check_network()
    cfg = check_config(home)
    if cfg:
        base_url, token = check_services(cfg)
        if base_url and is_local_endpoint(base_url):
            check_bridge(base_url, token)
    check_mcp(home)
    check_tools(home)
    check_hooks(home, cfg)
    check_statusline(home)
    check_logs(home)
    check_assets(args.skill_dir, home)
    check_patch_script(args.skill_dir)
    check_trigger_chain(home)
    if args.e2e:
        run_e2e("用内置 WebSearch 搜一下 exa.ai 的定价，一句话回答", args.timeout)

    fails = [t for lv, t in RESULTS if lv == "FAIL"]
    warns = [t for lv, t in RESULTS if lv == "WARN"]
    print("\n—— 合计：%d 项通过 / %d 项告警 / %d 项失败 ——"
          % (len([1 for lv, _ in RESULTS if lv == "PASS"]), len(warns), len(fails)))
    if fails:
        print("失败项：")
        for t in fails:
            print("  ✗ %s" % t)
        return 2
    return 1 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
