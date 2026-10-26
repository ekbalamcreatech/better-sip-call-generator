import os
import json
from datetime import datetime
from config import HISTORY_FILE

def save_run(mode: str, params: dict, stats: dict, mos: dict = None) -> bool:
    try:
        history = load_history()
        entry = {
            "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
            "params": params,
            "stats": stats,
            "mos": mos
        }
        history.insert(0, entry)
        history = history[:200]  # keep last 200 runs
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
        return True
    except Exception as e:
        print(f"Save history error: {e}")
        return False

def load_history(limit: int = 50) -> list:
    try:
        if not os.path.exists(HISTORY_FILE):
            return []
        with open(HISTORY_FILE) as f:
            data = json.load(f)
        return data[:limit]
    except Exception:
        return []
