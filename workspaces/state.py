"""Workspace registry: in-memory state, ownership, claiming and status."""
import os
from engines.sipp import parse_stats_csv
from typing import Dict, Optional
from config import RUN_DIR



# Capacity is enforced by counting LIVE OWNED workspaces (owner is not None),
# not by ID range. A released slot frees capacity and its ID is reused
# (see _find_smallest_free_id).
MAX_SCRIPTS = 5

# ─── Workspace State ──────────────────────────────────────────────────────────
_workspaces: Dict[int, dict] = {}

def init_workspace(workspace_id: int, role: str = "tx", label: str = "",
                   ip: str = "127.0.0.1", port: int = 5081, owner: str = None):
    if workspace_id not in _workspaces:
        _workspaces[workspace_id] = {
            "role": role,
            "label": label or f"Workspace {workspace_id}",
            "ip": ip,
            "port": port,
            "running": False,
            "scripts": {},
            "current_interval": 0,
            "intervals": [],
            "tcpdump_proc": None,
            "log": [],
            "cumulative": {},
            "owner": owner,   # username that claimed this slot, or None if free
        }
    else:
        # update role, label, ip, port even if workspace exists
        _workspaces[workspace_id]["role"]  = role
        _workspaces[workspace_id]["label"] = label or _workspaces[workspace_id]["label"]
        _workspaces[workspace_id]["ip"]    = ip
        _workspaces[workspace_id]["port"]  = port
        _workspaces[workspace_id]["scripts"] = {}  # clear scripts on re-init
        if owner is not None:
            _workspaces[workspace_id]["owner"] = owner
        _workspaces[workspace_id].setdefault("owner", None)

def count_live_workspaces(owner: str = None) -> int:
    """
    Count of currently-CLAIMED (owner is not None) workspaces — optionally
    filtered to one owner. A released workspace (owner set back to None)
    doesn't count, even though its dict entry and old ID may still exist.
    """
    if owner is not None:
        return sum(1 for ws in _workspaces.values() if ws.get("owner") == owner)
    return sum(1 for ws in _workspaces.values() if ws.get("owner") is not None)

def can_claim_workspace(owner: str, max_per_user: int, max_total: int):
    """
    Returns (ok, error). Shared cap-check logic used both when minting a
    brand new ID (claim_new_workspace_id) and when /init re-adopts a
    previously-released (owner=None) slot directly — without this second
    path also being checked, /init would silently bypass the workspace caps
    entirely by re-claiming an unowned ID with no cap enforcement at all.
    """
    owned_by_user = count_live_workspaces(owner)
    if owned_by_user >= max_per_user:
        return False, f"You already have {owned_by_user} workspace(s) — the limit is {max_per_user} per user"
    total_claimed = count_live_workspaces()
    if total_claimed >= max_total:
        occupants = {wid: ws.get("owner") for wid, ws in _workspaces.items() if ws.get("owner")}
        return False, f"Workspace limit reached: {max_total} total workspaces in use across all users ({occupants})"
    return True, None

def _find_smallest_free_id() -> int:
    """
    Smallest positive integer that's either never been used or has been
    released (owner is None). Was an ever-incrementing counter that never
    reused a number — correct, but confusing in practice: releasing
    "Workspace 1" and adding a new one would show up as "Workspace 6"
    instead of reclaiming slot 1. Reusing gaps matches what an operator
    actually expects to see, and as a side benefit avoids _workspaces
    growing unbounded over a long uptime.
    """
    wid = 1
    while True:
        ws = _workspaces.get(wid)
        if ws is None or ws.get("owner") is None:
            return wid
        wid += 1

def claim_new_workspace_id(owner: str, max_per_user: int, max_total: int):
    """
    Returns (workspace_id, error). Claims the smallest currently-free ID
    for `owner` — or returns None with a clear reason if either this
    user's own cap or the system-wide cap is already reached.
    """
    ok, err = can_claim_workspace(owner, max_per_user, max_total)
    if not ok:
        return None, err

    wid = _find_smallest_free_id()
    init_workspace(wid, owner=owner)
    return wid, None

def release_workspace(workspace_id: int):
    """Frees a slot (and its IP) for reuse without deleting its history/log."""
    ws = _workspaces.get(workspace_id)
    if ws:
        ws["owner"] = None

def ip_port_in_use_by(ip: str, port: int, exclude_workspace_id: int = None):
    """
    Returns the owner username currently holding this exact (ip, port)
    combination on a claimed workspace, or None if it's free.

    Was ip_in_use_by(ip) — locked the WHOLE IP the moment any workspace
    claimed it. That's wrong: the real OS-level constraint is the (ip, port)
    PAIR, not the IP alone — SIPp (and the app's own pre-existing
    nextAvailablePort()/checkAllPortConflicts() logic, which already keyed
    on "ip:port" strings) has always assumed many workspaces can share one
    IP on different ports. With only 2 physical IPs on a typical box, the
    IP-only lock meant at most 2 workspaces could ever be live across ALL
    users combined — starving any second real user. Checking ip+port
    instead restores the intended "many workspaces, one IP, different
    ports" pattern while still preventing a genuine port collision.
    """
    for wid, ws in _workspaces.items():
        if wid == exclude_workspace_id:
            continue
        if ws.get("owner") is not None and ws.get("ip") == ip and ws.get("port") == port:
            return ws["owner"]
    return None

