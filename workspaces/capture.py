"""tcpdump capture lifecycle for workspaces."""
import asyncio
import os
import signal
import subprocess
from typing import Dict

from config import RUN_DIR
from netutil import iface_for_ip, privileged
from procutil import guarded
from workspaces.state import log_workspace

_tcpdump_store: Dict[int, subprocess.Popen] = {}  # workspace_id -> tcpdump


def pcap_path(workspace_id: int) -> str:
    return os.path.join(RUN_DIR, f"rtp_ws{workspace_id}_capture.pcap")


def _terminate(proc: subprocess.Popen) -> None:
    """Stop a tcpdump process: SIGINT (flushes the file), then escalate."""
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            proc.send_signal(sig)
            proc.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            continue
        except OSError:
            return


async def _start_tcpdump_capture(workspace_id: int, bpf_filter: str, target_ip: str) -> None:
    """Stop any previous capture for this workspace, then start a fresh one.

    Failures (no permission, bad interface, ...) are written to the workspace
    Live Log so they are visible in the UI.
    """
    old = _tcpdump_store.pop(workspace_id, None)
    if old:
        _terminate(old)
    # Orphan from a previous service run: scoped to this workspace's capture file only.
    subprocess.run(privileged(["pkill", "-f", f"tcpdump.*rtp_ws{workspace_id}_capture"]),
                   capture_output=True)
    await asyncio.sleep(0.5)

    pcap_file = pcap_path(workspace_id)
    err_log_path = os.path.join(RUN_DIR, f"tcpdump_ws{workspace_id}_stderr.log")
    iface = iface_for_ip(target_ip)
    with open(err_log_path, "w") as err_log:
        proc = subprocess.Popen(
            guarded(privileged(["tcpdump", "-i", iface, "-w", pcap_file, "-U", bpf_filter])),
            stdout=err_log, stderr=subprocess.STDOUT)
    _tcpdump_store[workspace_id] = proc

    await asyncio.sleep(0.5)
    if proc.poll() is not None:
        try:
            with open(err_log_path) as f:
                err_output = f.read().strip()
        except OSError:
            err_output = "(could not read tcpdump output)"
        log_workspace(workspace_id,
                      f"tcpdump failed to start (exit code {proc.returncode}): {err_output or 'no output'}", "err")
        _tcpdump_store.pop(workspace_id, None)
    else:
        log_workspace(workspace_id,
                      f"tcpdump capture started on {iface} (PID {proc.pid}, filter: {bpf_filter})", "info")


async def _start_tcpdump(workspace_id: int, scripts: list) -> None:
    """TX capture: traffic to/from the SUT this workspace calls."""
    target_ip = scripts[0].sut_ip if scripts else None
    if target_ip:
        await _start_tcpdump_capture(workspace_id, f"host {target_ip}", target_ip)


async def _start_tcpdump_rx(workspace_id: int, term_ip: str) -> None:
    """RX capture: traffic touching the listening address."""
    await _start_tcpdump_capture(workspace_id, f"host {term_ip}", term_ip)


def _stop_tcpdump(workspace_id: int) -> None:
    proc = _tcpdump_store.pop(workspace_id, None)
    if proc:
        _terminate(proc)
