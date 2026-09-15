#!/usr/bin/env python3
"""Exa bridge for Kimi Code built-in WebSearch / FetchURL tools.

Kimi Code's built-in tools speak a fixed HTTP contract; this bridge translates
that contract to Exa's REST API so the tools appear under their native names
while searches and fetches bill to your Exa account.

  POST /search  <- {"text_query": "..."}
                -> {"search_results": [{"title", "url", "snippet", "date", "site_name"}]}

  POST /fetch   <- {"url": "..."}
                -> 200 with the page text as the body

  GET  /health  -> {"ok": true, "port": ..., "results": ..., "key": bool, "status": true}
  GET  /status  -> {"ok": true, "session": ..., "text": ..., "cache": 99, "balance": "¥41.39"}
                   本地 statusline.py 的缓存率 + 余额；只读、无 CORS 头（普通网页读不到，
                   浏览器用户脚本用 GM_xmlhttpRequest 才能取）
  GET  /panel   -> 一个自包含小页面，每 5s 轮询 /status 显示同样两个数字

Environment:
  EXA_API_KEY             Exa key; falls back to ~/.kimi-code/mcp.json
                          (mcpServers.exa.headers.x-api-key) when unset
  EXA_BRIDGE_TOKEN        bearer token clients must present (empty = accept any)
  EXA_BRIDGE_PORT         listen port, default 8787
  EXA_BRIDGE_NUM_RESULTS  search results per query, default 5
"""

import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

EXA_API_BASE = os.environ.get("EXA_API_BASE", "https://api.exa.ai").rstrip("/")
PORT = int(os.environ.get("EXA_BRIDGE_PORT", "8787"))
NUM_RESULTS = int(os.environ.get("EXA_BRIDGE_NUM_RESULTS", "5"))
SNIPPET_CHARS = 400
PAGE_TEXT_CHARS = 200_000

KIMI_HOME = os.environ.get("KIMI_CODE_HOME") or os.path.expanduser("~/.kimi-code")
STATUSLINE_SCRIPT = os.path.join(KIMI_HOME, "statusline.py")
STATUS_TTL_S = 2.0
STATUS_TIMEOUT_S = 8


def api_key() -> str:
    key = os.environ.get("EXA_API_KEY", "").strip()
    if key:
        return key
    try:
        path = os.path.join(os.environ.get("KIMI_CODE_HOME", os.path.expanduser("~/.kimi-code")), "mcp.json")
        with open(path, encoding="utf-8") as fh:
            headers = json.load(fh)["mcpServers"]["exa"].get("headers", {})
        for name, value in headers.items():
            if name.lower() == "x-api-key":
                return str(value).strip()
    except Exception:
        pass
    return ""


def exa_post(path: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        EXA_API_BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-api-key": api_key()},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def describe_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", "replace").strip()
        except Exception:
            body = ""
        return f"Exa HTTP {exc.code}: {body[:500]}"
    return f"{type(exc).__name__}: {exc}"


