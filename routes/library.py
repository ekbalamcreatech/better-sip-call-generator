from fastapi import HTTPException, Request

from storage.scenarios import save_scenario, list_scenarios, load_scenario, delete_scenario, scenario_owner
from storage.workspace_templates import (
    save_workspace_template, list_workspace_templates,
    load_workspace_template, delete_workspace_template, workspace_template_owner
)
from storage.script_templates import (
    save_script_template, list_script_templates,
    load_script_template, delete_script_template, script_template_owner
)
from models import (
    ScenarioSave, WorkspaceTemplateSave, ScriptTemplateSave
)

from fastapi import APIRouter
from typing import Literal
from security import session_username, owner_guard, check_scenario_xml
router = APIRouter()


# ─── Scenarios ────────────────────────────────────────────────────────────────
@router.post("/scenarios/save")
async def save_scenario_route(request: Request, req: ScenarioSave):
    username = session_username(request)
    check_scenario_xml(req.xml)
    existing = scenario_owner(req.name, req.mode)
    if existing is not None:
        owner_guard(request, existing, "scenario")
    ok = save_scenario(req.name, req.description, req.xml, req.mode, saved_by=existing or username)
    return {"ok": ok}

@router.get("/scenarios/list/{mode}")
async def list_scenarios_route(mode: Literal["tx", "rx"]):
    return {"scenarios": list_scenarios(mode)}

@router.get("/scenarios/load/{filename}")
async def load_scenario_route(filename: str):
    data = load_scenario(filename)
    return data or {"error": "not found"}

@router.delete("/scenarios/{filename}")
async def delete_scenario_route(request: Request, filename: str):
    data = load_scenario(filename)
    owner_guard(request, (data or {}).get("saved_by", ""), "scenario")
    ok = delete_scenario(filename)
    return {"ok": ok}

# ─── Workspace Templates (save/load a WHOLE workspace as one named unit) ─────
# Shared/global library, same as Scenarios above — a saved workspace template
# is meant to be a reusable team asset, not siloed to whoever saved it first.
@router.post("/workspace-templates/save")
async def save_workspace_template_route(request: Request, req: WorkspaceTemplateSave):
    username = session_username(request)
    existing = workspace_template_owner(req.name)
    if existing is not None:
        owner_guard(request, existing, "workspace template")
    ok = save_workspace_template(
        req.name, req.description, req.role, req.ip, req.port,
        req.scripts, req.intervals, saved_by=existing or username
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to save workspace template — check the name isn't empty")
    return {"ok": True}

@router.get("/workspace-templates/list")
async def list_workspace_templates_route(request: Request):
    session_username(request)
    return {"templates": list_workspace_templates()}

@router.get("/workspace-templates/load/{filename}")
async def load_workspace_template_route(request: Request, filename: str):
    session_username(request)
    data = load_workspace_template(filename)
    if not data:
        raise HTTPException(status_code=404, detail="Workspace template not found")
    return data

@router.delete("/workspace-templates/{filename}")
async def delete_workspace_template_route(request: Request, filename: str):
    data = load_workspace_template(filename)
    owner_guard(request, (data or {}).get("saved_by", ""), "workspace template")
    ok = delete_workspace_template(filename)
    return {"ok": ok}

# ─── Script Templates (save/load a whole SCRIPT — SUT, numbers, codec, DTMF,
# RTP impairment, auth, STIR, XML — as one named unit). The middle layer
# between raw XML (Scenarios) and a whole Workspace (workspace-templates
# above) — same shared/global library, same access level.
@router.post("/script-templates/save")
async def save_script_template_route(request: Request, req: ScriptTemplateSave):
    username = session_username(request)
    check_scenario_xml((req.script or {}).get("xml", ""))
    existing = script_template_owner(req.name)
    if existing is not None:
        owner_guard(request, existing, "script template")
    ok = save_script_template(req.name, req.description, req.script, saved_by=existing or username)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to save script template — check the name isn't empty")
    return {"ok": True}

@router.get("/script-templates/list")
async def list_script_templates_route(request: Request):
    session_username(request)
    return {"templates": list_script_templates()}

@router.get("/script-templates/load/{filename}")
async def load_script_template_route(request: Request, filename: str):
    session_username(request)
    data = load_script_template(filename)
    if not data:
        raise HTTPException(status_code=404, detail="Script template not found")
    return data

@router.delete("/script-templates/{filename}")
async def delete_script_template_route(request: Request, filename: str):
    data = load_script_template(filename)
    owner_guard(request, (data or {}).get("saved_by", ""), "script template")
    ok = delete_script_template(filename)
    return {"ok": ok}
