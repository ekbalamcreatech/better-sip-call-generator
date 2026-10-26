"""
engines/auth.py — NEW FILE

Session-based login for the A Better SIP Call Generator web UI. Deliberately minimal:
stdlib-only password hashing (PBKDF2-HMAC-SHA256, no new dependency to
install), in-memory session store with a sliding-window inactivity
timeout, and a bootstrap admin account generated on first run.

Design choices, stated explicitly:

- In-memory sessions (not persisted to disk/DB). A service restart forces
  everyone to log in again. This is the same accepted pattern already used
  for `_workspaces` elsewhere in this project — and for a login session
  specifically, "restart invalidates sessions" is a reasonable security
  default, not just a shortcut.
- Sliding window: any authenticated request touches the session and resets
  its inactivity clock. This means a session stays alive indefinitely
  during an actively-monitored live test (status polling counts as
  activity) and only expires once requests genuinely stop — which is the
  correct behavior, not a bug: you don't want to get logged out mid-test.
- Single shared admin account model for now (no per-user roles). Multi-user
  RBAC is a real feature but a separate one — flagged, not built here.
"""
import os
import json
import hmac
import hashlib
import secrets
import time

from fsutil import private_dir, tighten, write_private

AUTH_FILE = os.path.join(os.path.dirname(__file__), "..", "storage", "auth_users.json")
_LEGACY_BOOTSTRAP_PW_FILE = os.path.join(os.path.dirname(__file__), "..", "storage", "INITIAL_ADMIN_PASSWORD.txt")

SESSION_TIMEOUT_SECONDS = int(os.environ.get("SIPPTESTER_SESSION_TIMEOUT_MINUTES", "20")) * 60
SESSION_COOKIE_NAME = "bscg_session"

# ─── Roles ───────────────────────────────────────────────────────────────────
# user  — normal operator. Isolated view: sees/controls only their own
#         workspaces. Can see whether an IP/slot is taken and by whom (useful
#         for coordination) but not the other person's test config.
# admin — everything a user can do, PLUS: see all workspaces, force-stop or
#         force-release anyone's workspace, manage user accounts, manage the
#         STIR certificate, view run history, and edit/delete anyone's saved
#         SUTs, scenarios and templates. There is always at least one admin:
#         the last one can't be deleted or demoted, so nobody gets locked out.
ROLE_USER = "user"
ROLE_ADMIN = "admin"
VALID_ROLES = {ROLE_USER, ROLE_ADMIN}
ELEVATED_ROLES = {ROLE_ADMIN}  # can see/manage all workspaces
LEGACY_ROLES = {"super_admin": ROLE_ADMIN}  # older installs had a third role; it maps to admin

# In-memory session store: session_id -> {"username": str, "last_activity": float}
_sessions = {}

PBKDF2_ITERATIONS = 260_000


# ─── Password hashing (stdlib only) ────────────────────────────────────────

def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except Exception:
        return False


# ─── User storage ───────────────────────────────────────────────────────────