def site_name(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def snippet_of(result: dict) -> str:
    highlights = result.get("highlights")
    if isinstance(highlights, list) and highlights:
        return " … ".join(str(h).strip() for h in highlights if str(h).strip())[:SNIPPET_CHARS]
    for field in ("summary", "text"):
        value = result.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", " ")[:SNIPPET_CHARS]
    return ""


def handle_search(body: dict) -> tuple[int, dict]:
    query = str(body.get("text_query", "")).strip()
    if not query:
        return 400, {"error": "missing text_query"}
    payload = {
        "query": query,
        "numResults": NUM_RESULTS,
        "contents": {"highlights": {"maxCharacters": SNIPPET_CHARS}},
    }
    try:
        data = exa_post("/search", payload, timeout=25)
    except Exception as exc:
        return 502, {"error": describe_error(exc)}
    results = []
    for item in data.get("results") or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        entry = {
            "title": str(item.get("title") or ""),
            "url": str(item["url"]),
            "snippet": snippet_of(item),
        }
        if item.get("publishedDate"):
            entry["date"] = str(item["publishedDate"])
        if site_name(entry["url"]):
            entry["site_name"] = site_name(entry["url"])
        results.append(entry)
    return 200, {"search_results": results}


def handle_fetch(body: dict) -> tuple[int, str, str]:
    url = str(body.get("url", "")).strip()
    if not url:
        return 400, "text/plain", "missing url"
    payload = {"urls": [url], "text": {"maxCharacters": PAGE_TEXT_CHARS}}
    try:
        data = exa_post("/contents", payload, timeout=45)
    except Exception as exc:
        # Stay 200 so the CLI does not silently fall back to its local fetcher.
        return 200, "text/markdown", f"[exa-bridge] fetch failed: {describe_error(exc)}"
    for item in data.get("results") or []:
        text = item.get("text") if isinstance(item, dict) else None
        if isinstance(text, str) and text.strip():
            title = str(item.get("title") or "").strip()
            body_text = f"# {title}\n\n{text}" if title else text
            return 200, "text/markdown", body_text
    statuses = data.get("statuses") or []
    detail = ""
    if statuses and isinstance(statuses[0], dict):
        error = statuses[0].get("error") or {}
        detail = str(error.get("tag") or statuses[0].get("status") or "")
    return 200, "text/markdown", f"[exa-bridge] no content returned for {url} {detail}".strip()


# ------------------------------------------------------- /status + /panel

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_STATUS_CACHE = {"ts": 0.0, "key": None, "payload": None}


def newest_session_id() -> str:
    pattern = os.path.join(KIMI_HOME, "sessions", "*", "session_*", "agents", "main", "wire.jsonl")
    files = glob.glob(pattern)
    if not files:
        return ""
    newest = max(files, key=os.path.getmtime)
    return os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(newest))))


def session_exists(session_id: str) -> bool:
    pattern = os.path.join(KIMI_HOME, "sessions", "*", session_id, "agents", "main", "wire.jsonl")
    return bool(glob.glob(pattern))


def status_payload(session_id: str) -> dict:
    """跑一次本地 statusline.py，把缓存率/余额抽成结构化 JSON（结果缓存 2 秒）。"""
    now = time.monotonic()
    if (_STATUS_CACHE["payload"] is not None
            and _STATUS_CACHE["key"] == session_id
            and now - _STATUS_CACHE["ts"] < STATUS_TTL_S):
        return _STATUS_CACHE["payload"]

    sid = session_id or newest_session_id()
    result = {"ok": False, "session": sid, "text": "", "cache": None, "balance": None}
    if not sid:
        result["error"] = "no session found under %s/sessions" % KIMI_HOME
    elif not os.path.exists(STATUSLINE_SCRIPT):
        result["error"] = "statusline script not found: %s" % STATUSLINE_SCRIPT
    else:
        try:
            proc = subprocess.run(
                [sys.executable, STATUSLINE_SCRIPT],
                input=json.dumps({"sessionId": sid}).encode(),
                capture_output=True, timeout=STATUS_TIMEOUT_S)
            text = ANSI_RE.sub("", (proc.stdout or b"").decode("utf-8", "replace")).strip()
            if text:
                first = text.splitlines()[0]
                result["ok"] = True
                result["text"] = first
                match = re.search(r"cache (\d+)%", first)
                if match:
                    result["cache"] = int(match.group(1))
                match = re.search(r"bal (\S+)", first)
                if match:
                    result["balance"] = match.group(1)
            else:
                result["error"] = "statusline produced no output"
        except subprocess.TimeoutExpired:
            result["error"] = "statusline timed out"
        except Exception as exc:
            result["error"] = "%s: %s" % (type(exc).__name__, exc)

    _STATUS_CACHE.update({"ts": now, "key": session_id, "payload": result})
    return result


