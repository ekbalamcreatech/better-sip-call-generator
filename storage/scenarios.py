import os
import json
import glob
from datetime import datetime
from config import SCENARIOS_DIR

def scenario_filename(name: str, mode: str) -> str:
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
    return f"{mode}_{safe_name.replace(' ', '_')}.json"

def scenario_owner(name: str, mode: str) -> str:
    """Owner of an existing scenario with this name, or None if it doesn't exist yet."""
    data = load_scenario(scenario_filename(name, mode))
    return None if data is None else data.get("saved_by", "")

def save_scenario(name: str, description: str, xml: str, mode: str = "tx", saved_by: str = "") -> bool:
    try:
        path = os.path.join(SCENARIOS_DIR, scenario_filename(name, mode))
        data = {
            "name": name,
            "description": description,
            "xml": xml,
            "mode": mode,
            "saved_by": saved_by,
            "saved_at": datetime.now().isoformat()
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Save scenario error: {e}")
        return False

def list_scenarios(mode: str = None) -> list:
    try:
        pattern = os.path.join(SCENARIOS_DIR, "*.json")
        files = glob.glob(pattern)
        scenarios = []
        for f in sorted(files, key=os.path.getmtime, reverse=True):
            with open(f) as fp:
                data = json.load(fp)
            if mode and data.get("mode") != mode:
                continue
            scenarios.append({
                "name": data["name"],
                "description": data.get("description", ""),
                "mode": data.get("mode", "tx"),
                "saved_by": data.get("saved_by", ""),
                "saved_at": data.get("saved_at", ""),
                "filename": os.path.basename(f)
            })
        return scenarios
    except Exception as e:
        print(f"List scenarios error: {e}")
        return []

def _safe_scenario_path(filename: str) -> str:
    """
    filename here is client-supplied (from the URL path). save_scenario()
    already sanitizes names before writing; load/delete need the same
    treatment before reading/removing, since os.path.join does NOT strip
    '../' sequences on its own — a filename like '../../main.py' resolves
    outside SCENARIOS_DIR entirely otherwise.
    """
    base = os.path.basename(filename)  # strips any directory components
    safe = "".join(c for c in base if c.isalnum() or c in "._- ")
    path = os.path.join(SCENARIOS_DIR, safe)
    # Belt-and-suspenders: confirm the resolved path is still inside
    # SCENARIOS_DIR even after normalization.
    if os.path.realpath(path).startswith(os.path.realpath(SCENARIOS_DIR) + os.sep) or \
       os.path.realpath(path) == os.path.realpath(SCENARIOS_DIR):
        return path
    raise ValueError(f"Invalid scenario filename: {filename}")


def load_scenario(filename: str) -> dict:
    try:
        path = _safe_scenario_path(filename)
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Load scenario error: {e}")
        return None

def delete_scenario(filename: str) -> bool:
    try:
        path = _safe_scenario_path(filename)
        os.remove(path)
        return True
    except Exception as e:
        print(f"Delete scenario error: {e}")
        return False