def _load_users():
    if not os.path.exists(AUTH_FILE):
        return {}
    with open(AUTH_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_users(users):
    private_dir(os.path.dirname(AUTH_FILE))
    write_private(AUTH_FILE, json.dumps(users, indent=2))


def _migrate_legacy_roles():
    """
    Fixes a real gap: ensure_default_admin() below only assigns a role when
    creating a BRAND NEW auth_users.json. An install that already had
    auth_users.json from before roles existed (e.g. deployed the
    auth-only patch, then the multi-tenant patch on top) has user records
    with no "role" key at all — and get_user_role()'s runtime fallback
    quietly treats that as ROLE_USER, silently demoting what was meant to
    be full admin access. Pre-role installs only ever had one implicit
    full-power account, so any user record missing "role" entirely (not
    explicitly set to "user" — that's a real, later admin decision and
    must be left alone) gets promoted to admin, once, and persisted.
    """
    users = _load_users()
    changed = False
    for uname, entry in users.items():
        if entry.get("role") in LEGACY_ROLES:
            entry["role"] = LEGACY_ROLES[entry["role"]]
            changed = True
            print(f"[auth] Migrated '{uname}' from a legacy role to admin.")
        if "role" not in entry:
            entry["role"] = ROLE_ADMIN
            changed = True
            print(f"[auth] Migrated pre-existing user '{uname}' with no role field — assigned admin (pre-role installs had implicit full access).")
    if changed:
        _save_users(users)


def ensure_default_admin():
    """
    Called once on startup. If no users file exists yet, create an admin
    account with a random password (never a hardcoded default) and print it
    to the console / service log ONE TIME. It is never written to disk.
    Set SIPPTESTER_INITIAL_ADMIN_PASSWORD (8+ chars) to choose it yourself
    (for automated installs); it is then not printed.

    Older versions also saved the password to storage/INITIAL_ADMIN_PASSWORD.txt;
    that file is removed here if it is still lying around.
    """
    if os.path.exists(_LEGACY_BOOTSTRAP_PW_FILE):
        try:
            os.remove(_LEGACY_BOOTSTRAP_PW_FILE)
            print("[auth] Removed leftover INITIAL_ADMIN_PASSWORD.txt (the password is no longer stored on disk).")
        except OSError as e:
            print(f"[auth] WARNING: could not remove {_LEGACY_BOOTSTRAP_PW_FILE}: {e}")

    if os.path.exists(AUTH_FILE):
        tighten(AUTH_FILE)
        _migrate_legacy_roles()
        return

    preset = os.environ.get("SIPPTESTER_INITIAL_ADMIN_PASSWORD", "")
    if preset and len(preset) < 8:
        raise SystemExit("SIPPTESTER_INITIAL_ADMIN_PASSWORD must be at least 8 characters")
    password = preset or secrets.token_urlsafe(12)
    _save_users({"admin": {"password_hash": hash_password(password), "role": ROLE_ADMIN}})

    if preset:
        print("[auth] First run: created account 'admin' with the password from SIPPTESTER_INITIAL_ADMIN_PASSWORD.")
        return
    print(
        "\n"
        "==================================================================\n"
        " First run — no admin account existed yet.\n"
        "   username: admin\n"
        f"   password: {password}\n"
        "\n"
        " Shown ONCE and not stored anywhere. Log in and change it.\n"
        " (systemd: journalctl -u <service> | grep -A3 'First run')\n"
        "==================================================================\n"
    )


def get_user_role(username: str):
    users = _load_users()
    entry = users.get(username)
    if not entry:
        return None
    # Fallback for any pre-role-system user record — treat as least-privileged
    # rather than erroring, so this can never accidentally grant elevation.
    return entry.get("role", ROLE_USER)


def get_user_max_workspaces(username: str, default: int):
    """
    Returns this account's own per-user workspace cap, or `default` (supplied by
    the caller) if this account has no explicit override set.
    """
    users = _load_users()
    entry = users.get(username)
    if not entry:
        return default
    override = entry.get("max_workspaces")
    return override if override is not None else default


def count_admins() -> int:
    users = _load_users()
    return sum(1 for u in users.values() if u.get("role") == ROLE_ADMIN)


def list_users() -> list:
    """
    Returns [{username, role, max_workspaces}] — never exposes password
    hashes. max_workspaces is null/None when the account has no
    per-user override and is just using the default.
    """
    users = _load_users()
    return [
        {"username": u, "role": v.get("role", ROLE_USER), "max_workspaces": v.get("max_workspaces")}
        for u, v in users.items()
    ]


def create_user(username: str, password: str, role: str, max_workspaces: int = None):
    """
    Returns (ok: bool, error: str|None). max_workspaces is an optional
    per-account override of the default workspace cap.
    Leave None to use the default.
    """
    username = username.strip()
    if not username or not all(c.isalnum() or c in "._-" for c in username):
        return False, "Username must be non-empty and contain only letters, numbers, '.', '_', '-'"
    if role not in VALID_ROLES:
        return False, f"Role must be one of: {', '.join(sorted(VALID_ROLES))}"
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if max_workspaces is not None and max_workspaces < 0:
        return False, "max_workspaces cannot be negative"
    users = _load_users()
    if username in users:
        return False, f"User '{username}' already exists"
    entry = {"password_hash": hash_password(password), "role": role}
    if max_workspaces is not None:
        entry["max_workspaces"] = max_workspaces
    users[username] = entry
    _save_users(users)
    return True, None


def set_user_max_workspaces(username: str, max_workspaces):
    """
    Returns (ok: bool, error: str|None). Pass None to clear the override
    and fall back to the default again.
    """
    users = _load_users()
    if username not in users:
        return False, f"User '{username}' does not exist"
    if max_workspaces is not None:
        if max_workspaces < 0:
            return False, "max_workspaces cannot be negative"
        users[username]["max_workspaces"] = max_workspaces
    else:
        users[username].pop("max_workspaces", None)
    _save_users(users)
    return True, None


def delete_user(username: str):
    """Returns (ok: bool, error: str|None). Refuses to delete the last admin."""
    users = _load_users()
    if username not in users:
        return False, f"User '{username}' does not exist"
    if users[username].get("role") == ROLE_ADMIN and count_admins() <= 1:
        return False, "Cannot delete the last admin account — create another admin first"
    del users[username]
    _save_users(users)
    invalidate_user_sessions(username)
    return True, None


def set_user_role(username: str, role: str):
    """Returns (ok: bool, error: str|None). Refuses to demote the last admin."""
    users = _load_users()
    if username not in users:
        return False, f"User '{username}' does not exist"
    if role not in VALID_ROLES:
        return False, f"Role must be one of: {', '.join(sorted(VALID_ROLES))}"
    if users[username].get("role") == ROLE_ADMIN and role != ROLE_ADMIN and count_admins() <= 1:
        return False, "Cannot demote the last admin account — promote another user first"
    users[username]["role"] = role
    _save_users(users)
    invalidate_user_sessions(username)  # role change: make them sign in again
    return True, None


def authenticate(username: str, password: str) -> bool:
    users = _load_users()
    entry = users.get(username)
    if not entry:
        return False
    return verify_password(password, entry["password_hash"])


def change_password(username: str, old_password: str, new_password: str, keep_session: str = None) -> bool:
    if not authenticate(username, old_password):
        return False
    users = _load_users()
    if username not in users:
        return False
    users[username]["password_hash"] = hash_password(new_password)
    _save_users(users)
    invalidate_user_sessions(username, keep=keep_session)  # other devices must sign in again
    return True


# ─── Session management ─────────────────────────────────────────────────────

def create_session(username: str) -> str:
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = {"username": username, "last_activity": time.time()}
    return session_id


def invalidate_user_sessions(username: str, keep: str = None) -> int:
    """Log `username` out everywhere (except the `keep` session). Returns how many were ended."""
    ids = [sid for sid, e in _sessions.items() if e["username"] == username and sid != keep]
    for sid in ids:
        del _sessions[sid]
    return len(ids)


def touch_session(session_id: str) -> bool:
    """
    Validates the session and, if valid, refreshes its inactivity clock
    (sliding-window timeout). Returns False and removes the session if it's
    missing or has been idle longer than SESSION_TIMEOUT_SECONDS.
    """
    entry = _sessions.get(session_id)
    if not entry:
        return False
    if time.time() - entry["last_activity"] > SESSION_TIMEOUT_SECONDS:
        del _sessions[session_id]
        return False
    entry["last_activity"] = time.time()
    return True


def get_session_username(session_id: str):
    entry = _sessions.get(session_id)
    return entry["username"] if entry else None


def destroy_session(session_id: str):
    _sessions.pop(session_id, None)


def session_seconds_remaining(session_id: str):
    entry = _sessions.get(session_id)
    if not entry:
        return 0
    elapsed = time.time() - entry["last_activity"]
    return max(0, int(SESSION_TIMEOUT_SECONDS - elapsed))
