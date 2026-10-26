from fastapi import Request
from fastapi.responses import FileResponse
import shutil
import subprocess
import os
import glob
import time

from workspaces.manager import (
    get_workspace
)

from fastapi import APIRouter
from security import workspace_guard
from config import RUN_DIR
router = APIRouter()


# ─── PCAP Export ──────────────────────────────────────────────────────────────
@router.get("/pcap/{workspace_id}")
async def export_pcap(request: Request, workspace_id: int, script_id: int = 1):
    workspace_guard(request, workspace_id)
    from engines.pcap import build_pcap

    ws = get_workspace(workspace_id)

    # try RTP+SIP merged capture first
    rtp_pcap = f"{RUN_DIR}/rtp_ws{workspace_id}_capture.pcap"
    if not os.path.exists(rtp_pcap):
        old_pcap = f"{RUN_DIR}/rtp_tx_capture.pcap"
        if os.path.exists(old_pcap) and (time.time() - os.path.getmtime(old_pcap)) < 7200:
            rtp_pcap = old_pcap

    # Only serve a capture that was refreshed during this run; a leftover file
    # (e.g. tcpdump failed to start) must not be passed off as current data.
    pcap_is_fresh = (
        os.path.exists(rtp_pcap)
        and os.path.getsize(rtp_pcap) > 100
        and (not ws or not ws.get("run_start_time") or os.path.getmtime(rtp_pcap) >= ws["run_start_time"] - 5)
    )

    if pcap_is_fresh:
        download_name = f"sipp_ws{workspace_id}_capture.pcap"
        output_path = f"{RUN_DIR}/sipp_ws{workspace_id}_capture.pcap"
        # tcpdump already writes classic pcap; editcap (optional) only normalises it.
        if shutil.which("editcap"):
            conv = subprocess.run(["editcap", "-F", "pcap", rtp_pcap, output_path], capture_output=True)
            if conv.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return FileResponse(output_path, media_type="application/octet-stream", filename=download_name)
        return FileResponse(rtp_pcap, media_type="application/octet-stream", filename=download_name)
    elif os.path.exists(rtp_pcap) and ws and ws.get("run_start_time"):
        # The file exists but predates this run — tell the operator that
        # plainly instead of silently falling through to the SIP-only
        # fallback below, which would otherwise look like "it just used
        # a different, lesser format" rather than "the real capture failed".
        age_s = int(time.time() - os.path.getmtime(rtp_pcap))
        return {"error": f"No fresh RTP/SIP capture for this run — the existing file is {age_s}s older than "
                          f"when this test started. tcpdump may have failed to start; check this workspace's "
                          f"Live Log tab for a 'tcpdump failed to start' message."}

    # fallback — SIP only from workspace+script messages log
    sip_files = glob.glob(f"{RUN_DIR}/bscg_uac_{workspace_id}_{script_id}_*_messages.log")
    sip_files += glob.glob(f"{RUN_DIR}/bscg_uas_{workspace_id}_{script_id}_*_messages.log")
    if not sip_files:
        return {"error": f"No capture available for script {script_id} — run a test first"}
    latest_log = max(sip_files, key=os.path.getmtime)
    sip_pcap = f"{RUN_DIR}/sipp_ws{workspace_id}_s{script_id}_sip.pcap"
    ok = build_pcap(latest_log, sip_pcap)
    if not ok:
        return {"error": "Failed to build SIP PCAP"}
    filename = f"sipp_ws{workspace_id}_script{script_id}_{os.path.basename(latest_log).replace('_messages.log', '.pcap')}"
    return FileResponse(sip_pcap, media_type="application/octet-stream", filename=filename)

# ─── RTP Playback ─────────────────────────────────────────────────────────────
@router.get("/rtp/streams/{workspace_id}")
async def get_rtp_streams(request: Request, workspace_id: int):
    workspace_guard(request, workspace_id)
    from engines.rtp_extract import get_playback_streams
    streams = get_playback_streams(f"ws{workspace_id}")
    return {"streams": streams, "count": len(streams)}
