from fastapi import HTTPException, Request

from workspaces.manager import (
    get_workspace
)
from engines import auth
from engines.scenario_guard import validate_scenario_xml, ScenarioRejected


def session_username(request: Request) -> str:
    """
    The auth middleware already guarantees a valid session exists for any
    route reaching this point (everything except the exempt paths) — this
    just extracts who it belongs to.
    """
    session_id = request.cookies.get(auth.SESSION_COOKIE_NAME)
    username = auth.get_session_username(session_id)
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in")
    return username

def require_role(request: Request, allowed_roles: set):
    username = session_username(request)
    role = auth.get_user_role(username)
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions for this action")
    return username, role

def workspace_guard(request: Request, workspace_id: int):
    """
    Enforces the isolation model: a 'user'-role account can only touch its
    own workspaces (or an unclaimed slot — nothing sensitive lives there).
    admins can touch anything, which is the whole point of their
    oversight capability (force-stop, force-release someone's abandoned
    workspace). Returns (username, role) for the caller's convenience.
    """
    username = session_username(request)
    role = auth.get_user_role(username)
    if role in auth.ELEVATED_ROLES:
        return username, role
    ws = get_workspace(workspace_id)
    owner = ws.get("owner") if ws else None
    if owner is not None and owner != username:
        raise HTTPException(status_code=403, detail="This workspace belongs to another user")
    return username, role


def check_scenario_xml(xml: str) -> None:
    """HTTP 400 if the scenario XML contains something we refuse to run or store."""
    try:
        validate_scenario_xml(xml)
    except ScenarioRejected as e:
        raise HTTPException(status_code=400, detail=str(e))


def owner_guard(request: Request, owner: str, what: str = "item") -> str:
    """
    Library items (scenarios, templates, SUTs) are shared for everyone to read
    and copy, but only their creator or an admin may overwrite or delete them.
    Items with no recorded owner (e.g. seeded defaults) are admin-only.
    """
    username = session_username(request)
    if auth.get_user_role(username) in auth.ELEVATED_ROLES or (owner and owner == username):
        return username
    who = f"owned by {owner}" if owner else "a built-in item"
    raise HTTPException(
        status_code=403,
        detail=f"This {what} is {who}. You can load it and save it under a new name to make your own copy.",
    )