PANEL_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kimi-code 状态</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font: 13px/1.5 -apple-system, "SF Pro Text", system-ui, sans-serif;
         background: #f6f6f7; color: #1a1a1a; }
  @media (prefers-color-scheme: dark) { body { background: #1b1b1d; color: #e8e8e8; } }
  .wrap { padding: 12px 16px; }
  .row { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
  .k { opacity: .55; font-size: 12px; }
  .row b { font-variant-numeric: tabular-nums; font-size: 15px; }
  .detail { opacity: .55; font-size: 12px; margin-top: 4px; }
  .err { color: #d05353; font-size: 12px; margin-top: 4px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="row">
    <span class="k">cache</span><b id="cache">&mdash;</b>
    <span class="k">bal</span><b id="bal">&mdash;</b>
  </div>
  <div class="detail" id="detail"></div>
  <div class="err" id="err"></div>
</div>
<script>
  function paint(rate) {
    if (rate == null) return '';
    if (rate >= 80) return '#2e9e5b';
    if (rate >= 50) return '#c98a1b';
    return '#d05353';
  }
  function tick() {
    fetch('/status', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
      var cache = document.getElementById('cache');
      cache.textContent = (d.cache == null) ? '\u2014' : d.cache + '%';
      cache.style.color = paint(d.cache);
      document.getElementById('bal').textContent = d.balance || '\u2014';
      var text = String(d.text || '');
      var i = text.indexOf('cached');
      document.getElementById('detail').textContent = i >= 0 ? text.slice(i) : text;
      document.getElementById('err').textContent = d.ok ? '' : ('桥报错：' + (d.error || '未知'));
    }).catch(function (e) {
      document.getElementById('err').textContent = '桥不可用：' + e;
    });
  }
  tick();
  setInterval(tick, 5000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "exa-bridge/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, content_type: str, payload: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj: dict):
        self._send(status, "application/json", json.dumps(obj).encode())

    def _authorized(self) -> bool:
        expected = os.environ.get("EXA_BRIDGE_TOKEN", "").strip()
        if not expected:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {expected}"

    def _local_host(self) -> bool:
        """只认本机 Host，挡 DNS rebinding（/status、/panel 用）。"""
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self._json(200, {"ok": True, "port": PORT, "results": NUM_RESULTS,
                             "key": bool(api_key()), "status": True})
        elif path == "/status":
            if not self._local_host():
                self._json(403, {"ok": False, "error": "forbidden host"})
                return
            sid = (parse_qs(urlsplit(self.path).query).get("session") or [""])[0].strip()
            if sid and not re.fullmatch(r"session_[A-Za-z0-9_-]+", sid):
                self._json(400, {"ok": False, "error": "bad session id"})
                return
            if sid and not session_exists(sid):
                self._json(404, {"ok": False, "error": "session not found"})
                return
            self._json(200, status_payload(sid))
        elif path == "/panel":
            if not self._local_host():
                self._json(403, {"ok": False, "error": "forbidden host"})
                return
            self._send(200, "text/html; charset=utf-8", PANEL_HTML.encode("utf-8"))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        # Read the body before anything else: an undrained body would be parsed
        # as the next request line on this keep-alive connection.
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        path = urlsplit(self.path).path
        try:
            body = json.loads(raw.decode("utf-8", "replace") or "{}")
        except Exception:
            self._json(400, {"error": "invalid json"})
            return
        if not isinstance(body, dict):
            self._json(400, {"error": "body must be an object"})
            return
        if path == "/search":
            status, payload = handle_search(body)
            self._json(status, payload)
        elif path == "/fetch":
            status, content_type, text = handle_fetch(body)
            self._send(status, content_type, text.encode())
        else:
            self._json(404, {"error": "not found"})


def main():
    if not api_key():
        sys.stderr.write("exa-bridge: no Exa API key (set EXA_API_KEY or mcp.json header)\n")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    sys.stderr.write(f"exa-bridge listening on http://127.0.0.1:{PORT} (results={NUM_RESULTS})\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
