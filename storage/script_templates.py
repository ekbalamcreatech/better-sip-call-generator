"""
storage/script_templates.py — NEW FILE

The middle layer of three: raw XML (Scenarios) -> a whole configured
SCRIPT, including its XML (this file) -> a whole WORKSPACE of scripts +
intervals (workspace_templates.py). Mirrors the exact same conventions
as both of those, including the same path-traversal fix.

Why this layer earns its place rather than being redundant with the
other two: Scenarios only saves the XML string — reloading it still
means redoing the SUT selection, calling/called numbers, CPS, codec,
DTMF, RTP impairment, auth, and STIR settings by hand. This saves the
WHOLE script object (everything Scenarios has, plus all of that
surrounding configuration) as one named, reusable unit — pull a fully-
configured script straight into any workspace's script slot, not just
its XML into an empty one.

Global/shared library, same as Scenarios and Workspace Templates.
"""
import os
import json
import glob
from datetime import datetime
from config import SCRIPT_TEMPLATES_DIR


def script_template_filename(name: str) -> str:
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
    return f"{safe_name.replace(' ', '_')}.json"


def script_template_owner(name: str):
    """Owner of an existing template with this name, or None if it doesn't exist yet."""
    data = load_script_template(script_template_filename(name))
    return None if data is None else data.get("saved_by", "")


def save_script_template(name: str, description: str, script: dict, saved_by: str = "") -> bool:
    try:
        safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
        safe_name = safe_name.replace(" ", "_")
        if not safe_name:
            return False
        path = os.path.join(SCRIPT_TEMPLATES_DIR, f"{safe_name}.json")
        data = {
            "name": name,
            "description": description,
            "script": script,
            "saved_by": saved_by,
            "saved_at": datetime.now().isoformat(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Save script template error: {e}")
        return False


def list_script_templates() -> list:
    """Lightweight metadata only — for a picker list, not the full script payload."""
    try:
        pattern = os.path.join(SCRIPT_TEMPLATES_DIR, "*.json")
        files = glob.glob(pattern)
        templates = []
        for f in sorted(files, key=os.path.getmtime, reverse=True):
            with open(f) as fp:
                data = json.load(fp)
            script = data.get("script", {})
            templates.append({
                "name": data["name"],
                "description": data.get("description", ""),
                "sut_name": script.get("sut_name", ""),
                "cps": script.get("cps"),
                "codec": script.get("codec", "PCMU"),
                "has_xml": bool(script.get("xml")),
                "saved_by": data.get("saved_by", ""),
                "saved_at": data.get("saved_at", ""),
                "filename": os.path.basename(f),
            })
        return templates
    except Exception as e:
        print(f"List script templates error: {e}")
        return []


def _safe_script_template_path(filename: str) -> str:
    """Same path-traversal fix already applied to scenarios.py and workspace_templates.py."""
    base = os.path.basename(filename)
    safe = "".join(c for c in base if c.isalnum() or c in "._- ")
    path = os.path.join(SCRIPT_TEMPLATES_DIR, safe)
    if os.path.realpath(path).startswith(os.path.realpath(SCRIPT_TEMPLATES_DIR) + os.sep) or \
       os.path.realpath(path) == os.path.realpath(SCRIPT_TEMPLATES_DIR):
        return path
    raise ValueError(f"Invalid script template filename: {filename}")


def load_script_template(filename: str) -> dict:
    try:
        path = _safe_script_template_path(filename)
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Load script template error: {e}")
        return None


def delete_script_template(filename: str) -> bool:
    try:
        path = _safe_script_template_path(filename)
        os.remove(path)
        return True
    except Exception as e:
        print(f"Delete script template error: {e}")
        return False
