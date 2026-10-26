"""Small network/privilege helpers shared by the workspace code."""
import os
import re
import subprocess
from typing import List


def privileged(cmd: List[str]) -> List[str]:
    """Prefix a command with `sudo -n` when not running as root (never prompts)."""
    if os.geteuid() == 0 or os.environ.get("SIPPTESTER_SUDO", "auto") == "0":
        return cmd
    return ["sudo", "-n"] + cmd


def _ip_route(args: List[str]) -> str:
    try:
        return subprocess.run(["ip", "-o"] + args, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def iface_for_ip(ip: str) -> str:
    """Interface the kernel would use to reach `ip` (override: SIPPTESTER_CAPTURE_IFACE)."""
    forced = os.environ.get("SIPPTESTER_CAPTURE_IFACE")
    if forced:
        return forced
    for out in (_ip_route(["route", "get", ip]) if ip else "", _ip_route(["route", "show", "default"])):
        m = re.search(r"\bdev (\S+)", out)
        if m:
            return m.group(1)
    return "any"


def local_ipv4s() -> List[str]:
    """Non-loopback IPv4 addresses on this host."""
    ips = []
    for line in _ip_route(["-4", "addr", "show"]).splitlines():
        m = re.search(r"\binet (\d+\.\d+\.\d+\.\d+)/", line)
        if m and not m.group(1).startswith(("127.", "169.254.")):
            ips.append(m.group(1))
    return ips
