import os
import json
from config import BASE_DIR

REGISTRY_FILE = os.path.join(BASE_DIR, "storage", "sut_registry.json")

def load_suts() -> list:
    try:
        if not os.path.exists(REGISTRY_FILE):
            # seed with defaults
            defaults = [
                {"name": "Local-UAS", "ip": "127.0.0.1", "port": "5060"},
            ]
            save_suts(defaults)
            return defaults
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    except Exception as e:
        print(f"SUT load error: {e}")
        return []

def save_suts(suts: list) -> bool:
    try:
        with open(REGISTRY_FILE, "w") as f:
            json.dump(suts, f, indent=2)
        return True
    except Exception as e:
        print(f"SUT save error: {e}")
        return False

def sut_owner(name: str):
    """created_by of the named SUT ('' for built-ins), or None if it doesn't exist."""
    for s in load_suts():
        if s["name"] == name:
            return s.get("created_by", "")
    return None

def add_sut(name: str, ip: str, port: str, created_by: str = "") -> bool:
    suts = load_suts()
    # check for duplicate name
    if any(s["name"] == name for s in suts):
        return False
    suts.append({"name": name, "ip": ip, "port": port, "created_by": created_by})
    return save_suts(suts)

def update_sut(name: str, ip: str, port: str) -> bool:
    suts = load_suts()
    for s in suts:
        if s["name"] == name:
            s["ip"] = ip
            s["port"] = port
            return save_suts(suts)
    return False

def delete_sut(name: str) -> bool:
    suts = load_suts()
    suts = [s for s in suts if s["name"] != name]
    return save_suts(suts)
