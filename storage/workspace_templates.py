"""
storage/workspace_templates.py — NEW FILE

Save/load a WHOLE workspace configuration as one named unit — role, IP,
port, every script (including its generated XML), every interval — the
workspace-level equivalent of the existing Scenarios library (which only
saves a single script's XML). Mirrors that same file structure and
conventions deliberately, including the same path-traversal fix already
applied there (load/delete sanitize the filename the same way save does).

Global/shared library, same as Scenarios — not per-user. This is a
deliberate choice, matching the existing convention: a saved workspace
template ("REGISTER Auth Test Rig") is meant to be a reusable team asset,
not something siloed to whoever happened to save it first.
"""
import os
import json
import glob
from datetime import datetime
from config import WORKSPACE_TEMPLATES_DIR


def workspace_template_filename(name: str) -> str:
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
    return f"{safe_name.replace(' ', '_')}.json"


def workspace_template_owner(name: str):
    """Owner of an existing template with this name, or None if it doesn't exist yet."""
    data = load_workspace_template(workspace_template_filename(name))
    return None if data is None else data.get("saved_by", "")


def save_workspace_template(name: str, description: str, role: str, ip: str,
                             port: int, scripts: list, intervals: list,
                             saved_by: str = "") -> bool:
    try:
        safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
        safe_name = safe_name.replace(" ", "_")
        if not safe_name:
            return False
        path = os.path.join(WORKSPACE_TEMPLATES_DIR, f"{safe_name}.json")
        data = {
            "name": name,
            "description": description,
            "role": role,
            "ip": ip,
            "port": port,
            "scripts": scripts,
            "intervals": intervals,
            "saved_by": saved_by,
            "saved_at": datetime.now().isoformat(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Save workspace template error: {e}")
        return False


def list_workspace_templates() -> list:
    """Lightweight metadata only — for a picker list, not the full payload (which may include large XML)."""
    try:
        pattern = os.path.join(WORKSPACE_TEMPLATES_DIR, "*.json")
        files = glob.glob(pattern)
        templates = []
        for f in sorted(files, key=os.path.getmtime, reverse=True):
            with open(f) as fp:
                data = json.load(fp)
            templates.append({
                "name": data["name"],
                "description": data.get("description", ""),
                "role": data.get("role", "tx"),
                "script_count": len(data.get("scripts", [])),
                "interval_count": len(data.get("intervals", [])),
                "saved_by": data.get("saved_by", ""),
                "saved_at": data.get("saved_at", ""),
                "filename": os.path.basename(f),
            })
        return templates
    except Exception as e:
        print(f"List workspace templates error: {e}")
        return []


def _safe_template_path(filename: str) -> str:
    """Same path-traversal fix already applied to storage/scenarios.py — see that file for the full reasoning."""
    base = os.path.basename(filename)
    safe = "".join(c for c in base if c.isalnum() or c in "._- ")
    path = os.path.join(WORKSPACE_TEMPLATES_DIR, safe)
    if os.path.realpath(path).startswith(os.path.realpath(WORKSPACE_TEMPLATES_DIR) + os.sep) or \
       os.path.realpath(path) == os.path.realpath(WORKSPACE_TEMPLATES_DIR):
        return path
    raise ValueError(f"Invalid workspace template filename: {filename}")


def load_workspace_template(filename: str) -> dict:
    try:
        path = _safe_template_path(filename)
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Load workspace template error: {e}")
        return None


def delete_workspace_template(filename: str) -> bool:
    try:
        path = _safe_template_path(filename)
        os.remove(path)
        return True
    except Exception as e:
        print(f"Delete workspace template error: {e}")
        return False
