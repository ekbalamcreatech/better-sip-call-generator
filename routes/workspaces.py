from fastapi import HTTPException, Request
import os
import glob
import json

from workspaces.manager import (
    init_workspace, get_workspace, get_workspace_status,
    get_all_workspaces_status, run_workspace, stop_workspace,
    get_workspace_ladder, claim_new_workspace_id, can_claim_workspace,
    release_workspace, ip_port_in_use_by, bind_conflict
)
from workspaces.sipp_cmd import script_share, script_bind
from engines import auth
from models import (
    WorkspaceStart, WorkspaceConfig
)

from fastapi import APIRouter
from security import session_username, require_role, workspace_guard, check_scenario_xml
from config import RUN_DIR, STORAGE_DIR
router = APIRouter()


MAX_WORKSPACES_PER_USER = int(os.environ.get("SIPPTESTER_MAX_WORKSPACES_PER_USER", "8"))
MAX_WORKSPACES_TOTAL = int(os.environ.get("SIPPTESTER_MAX_WORKSPACES_TOTAL", "16"))

# ─── SAVE WORKSPACES ────────────────────────────────────────────────────────────────
WORKSPACES_DIR = STORAGE_DIR

# ─── Workspaces ───────────────────────────────────────────────────────────────
@router.get("/workspaces")
async def list_workspaces(request: Request):
    username = session_username(request)
    role = auth.get_user_role(username)
    all_status = get_all_workspaces_status()
    if role in auth.ELEVATED_ROLES:
        return all_status
    # Isolation model: a 'user'-role account only sees its own workspaces.
    return {wid: s for wid, s in all_status.items() if s.get("owner") == username}

@router.post("/workspaces/claim")
async def workspace_claim(request: Request):
    """
    Server-side slot allocation. Fixes the collision bug where two browser
    sessions each running their own local ID counter could both land on
    the same workspace_id and silently overwrite each other's config —
    now the server hands out the ID, atomically marking it owned in the
    same call. Enforces this account's own per-user cap (which may be a
    custom override, not just the default) and the global
    total workspace capacity.
    """
    username = session_username(request)
    max_per_user = auth.get_user_max_workspaces(username, default=MAX_WORKSPACES_PER_USER)
    max_total = MAX_WORKSPACES_TOTAL
    wid, err = claim_new_workspace_id(username, max_per_user, max_total)
    if wid is None:
        raise HTTPException(status_code=409, detail=err)
    return {"workspace_id": wid}

@router.post("/workspaces/{workspace_id}/init")
async def workspace_init(request: Request, workspace_id: int, config: WorkspaceConfig):
    username, role = workspace_guard(request, workspace_id)

    existing = get_workspace(workspace_id)
    existing_owner = existing.get("owner") if existing else None
    if existing_owner is not None and existing_owner != username and role not in auth.ELEVATED_ROLES:
        raise HTTPException(status_code=403, detail=f"Workspace {workspace_id} belongs to '{existing_owner}'")

    if existing_owner is None:
        max_per_user = auth.get_user_max_workspaces(username, default=MAX_WORKSPACES_PER_USER)
        max_total = MAX_WORKSPACES_TOTAL
        ok, err = can_claim_workspace(username, max_per_user, max_total)
        if not ok:
            raise HTTPException(status_code=409, detail=err)

    conflicting_owner = ip_port_in_use_by(config.ip, config.sip_port, exclude_workspace_id=workspace_id)
    if conflicting_owner is not None:
        who = "another of your workspaces" if conflicting_owner == username else f"'{conflicting_owner}'"
        raise HTTPException(
            status_code=409,
            detail=f"{config.ip}:{config.sip_port} is already in use by {who} — pick a different port"
        )

    # Preserve ownership if this workspace was already claimed by this user
    # (or by nobody yet — first /init after /claim sets it).
    owner_to_set = existing_owner or username
    init_workspace(workspace_id, config.role, config.label, config.ip, config.sip_port, owner=owner_to_set)
    return {"ok": True, "workspace_id": workspace_id}

@router.get("/workspaces/{workspace_id}/status")
async def workspace_status(request: Request, workspace_id: int):
    workspace_guard(request, workspace_id)
    return get_workspace_status(workspace_id)

def _check_binds(workspace_id: int, ws: dict, req: WorkspaceStart) -> list:
    """
    Reject a start whose SIPp processes would fight over an address, instead of
    letting SIPp fail later with 'Address already in use'. Returns the
    (ip, port) pairs this run will hold.
    """
    if ws["role"] == "rx":
        binds = [(ws["ip"], ws["port"])]
    else:
        # scripts that run together (same interval) must not share a port
        groups = [i.script_cps for i in req.intervals] or [{str(s.script_id): 1 for s in req.scripts}]
        binds = []
        for cps_map in groups:
            seen = {}
            for s in req.scripts:
                if script_share(s) <= 0 or float(cps_map.get(str(s.script_id), 0)) <= 0:
                    continue
                addr = script_bind(s, workspace_id)
                if addr in seen:
                    raise HTTPException(status_code=400, detail=(
                        f"Scripts {seen[addr]} and {s.script_id} both use {addr[0]}:{addr[1]} in the same "
                        f"interval — give each script its own source port"))
                seen[addr] = s.script_id
            binds += list(seen)
        binds = sorted(set(binds))
        # the workspace's own configured address is its own business; others must not collide
    clash = bind_conflict(workspace_id, [b for b in binds if b != (ws.get("ip"), ws.get("port"))])
    if clash:
        ip, port, other, owner = clash
        raise HTTPException(status_code=409, detail=(
            f"{ip}:{port} is already used by workspace {other} ({owner}) — pick a different source port"))
    return binds


