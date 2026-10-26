"""AI provider settings and the scenario-generation call."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from engines import auth, llm_provider
from security import require_role, session_username

router = APIRouter()


class LlmConfig(BaseModel):
    provider: str
    model: str
    base_url: str = ""
    auth_mode: str = "api_key"


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=60000)
    max_tokens: int = Field(default=3500, ge=1, le=8000)
    api_key: str = Field(default="", max_length=512)


@router.get("/llm/info")
async def llm_info(request: Request):
    """Current provider/model for any logged-in user. Never includes a key (none is stored)."""
    session_username(request)
    return {**llm_provider.get_config(), "key_required": llm_provider.key_required()}


@router.post("/llm/config")
async def llm_set_config(request: Request, body: LlmConfig):
    """Admin only: changes where every user's scenario prompts are sent."""
    require_role(request, {auth.ROLE_ADMIN})
    try:
        cfg = llm_provider.save_config(body.provider, body.model, body.base_url or None, body.auth_mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "config": {**cfg, "key_required": llm_provider.key_required()}}


@router.post("/llm/generate")
async def llm_generate(request: Request, body: GenerateRequest):
    """Send one scenario prompt to the configured AI service. The key is used for this call only."""
    session_username(request)
    try:
        text = await llm_provider.generate(body.api_key.strip(), body.prompt, body.max_tokens)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # the provider's message is useful; the key is never part of it
        msg = str(e).replace(body.api_key, "***") if body.api_key else str(e)
        raise HTTPException(status_code=502, detail=f"AI service error: {msg[:300]}")
    return {"text": text}
