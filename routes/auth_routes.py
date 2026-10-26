from fastapi import Form, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse

from engines import auth, throttle

from fastapi import APIRouter
import webguard
router = APIRouter()


_LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>A Better SIP Call Generator — Login</title>
<style>
  body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e5e5e5;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
  .box{background:#181b21;border:1px solid #2a2e37;border-radius:10px;padding:32px;width:320px}
  h1{font-size:18px;margin:0 0 20px}
  input{width:100%;box-sizing:border-box;padding:9px 10px;margin-bottom:12px;border-radius:6px;
        border:1px solid #333;background:#0f1115;color:#e5e5e5;font-size:14px}
  button{width:100%;padding:10px;border-radius:6px;border:none;background:#2563eb;color:#fff;
         font-size:14px;cursor:pointer}
  button:hover{background:#1d4ed8}
  #err{color:#f87171;font-size:13px;margin-bottom:10px;min-height:16px}
</style></head>
<body>
  <div class="box">
    <h1>A Better SIP Call Generator</h1>
    <div id="err"></div>
    <input id="u" placeholder="Username" autocomplete="username">
    <input id="p" type="password" placeholder="Password" autocomplete="current-password">
    <button onclick="doLogin()">Log in</button>
  </div>
<script>
document.getElementById('p').addEventListener('keydown', e => { if(e.key === 'Enter') doLogin(); });
async function doLogin(){
  const u = document.getElementById('u').value.trim();
  const p = document.getElementById('p').value;
  const errEl = document.getElementById('err');
  errEl.textContent = '';
  if(!u || !p){ errEl.textContent = 'Username and password required'; return; }
  const fd = new FormData();
  fd.append('username', u);
  fd.append('password', p);
  const r = await fetch('/auth/login', {method:'POST', body:fd});
  if(r.ok){ window.location.href = '/'; }
  else if(r.status === 429){ const d = await r.json().catch(()=>({})); errEl.textContent = d.detail || 'Too many attempts. Try again later.'; }
  else { errEl.textContent = 'Invalid username or password'; }
}
</script>
</body></html>"""

@router.get("/login")
async def login_page():
    return HTMLResponse(_LOGIN_PAGE_HTML)

@router.post("/auth/login")
async def auth_login(request: Request, username: str = Form(...), password: str = Form(...)):
    ip = request.client.host if request.client else "unknown"
    wait = throttle.seconds_locked(ip, username)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {wait}s.",
                            headers={"Retry-After": str(wait)})
    if not auth.authenticate(username, password):
        throttle.record_failure(ip, username)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    throttle.record_success(ip, username)
    session_id = auth.create_session(username)
    resp = JSONResponse({"ok": True, "username": username})
    resp.set_cookie(
        auth.SESSION_COOKIE_NAME, session_id,
        httponly=True, samesite="lax", path="/", secure=webguard.cookie_secure(request),
        max_age=auth.SESSION_TIMEOUT_SECONDS
    )
    return resp

@router.post("/auth/logout")
async def auth_logout(request: Request):
    session_id = request.cookies.get(auth.SESSION_COOKIE_NAME)
    if session_id:
        auth.destroy_session(session_id)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE_NAME, path="/")
    return resp

@router.get("/auth/status")
async def auth_status(request: Request):
    session_id = request.cookies.get(auth.SESSION_COOKIE_NAME)
    username = auth.get_session_username(session_id) if session_id else None
    return {
        "authenticated": username is not None,
        "username": username,
        "role": auth.get_user_role(username) if username else None,
        "seconds_remaining": auth.session_seconds_remaining(session_id) if session_id else 0
    }

@router.post("/auth/change-password")
async def auth_change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...)
):
    session_id = request.cookies.get(auth.SESSION_COOKIE_NAME)
    username = auth.get_session_username(session_id) if session_id else None
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    ok = auth.change_password(username, old_password, new_password, keep_session=session_id)
    if not ok:
        raise HTTPException(status_code=401, detail="Old password incorrect")
    return {"ok": True}
