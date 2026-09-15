"""statusline 后台刷新守护（Windows）：把重活从 300ms 热路径里搬出来。

背景：kimi-code 的状态栏命令由 runner 强制 300ms 超时（超时 taskkill /T /F 并丢弃结果）。
这台机器上 cmd(≈40ms) + 解释器启动(≈90-150ms) + 脚本自身(≈80ms) 空闲就 ~240ms、机器忙时
400ms+，同步调用必然间歇性失败，footer 回落成内置布局。

现在的分工：
  statusline-fast.exe（热路径，~10ms）：stdin 的 JSON 快照按会话键落盘 + 打印预渲染行 +
      心跳过期时拉起本守护进程（bInheritHandles=FALSE，不会拖住 runner 的管道）。
  本文件（常驻，约 1% CPU）：读 payload_<key>.json -> statusline.build_line() -> line_<key>.txt；
      顺带负责 exa-bridge 探活与余额刷新（不再受 runner 的 taskkill 连坐）。

会话键 = 当前工作目录的叶子名（fast.exe 用 %CD% 的叶子名；两个会话不同目录即互不干扰）。
"""
import glob
import json
import os
import sys
import time

KIMI_HOME = os.environ.get("KIMI_CODE_HOME") or os.path.join(os.path.expanduser("~"), ".kimi-code")
STATE_DIR = os.path.join(KIMI_HOME, "statusline")
HEARTBEAT = os.path.join(STATE_DIR, "daemon.heartbeat")
LOCK = os.path.join(STATE_DIR, "daemon.lock")
IDLE_EXIT_S = 3600
FORCE_REFRESH_S = 30
LOOP_S = 1.0

sys.path.insert(0, KIMI_HOME)
import statusline  # noqa: E402  （复用它的 build_line / watch_bridge / 余额刷新）

os.environ["KIMI_CODE_STATUS_LINE"] = "1"   # 通过 watch_bridge 的门闩：这里就是它的正牌调用方


def log(text):
    try:
        with open(os.path.join(STATE_DIR, "daemon.log"), "a", encoding="utf-8") as fh:
            fh.write("%.0f %s\n" % (time.time(), text))
    except Exception:
        pass


def acquire_lock():
    try:
        import msvcrt
        os.makedirs(STATE_DIR, exist_ok=True)
        handle = open(LOCK, "a+")
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except Exception:
        return None


def beat():
    try:
        with open(HEARTBEAT, "w", encoding="utf-8") as fh:
            fh.write("%.0f\n" % time.time())
    except Exception:
        pass


def write_line(path, text):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        os.replace(tmp, path)
    except Exception:
        pass


def render(payload, key):
    try:
        line = statusline.build_line(payload)
    except Exception as exc:
        log("build_line failed: %r" % (exc,))
        return False
    if not line:
        return False
    write_line(os.path.join(STATE_DIR, "line_%s.txt" % key), line)
    return True


def main():
    lock = acquire_lock()
    if lock is None:
        return 0
    log("daemon start pid=%d" % os.getpid())
    seen = {}
    rendered_at = {}
    last_activity = time.time()
    try:
        while True:
            now = time.time()
            beat()
            active = False
            for path in glob.glob(os.path.join(STATE_DIR, "payload_*.json")):
                key = os.path.basename(path)[len("payload_"):-len(".json")]
                try:
                    with open(path, "rb") as fh:
                        raw = fh.read()
                except OSError:
                    continue
                if not raw:
                    continue
                changed = raw != seen.get(path)
                if changed and now - rendered_at.get(path, 0) < 0.5:
                    active = True
                    continue
                if not changed and now - rendered_at.get(path, 0) < FORCE_REFRESH_S:
                    continue
                try:
                    payload = json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    continue
                if not isinstance(payload, dict) or not payload:
                    continue
                seen[path] = raw
                if render(payload, key):
                    rendered_at[path] = now
                    active = True
            try:
                statusline.watch_bridge()
            except Exception:
                pass
            if active:
                last_activity = now
            elif now - last_activity > IDLE_EXIT_S:
                log("daemon idle exit")
                return 0
            time.sleep(LOOP_S)
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
