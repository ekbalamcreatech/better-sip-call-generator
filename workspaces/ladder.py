"""Builds ladder-diagram data from SIPp message logs."""
import os
import subprocess
import glob
import re

from workspaces.state import _workspaces
from config import RUN_DIR

def _get_local_ips() -> list:
    """Get all local IP addresses."""
    result = subprocess.run(["ip", "-4", "addr", "show"], capture_output=True, text=True)
    import re
    return re.findall(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)

def get_workspace_ladder(workspace_id: int) -> dict:
    ws = _workspaces.get(workspace_id)
    role = ws.get("role", "tx") if ws else "tx"
    prefix = "uas" if role == "rx" else "uac"

    # find all script logs for this workspace
    all_files = glob.glob(f"{RUN_DIR}/bscg_{prefix}_{workspace_id}_*_messages.log")
    if not all_files:
        return {"calls": {}, "scripts": []}

    # group by script_id
    scripts = {}
    for f in all_files:
        match = re.search(rf'bscg_{prefix}_{workspace_id}_(\d+)_\d+_messages', os.path.basename(f))
        if match:
            sid = int(match.group(1))
            if sid not in scripts:
                scripts[sid] = []
            scripts[sid].append(f)

    # for each script get ALL logs from current run (last N minutes)
    import time
    run_window = 3600  # last hour
    script_logs = {}
    for sid, files in scripts.items():
        # get recent files within run window
        recent = [f for f in files if time.time() - os.path.getmtime(f) < run_window]
        script_logs[sid] = sorted(recent, key=os.path.getmtime)

    return {
        "script_logs": {str(sid): logs for sid, logs in script_logs.items()},
        "scripts": sorted(scripts.keys())
    }