@router.post("/workspaces/{workspace_id}/start")
async def workspace_start(request: Request, workspace_id: int, req: WorkspaceStart):
    workspace_guard(request, workspace_id)
    for script in req.scripts:
        check_scenario_xml(script.xml)
    ws = get_workspace(workspace_id)
    if not ws:
        init_workspace(workspace_id, owner=session_username(request))
        ws = get_workspace(workspace_id)

    if ws["running"]:
        return {"error": "Workspace already running"}

    ws["bound"] = _check_binds(workspace_id, ws, req)

    # route to TX or RX based on role
    if ws["role"] == "rx":
        from workspaces.manager import run_rx_workspace
        # get RX config from first script or workspace defaults
        term_ip    = ws["ip"]
        listen_port = ws["port"]
        rx_script  = req.scripts[0] if req.scripts else None
        enable_mos = rx_script.enable_rtp if rx_script else False
        xml        = rx_script.xml if rx_script and rx_script.xml else None
        result = await run_rx_workspace(workspace_id, term_ip, listen_port, enable_mos, xml, rx_script)
        return {"status": "started", "workspace_id": workspace_id, **(result or {})}
    else:
        result = await run_workspace(workspace_id, req.scripts, req.intervals, req.continuous)
        return {"status": "started", "workspace_id": workspace_id, **(result or {})}

@router.post("/workspaces/{workspace_id}/stop")
async def workspace_stop(request: Request, workspace_id: int):
    workspace_guard(request, workspace_id)
    await stop_workspace(workspace_id)
    return {"status": "stopped", "workspace_id": workspace_id}

@router.post("/workspaces/{workspace_id}/release")
async def workspace_release(request: Request, workspace_id: int):
    """
    Frees the slot (and its IP) for reuse. Callable by the owner themselves
    ('I'm done with this workspace') or by admin on ANYONE's
    workspace — this is the "kick the person who went on vacation with a
    workspace open, release resources" capability.
    """
    username, role = workspace_guard(request, workspace_id)
    ws = get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.get("running"):
        await stop_workspace(workspace_id)
    freed_owner = ws.get("owner")
    release_workspace(workspace_id)
    return {"ok": True, "workspace_id": workspace_id, "released_from": freed_owner}

@router.post("/workspaces/{workspace_id}/force-stop")
async def workspace_force_stop(request: Request, workspace_id: int):
    """admin only — stops someone else's running workspace without releasing the slot."""
    require_role(request, auth.ELEVATED_ROLES)
    ws = get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await stop_workspace(workspace_id)
    return {"ok": True, "workspace_id": workspace_id, "owner": ws.get("owner")}

@router.get("/workspaces/{workspace_id}/ladder")
async def workspace_ladder(request: Request, workspace_id: int, script_id: int = 1):
    workspace_guard(request, workspace_id)
    from engines.sipp import parse_messages_log

    ws = get_workspace(workspace_id)
    role = ws.get("role", "tx") if ws else "tx"
    prefix = "uas" if role == "rx" else "uac"

    if role == "rx":
        sip_files = glob.glob(f"{RUN_DIR}/bscg_{prefix}_{workspace_id}_*_messages.log")
    else:
        sip_files = glob.glob(f"{RUN_DIR}/bscg_{prefix}_{workspace_id}_{script_id}_*_messages.log")

    if ws and ws.get("run_start_time"):
        run_start = ws["run_start_time"]
        recent = sorted([f for f in sip_files if os.path.getmtime(f) >= run_start - 5],
                        key=os.path.getmtime)
    else:
        # workspace not in memory (e.g. after a service restart) —
        # fall back to just the single most recent log
        recent = sorted(sip_files, key=os.path.getmtime)[-1:]

    if not recent:
        return {"calls": {}, "available_scripts": [], "log_file": ""}

    all_calls = {}
    for log_file in recent:
        calls = parse_messages_log(log_file)
        all_calls.update(calls)

    data = get_workspace_ladder(workspace_id)
    return {
        "calls": all_calls,
        "available_scripts": data.get("scripts", []),
        "log_file": os.path.basename(recent[-1]) if recent else ""
    }

def _user_workspaces_file(username: str) -> str:
    """
    Was a single shared WORKSPACES_FILE for everyone — meaning any two
    logged-in users saw and silently overwrote each other's saved side-panel
    layout, regardless of the backend workspace-ownership work elsewhere.
    This convenience "restore my UI on reload" layer never went through
    that ownership model at all. Scoping by username fixes it: a new user's
    file doesn't exist yet, so they correctly see nothing until they create
    their own workspaces.
    """
    safe = "".join(c for c in username if c.isalnum() or c in "._-") or "unknown"
    return os.path.join(WORKSPACES_DIR, f"saved_workspaces_{safe}.json")

@router.get("/workspaces/saved")
async def get_saved_workspaces(request: Request):
    """Load saved workspace configurations — scoped to the logged-in user."""
    username = session_username(request)
    path = _user_workspaces_file(username)
    if not os.path.exists(path):
        return {"workspaces": []}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {"workspaces": []}

@router.post("/workspaces/save")
async def save_workspaces(request: Request, data: dict):
    """Save workspace configurations — scoped to the logged-in user."""
    username = session_username(request)
    path = _user_workspaces_file(username)
    os.makedirs(WORKSPACES_DIR, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    return {"ok": True}
