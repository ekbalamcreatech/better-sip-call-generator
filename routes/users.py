from fastapi import Form, HTTPException, Request

from engines import auth

from fastapi import APIRouter
from security import require_role
router = APIRouter()


@router.get("/users")
async def list_users_route(request: Request):
    require_role(request, {auth.ROLE_ADMIN})
    return {"users": auth.list_users()}

@router.post("/users")
async def create_user_route(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(auth.ROLE_USER),
    max_workspaces: int = Form(None)
):
    require_role(request, {auth.ROLE_ADMIN})

    ok, err = auth.create_user(username, password, role, max_workspaces=max_workspaces)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"ok": True, "users": auth.list_users()}

@router.delete("/users/{username}")
async def delete_user_route(request: Request, username: str):
    caller, _ = require_role(request, {auth.ROLE_ADMIN})
    if username == caller:
        raise HTTPException(status_code=400, detail="Cannot delete your own account while logged in as it")
    ok, err = auth.delete_user(username)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"ok": True, "users": auth.list_users()}

@router.post("/users/{username}/role")
async def set_user_role_route(request: Request, username: str, role: str = Form(...)):
    require_role(request, {auth.ROLE_ADMIN})
    ok, err = auth.set_user_role(username, role)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"ok": True, "users": auth.list_users()}

@router.post("/users/{username}/max-workspaces")
async def set_user_max_workspaces_route(request: Request, username: str, max_workspaces: int = Form(None)):
    """
    Adjust one account's own workspace allotment — independent of the
    This is the "give this one person 6 while everyone else has the
    default" lever. Pass no value (or omit the form field) to clear the
    override and fall back to the default limit.
    """
    require_role(request, {auth.ROLE_ADMIN})
    ok, err = auth.set_user_max_workspaces(username, max_workspaces)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"ok": True, "users": auth.list_users()}
