#!/usr/bin/env python3
"""把 skill 里的部署脚本同步到机器上的落地点（幂等，可反复跑）。

做三件事：
  1. 同步部署文件——Windows 5 个（多出 `statusline-daemon.pyw` 与 `statusline-fast.c`），
     macOS / Linux 3 个；按内容比对，一致就不动文件（免得白改 mtime）；
  2. Windows：`statusline-fast.c` 有变（或 exe 缺失 / exe 比 `.c` 旧）时用 MSYS2 gcc 重编 exe；
  3. 重启状态栏守护进程（Windows 专用）；加 `--bridge` 时连 exa-bridge 一起重启。

**不碰**：`config.toml` / `tui.toml` / 常驻定义（那些走 `patch-config.py` 与模板），也不做
「正本 → 安装副本」的同步（那是 rsync / robocopy 那一步）。

退出码：0 顺利；1 有告警（找不到 gcc、桥探活没恢复）；2 有失败。
`--check` 只报告：0 = 全部一致，2 = 有漂移（适合塞进别的流程）。

实测状态：Windows 分支（拷贝 / 重编 / 守护进程重启 / 沙箱）已实测；
macOS / Linux 的拷贝分支直接可用，`--bridge` 的重启命令照文档写、**未实机复跑**。
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WINDOWS = sys.platform == "win32"
SKILL_DIR = Path(__file__).resolve().parent.parent

FILES = [
    ("assets/exa-bridge.py", "exa-bridge/exa-bridge.py"),
    ("assets/statusline.py", "statusline.py"),
    ("assets/todo-panel-guard.py", "hooks/todo-panel-guard.py"),
]
if WINDOWS:
    FILES += [
        ("assets/statusline-daemon.pyw", "statusline-daemon.pyw"),
        ("assets/statusline-fast.c", "statusline-fast.c"),
    ]

EXE = "statusline-fast.exe"
DAEMON = "statusline-daemon.pyw"
BRIDGE_LNK = "kimi-exa-bridge.lnk"
GCC_CANDIDATES = [r"C:\msys64\mingw64\bin\gcc.exe", r"C:\msys64\ucrt64\bin\gcc.exe"]

FAILED = False
WARNED = False
DRIFTS = []


def say(tag, msg):
    print("[%s] %s" % (tag, msg))


def fail(msg):
    global FAILED
    FAILED = True
    say("FAIL", msg)


def warn(msg):
    global WARNED
    WARNED = True
    say("WARN", msg)


def drift(msg):
    DRIFTS.append(msg)
    say("漂移", msg)


def home_dir() -> Path:
    return Path(os.environ.get("KIMI_CODE_HOME") or Path.home() / ".kimi-code").expanduser()


def sync_files(home: Path, check: bool) -> set:
    """按内容比对同步；返回本次真正改动的源文件（相对 assets/），给 exe 重编判断用。"""
    changed = set()
    for src_rel, dst_rel in FILES:
        src = SKILL_DIR / src_rel
        dst = home / dst_rel
        if not src.exists():
            fail("%s 不存在——skill 目录不完整？" % src_rel)
            continue
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            say("OK", "已是最新  %s" % dst_rel)
            continue
        changed.add(src_rel)
        if check:
            drift("%s ≠ %s" % (dst_rel, src_rel))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if dst.read_bytes() == src.read_bytes():
            say("同步", "%s → %s" % (src_rel, dst))
        else:
            fail("拷贝后校验不一致：%s" % dst)
    return changed


def find_gcc():
    for cand in GCC_CANDIDATES:
        if Path(cand).exists():
            return cand
    return shutil.which("gcc")


def ensure_exe(home: Path, changed: set, check: bool) -> None:
    if not WINDOWS:
        return
    c_dst = home / "statusline-fast.c"
    exe = home / EXE
    if not c_dst.exists():
        warn("没有 %s，跳过 exe 重编" % c_dst)
        return
    stale = (not exe.exists()
             or "assets/statusline-fast.c" in changed
             or exe.stat().st_mtime < c_dst.stat().st_mtime)
    if not stale:
        say("OK", "%s 与 .c 同步（无需重编）" % EXE)
        return
    if check:
        drift("%s 需要重编（.c 更新过，或 exe 缺失 / 落后）" % EXE)
        return
    gcc = find_gcc()
    if not gcc:
        warn("找不到 gcc，%s 没重编——装 MSYS2 后重跑，或手动：gcc -O2 -static -s -o %s %s"
             % (EXE, exe, c_dst))
        return
    proc = subprocess.run([gcc, "-O2", "-static", "-s", "-o", str(exe), str(c_dst)],
                          capture_output=True, text=True)
    detail = (proc.stderr or proc.stdout or "").strip()
    if proc.returncode != 0 or not exe.exists():
        fail("gcc 重编失败（退出码 %d）：%s" % (proc.returncode, detail[:300] or "无输出"))
    else:
        say("重建", "%s（%s，%d 字节）" % (EXE, gcc, exe.stat().st_size))


def daemon_pids(home: Path) -> list:
    """只认「命令行里同时出现本 home 与守护脚本名」的 pythonw，避免误杀别的实例。"""
    want = str(home).replace("\\", "/").lower()
    script = ("Get-CimInstance Win32_Process -Filter \"Name LIKE 'pythonw%'\" | "
              "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=40).stdout
    except Exception as exc:
        warn("查守护进程失败：%s" % exc)
        return []
    pids = []
    for line in out.splitlines():
        pid, _, cmd = line.partition("\t")
        cmd = cmd.replace("\\", "/").lower()
        if pid.strip().isdigit() and DAEMON in cmd and want in cmd:
            pids.append(int(pid))
    return pids


def restart_daemon(home: Path, check: bool) -> None:
    if not WINDOWS:
        return
    pids = daemon_pids(home)
    if not pids:
        say("OK", "守护进程没在跑（下一次 tick 由热路径自动拉起）")
        return
    if check:
        say("INFO", "守护进程在跑（pid %s）——改了 .py / .pyw 要重启它"
            % ",".join(map(str, pids)))
        return
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True)
    say("重启", "守护进程已停（pid %s），下一次 tick（≤5 秒）自动拉起新副本"
        % ",".join(map(str, pids)))


def listening_pid(port: int) -> int:
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=30).stdout
    except Exception as exc:
        warn("netstat 失败：%s" % exc)
        return 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(":%d" % port) and parts[-1].isdigit() \
                and parts[3].upper().startswith("LISTEN"):
            return int(parts[-1])
    return 0


def wait_health(port: int, timeout: float = 12.0) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with opener.open("http://127.0.0.1:%d/health" % port, timeout=2) as fh:
                if fh.status == 200:
                    say("OK", "桥 /health 已恢复（端口 %d）" % port)
                    return True
        except Exception:
            time.sleep(0.5)
    warn("桥拉起后 %d 秒内 /health 没通——去 bridge.log 看看" % int(timeout))
    return False


def restart_bridge(home: Path) -> None:
    port = int(os.environ.get("EXA_BRIDGE_PORT") or 8787)
    if WINDOWS:
        pid = listening_pid(port)
        if pid:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True)
            say("重启", "桥已停（pid %d，端口 %d）" % (pid, port))
        lnk = (Path(os.environ.get("APPDATA") or "")
               / "Microsoft/Windows/Start Menu/Programs/Startup" / BRIDGE_LNK)
        launch = home / "exa-bridge/launch.pyw"
        if lnk.exists():
            os.startfile(str(lnk))          # 脱离进程树，与状态栏兜底同一条路
            say("重启", "已用启动文件夹的 %s 拉起" % BRIDGE_LNK)
        elif launch.exists():
            pyw = Path(sys.executable).with_name("pythonw.exe")
            subprocess.Popen([str(pyw), str(launch)], creationflags=0x00000008, close_fds=True)
            say("重启", "已用 pythonw 拉起 %s" % launch)
        else:
            fail("既没有 %s 也没有 launch.pyw，桥没拉起来" % BRIDGE_LNK)
            return
        wait_health(port)
        return
    # macOS / Linux：常驻定义里已有重启命令，照文档调用（未实机复跑）
    if sys.platform == "darwin":
        cmd = ["launchctl", "kickstart", "-k", "gui/%d/ai.kimi.exa-bridge" % os.getuid()]
    else:
        cmd = ["systemctl", "--user", "restart", "ai.kimi.exa-bridge"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        say("重启", "已执行 %s" % " ".join(cmd))
    except Exception as exc:
        fail("重启桥失败：%s" % exc)
        return
    wait_health(port)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="把 skill 里的部署脚本同步到机器上的落地点（幂等；改完脚本或体检报「脚本漂移」时跑它）")
    ap.add_argument("--check", action="store_true", help="只报告差异，不写任何文件（有漂移退 2）")
    ap.add_argument("--bridge", action="store_true", help="顺带重启 exa-bridge（会短暂中断搜索）")
    args = ap.parse_args()

    home = home_dir()
    say("INFO", "skill 目录：%s" % SKILL_DIR)
    say("INFO", "落地点：%s" % home)
    if args.check:
        say("INFO", "只读模式（--check）：不写任何文件")

    changed = sync_files(home, args.check)
    ensure_exe(home, changed, args.check)
    restart_daemon(home, args.check)
    if args.bridge:
        if args.check:
            say("INFO", "--check 下不重启桥")
        else:
            restart_bridge(home)

    print("—— 合计：本次改动 %d 个文件 / %d 项漂移 ——"
          % (0 if args.check else len(changed), len(DRIFTS)))
    if FAILED:
        return 2
    if args.check and DRIFTS:
        return 2
    return 1 if WARNED else 0


if __name__ == "__main__":
    sys.exit(main())
