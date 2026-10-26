import os
import re

from workspaces.manager import (
    ports_in_use_on_ip
)
from engines.audio import get_audio_files, get_audio_duration, calculate_call_duration
from storage.history import load_history
from storage.sut_registry import load_suts, add_sut, update_sut, delete_sut, sut_owner
from pydantic import BaseModel, field_validator

from fastapi import APIRouter, Request
from security import session_username, owner_guard, require_role
from engines import auth
from netutil import local_ipv4s
from config import AUDIO_DIR
router = APIRouter()


# ─── Health ───────────────────────────────────────────────────────────────────
@router.get("/health")
async def health():
    return {"ok": True, "app": "A Better SIP Call Generator"}

# ─── Interfaces ───────────────────────────────────────────────────────────────
@router.get("/interfaces")
async def get_interfaces():
    ips = [ip for ip in local_ipv4s()]
    # Annotate each discovered IP with whether a live workspace already
    # claims it, and by whom — lets the frontend grey out / label taken
    # IPs instead of letting two users silently collide on the same one.
    # An IP is never "taken" — only a specific (ip, port) pair is. This
    # lists what ports are currently claimed on each IP, informational
    # only; the frontend should never disable an IP option based on this.
    annotated = [{"ip": ip, "ports_in_use": ports_in_use_on_ip(ip)} for ip in ips]
    return {"ips": ips, "interfaces": annotated}

# ─── SUTs ─────────────────────────────────────────────────────────────────────
_SUT_NAME = re.compile(r"^[A-Za-z0-9 ._()\-]{1,64}$")
_HOST = re.compile(r"^[A-Za-z0-9.\-:]{1,255}$")


class SUTEntry(BaseModel):
    name: str
    ip: str
    port: str = "5060"

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v):
        if not _SUT_NAME.match(v):
            raise ValueError("name: 1-64 chars, letters, digits, space and . _ - ( ) only")
        return v

    @field_validator("ip")
    @classmethod
    def _ip_ok(cls, v):
        if not _HOST.match(v):
            raise ValueError("ip: must be an IP address or hostname")
        return v

    @field_validator("port")
    @classmethod
    def _port_ok(cls, v):
        if not (v.isdigit() and 0 < int(v) < 65536):
            raise ValueError("port: must be 1-65535")
        return v


@router.get("/suts")
async def get_suts():
    return {"suts": load_suts()}

@router.post("/suts")
async def create_sut(request: Request, entry: SUTEntry):
    username = session_username(request)  # any logged-in user may add a SUT
    ok = add_sut(entry.name, entry.ip, entry.port, created_by=username)
    return {"ok": ok, "error": "Name already exists" if not ok else None}

@router.put("/suts/{name}")
async def update_sut_entry(request: Request, name: str, entry: SUTEntry):
    owner = sut_owner(name)
    if owner is None:
        return {"ok": False}
    owner_guard(request, owner, "SUT")
    ok = update_sut(name, entry.ip, entry.port)
    return {"ok": ok}

@router.delete("/suts/{name}")
async def delete_sut_entry(request: Request, name: str):
    owner = sut_owner(name)
    if owner is not None:
        owner_guard(request, owner, "SUT")
    ok = delete_sut(name)
    return {"ok": ok}

# ─── Audio ────────────────────────────────────────────────────────────────────
@router.get("/audio/files")
async def list_audio():
    return {"files": get_audio_files()}

@router.post("/audio/duration")
async def audio_duration(data: dict):
    filename    = os.path.basename(data.get("filename", "reference.wav"))  # strip any '../' components
    mode        = data.get("mode", "plays")
    value       = int(data.get("value", 2))
    audio_path  = os.path.join(AUDIO_DIR, filename)
    duration_ms = calculate_call_duration(audio_path, mode, value)
    file_dur    = get_audio_duration(audio_path)
    return {
        "duration_ms": duration_ms,
        "duration_s":  duration_ms / 1000,
        "file_duration_s": file_dur,
        "display": f"{duration_ms/1000:.1f}s"
    }

# ─── History ──────────────────────────────────────────────────────────────────
@router.get("/history")
async def get_history(request: Request):
    require_role(request, auth.ELEVATED_ROLES)   # run history is not per-user, so admins only
    return {"history": load_history()}