def ports_in_use_on_ip(ip: str, exclude_workspace_id: int = None):
    """Informational: [{port, owner}, ...] for every claimed workspace on this IP — an IP is never itself 'taken', only specific ports on it."""
    result = []
    for wid, ws in _workspaces.items():
        if wid == exclude_workspace_id:
            continue
        if ws.get("owner") is not None and ws.get("ip") == ip:
            result.append({"port": ws.get("port"), "owner": ws["owner"]})
    return result

def get_workspace(workspace_id: int) -> Optional[dict]:
    return _workspaces.get(workspace_id)

def log_workspace(workspace_id: int, msg: str, level: str = "info"):
    """Add log entry to workspace."""
    import time
    ws = _workspaces.get(workspace_id)
    if ws is not None:
        ws["log"].append({
            "time": time.strftime("%H:%M:%S"),
            "msg": msg,
            "level": level
        })
        # keep last 200 entries
        if len(ws["log"]) > 200:
            ws["log"] = ws["log"][-200:]

def get_workspace_status(workspace_id: int) -> dict:
    """Get full status of a workspace."""
    ws = _workspaces.get(workspace_id)
    if not ws:
        return {"error": "Workspace not found"}

    scripts_status = {}
    totals = {"sent": 0, "completed": 0, "failed": 0, "active": 0, "retransmissions": 0}

    for sid, state in ws["scripts"].items():
        stats = dict(state.get("stats") or {})
        for k in totals:
            stats.setdefault(k, 0)
        stats["active"] = 0
        if ws["role"] == "tx" and state.get("running"):
            # show the interval in progress live, on top of the finished intervals
            live = parse_stats_csv(f"{RUN_DIR}/sipp_tx_stats_{workspace_id}_{sid}.csv")
            if live:
                for k in ("sent", "completed", "failed", "retransmissions"):
                    stats[k] += live[k]
                stats["active"] = live["active"]
        scripts_status[sid] = {
            "running": state.get("running", False),
            "stats": stats,
            "mos": state.get("mos"),
            "rtcp": state.get("rtcp")
        }
        for k in totals:
            totals[k] += stats[k]

    return {
        "workspace_id": workspace_id,
        "role": ws["role"],
        "label": ws["label"],
        "ip": ws["ip"],
        "port": ws["port"],
        "running": ws["running"],
        "current_interval": ws["current_interval"],
        "run_start_time": ws.get("run_start_time", 0),
        "owner": ws.get("owner"),
        "scripts": scripts_status,
        "totals": totals,
        "log": ws["log"][-20:]  # last 20 entries
    }

def get_all_workspaces_status() -> dict:
    return {wid: get_workspace_status(wid) for wid in _workspaces}

# ─── Script management ────────────────────────────────────────────────────────
def _init_script_state(workspace_id: int, script_id: int):
    ws = _workspaces.get(workspace_id)
    if ws is None:
        return
    # clear stale CSV
    try:
        # rename old CSV instead of deleting — allows reading previous interval stats
        old_csv = f"{RUN_DIR}/sipp_tx_stats_{workspace_id}_{script_id}.csv"
        if os.path.exists(old_csv):
            import shutil
            shutil.move(old_csv, f"{old_csv}.prev")
    except:
        pass
    # preserve cumulative stats — don't reset here, reset happens in run_workspace
    if script_id not in ws["scripts"]:
        ws["scripts"][script_id] = {
            "process": None,
            "running": False,
            "stats": {"sent": 0, "completed": 0, "failed": 0},
            "last_stats": {"sent": 0, "completed": 0, "failed": 0},
            "mos": None,
            "rtcp": None
        }
    else:
        # just reset process state, keep stats for mid-interval reads
        ws["scripts"][script_id]["process"] = None
        ws["scripts"][script_id]["running"] = False


def bind_conflict(workspace_id: int, binds: list):
    """
    First (ip, port, other_workspace_id, owner) from `binds` already held by a
    DIFFERENT claimed workspace (its configured address, or a port its scripts
    are actively using); None if all are free.
    """
    wanted = set(binds)
    for wid, ws in _workspaces.items():
        if wid == workspace_id or ws.get("owner") is None:
            continue
        held = {(ws.get("ip"), ws.get("port"))}
        if ws.get("running"):
            held |= set(ws.get("bound", ()))
        hit = wanted & held
        if hit:
            ip, port = sorted(hit)[0]
            return ip, port, wid, ws["owner"]
    return None
