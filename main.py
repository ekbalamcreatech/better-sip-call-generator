from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
import os

from engines.stirshaken import (
    generate_keypair, KEY_FILE
)
from engines import auth

from routes import auth_routes, users, system, workspaces, library, media, quality, stir, llm
from config import RUN_DIR, STIR_DIR
from procutil import reap_orphans
import webguard
from fsutil import private_dir, tighten

app = FastAPI(title="A Better SIP Call Generator")

# Was allow_origins=["*"] — wildcard CORS combined with the (now-removed)
# lack of auth meant any website a browser on this network visited could
# script requests against this server. The frontend is served from this
# same app (StaticFiles mount below), so it's same-origin and doesn't need
# CORS at all in the normal case. SIPPTESTER_ALLOWED_ORIGINS lets an operator
# add specific additional origins (e.g. a separate frontend deployment)
# without reopening this to everyone.
_allowed_origins = webguard.allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Auth: paths reachable without a valid session ─────────────────────────
# Keep this list short and deliberate — everything else requires login.
_AUTH_EXEMPT_PATHS = {"/login", "/auth/login", "/health"}

@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.url.path in _AUTH_EXEMPT_PATHS:
        return await call_next(request)

    session_id = request.cookies.get(auth.SESSION_COOKIE_NAME)
    if not session_id or not auth.touch_session(session_id):
        # Root page load (the SPA's own entry point) — send them to the
        # login page instead of a raw 401. Everything else (API calls,
        # the SPA's own fetch() calls, static assets) gets a clean JSON
        # 401 that the frontend's fetch wrapper catches and redirects on.
        if request.method == "GET" and request.url.path == "/":
            return RedirectResponse(url="/login")
        return JSONResponse(status_code=401, content={"error": "authentication required"})

    return await call_next(request)

# ─── Browser protections ──────────────────────────────────────────────────────
@app.middleware("http")
async def browser_protections(request: Request, call_next):
    """Reject cross-site state-changing requests (CSRF) and add security headers."""
    if webguard.cross_site_blocked(request):
        return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})
    response = await call_next(request)
    for name, value in webguard.SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    # The UI is plain JS/HTML with no build step. Make the browser re-check every file on each load
    # (a cheap 304 when unchanged) so an upgrade can never run new HTML against old cached scripts.
    path = request.url.path
    if request.method == "GET" and (path == "/" or path.endswith((".js", ".css", ".html"))):
        response.headers["Cache-Control"] = "no-cache"
    return response

# ─── Shutdown ─────────────────────────────────────────────────────────────────
@app.on_event("shutdown")
async def shutdown():
    """Clean stop (SIGTERM / systemctl stop): end every running test and capture."""
    from workspaces.manager import stop_workspace
    from workspaces.state import _workspaces
    for wid, ws in list(_workspaces.items()):
        if ws.get("running"):
            await stop_workspace(wid)

# ─── Startup ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    private_dir(STIR_DIR)
    auth.ensure_default_admin()

    # A previous crash or kill -9 can leave SIPp/tcpdump running against the
    # target with nobody controlling them. Nothing is running yet, so any
    # such process is an orphan.
    leftover = reap_orphans(RUN_DIR)
    if leftover:
        print(f"WARNING: could not stop orphaned processes: {leftover}")

    # generate STIR keypair if needed
    if not os.path.exists(os.path.join(STIR_DIR, "stir_key.pem")):
        generate_keypair()
        print("STIR/SHAKEN keypair generated")
    tighten(KEY_FILE)

    # clean up old log files (keep last 100 per pattern)
    import glob as _glob
    log_patterns = [
        RUN_DIR + "/bscg_uac_*_messages.log",
        RUN_DIR + "/bscg_uac_*_errors.log",
        RUN_DIR + "/bscg_uas_*_messages.log",
        RUN_DIR + "/bscg_uas_*_errors.log",
        RUN_DIR + "/scenario_uac_*_messages.log",
        RUN_DIR + "/scenario_uac_*_errors.log",
    ]
    for pattern in log_patterns:
        files = sorted(_glob.glob(pattern), key=os.path.getmtime, reverse=True)
        for old_file in files[100:]:
            try:
                os.remove(old_file)
            except:
                pass

    # clean up stale CSV prev files
    for f in _glob.glob(os.path.join(RUN_DIR, "sipp_tx_stats_*.csv.prev")):
        try:
            os.remove(f)
        except:
            pass

for _mod in (auth_routes, users, system, workspaces, library, media, quality, stir, llm):
    app.include_router(_mod.router)

# Static frontend: must be registered last so it never shadows an API route.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
