from fastapi.responses import Response
import os

from engines.stirshaken import (
    generate_keypair, generate_passport, verify_passport,
    get_cert_info, upload_cert, CERT_FILE
)

from fastapi import APIRouter, Request
from engines import auth
from security import require_role
router = APIRouter()


# ─── STIR/SHAKEN ──────────────────────────────────────────────────────────────
@router.get("/stir/cert")
async def serve_stir_cert():
    if not os.path.exists(CERT_FILE):
        generate_keypair()
    with open(CERT_FILE, 'rb') as f:
        cert_pem = f.read()
    return Response(content=cert_pem, media_type="application/x-pem-file")

@router.get("/stir/info")
async def stir_info():
    return get_cert_info()

@router.post("/stir/generate")
async def stir_generate(data: dict):
    return generate_passport(
        data.get("orig_tn", "5550001"),
        data.get("dest_tn", "9723612348"),
        data.get("attestation", "A"),
        data.get("orig_id"),
        expires=data.get("expires", 60)
    )

@router.post("/stir/verify")
async def stir_verify(data: dict):
    identity = data.get("identity_header", "")
    if not identity:
        return {"error": "identity_header required"}
    return verify_passport(identity)

@router.post("/stir/regenerate-cert")
async def stir_regen(request: Request):
    require_role(request, auth.ELEVATED_ROLES)
    ok = generate_keypair()
    return {"ok": ok, "cert_info": get_cert_info()}

@router.post("/stir/upload-cert")
async def stir_upload(request: Request, data: dict):
    require_role(request, auth.ELEVATED_ROLES)
    cert_pem = data.get("cert_pem", "").encode()
    key_pem  = data.get("key_pem", "").encode()
    if not cert_pem or not key_pem:
        return {"error": "cert_pem and key_pem required"}
    ok = upload_cert(cert_pem, key_pem)
    return {"ok": ok, "cert_info": get_cert_info() if ok else None}
