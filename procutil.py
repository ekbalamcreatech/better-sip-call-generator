"""Keeps SIPp / tcpdump children from outliving the app that started them."""
import os
import shutil
import signal
import time
from typing import List


def tied_to_parent(cmd: List[str]) -> List[str]:
    """
    Prefix `cmd` so the kernel sends it SIGTERM if this app dies, even on
    `kill -9` (uses util-linux `setpriv --pdeathsig`).

    Skipped for `sudo` commands: the kernel clears the setting when a
    set-uid binary is executed, so it would silently do nothing. Those, and
    anything where setpriv is missing, are covered by reap_orphans() at the
    next startup.
    """
    if cmd and cmd[0] == "sudo":
        return cmd
    setpriv = shutil.which("setpriv")
    return [setpriv, "--pdeathsig", "SIGTERM", "--"] + cmd if setpriv else cmd


# Shell wrapper for children that change credentials after starting (tcpdump
# drops root; sudo is set-uid), which clears the kernel's parent-death signal.
# The wrapper itself keeps the signal, and stops the real command when it fires.
_GUARD = '"$@" & p=$!; trap "kill -INT $p" INT; trap "kill $p" TERM; wait $p; wait $p'


def guarded(cmd: List[str]) -> List[str]:
    """Like tied_to_parent(), but also works for commands that drop privileges."""
    return tied_to_parent(["sh", "-c", _GUARD, "sh"] + cmd)


def _our_processes(run_dir: str) -> List[int]:
    """PIDs of sipp/tcpdump processes whose arguments point into run_dir."""
    marker = os.path.join(run_dir, "").encode()
    me = os.getpid()
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")
        except OSError:
            continue
        if argv and os.path.basename(argv[0]) in (b"sipp", b"tcpdump") and any(marker in a for a in argv[1:]):
            pids.append(int(entry))
    return pids


def reap_orphans(run_dir: str) -> List[int]:
    """
    Kill sipp/tcpdump processes left behind by a previous run of this app
    (crash, kill -9, power loss...). Called once at startup, before any
    workspace exists, so anything found here is by definition an orphan.
    """
    from netutil import privileged
    import subprocess

    found = _our_processes(run_dir)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in found:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:  # e.g. tcpdump started through sudo
                subprocess.run(privileged(["kill", f"-{int(sig)}", str(pid)]), capture_output=True)
        time.sleep(1.0 if sig == signal.SIGTERM else 0)
        found = [p for p in _our_processes(run_dir) if p in found]
        if not found:
            break
    return found
