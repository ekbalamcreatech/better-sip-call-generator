"""RX workspace: starts a SIPp UAS and monitors it."""
import os
import asyncio
import subprocess
import time
from models import ScriptConfig

from engines.sipp import parse_stats_csv
from workspaces.capture import _start_tcpdump_rx
from workspaces.rtp_sender import _start_rtp_sender_rx
from workspaces.state import _workspaces, init_workspace, log_workspace
from procutil import tied_to_parent
from engines.scenario_guard import prepare_scenario_xml
from config import RUN_DIR

# ─── RX Workspace ─────────────────────────────────────────────────────────────
async def run_rx_workspace(workspace_id: int, term_ip: str, listen_port: int,
                           enable_mos: bool = False, xml: str = None,
                           script: ScriptConfig = None):
    """
    Start a SIPp UAS listener for an RX workspace.

    `script` (new) carries the RX Audio-tab settings (audio_file, codec,
    rtp impairment fields, enable_rtp) — previously only `enable_mos`
    (a bare bool) was passed through, which was enough to display MOS
    scoring UI state but not enough to actually start sending any RTP,
    which is why RX has never sent audio at all. See
    _start_rtp_sender_rx() for the actual sender this now wires up.
    """
    ws = _workspaces.get(workspace_id)
    if not ws:
        init_workspace(workspace_id, role="rx")
        ws = _workspaces[workspace_id]

    if ws["running"]:
        return {"error": "Already running"}

    # Stop a stale listener for THIS workspace only (matched by its own scenario file).
    subprocess.run(["pkill", "-f", rf"sipp.*bscg_uas_{workspace_id}\.xml"], capture_output=True)
    await asyncio.sleep(1.0)

    await _start_tcpdump_rx(workspace_id, term_ip)

    # write scenario XML
    xml_path = f"{RUN_DIR}/bscg_uas_{workspace_id}.xml"
    stats_path = f"{RUN_DIR}/sipp_rx_stats_{workspace_id}.csv"

    if xml:
        clean_xml = prepare_scenario_xml(xml)  # validates the exact text that gets written
        with open(xml_path, "w") as f:
            f.write(clean_xml)
        cmd = [
            "sipp",
            "-sf", xml_path,
            "-i", term_ip,
            "-p", str(listen_port),
            "-trace_msg",
            "-trace_err",
            "-trace_stat",
            "-stf", stats_path, "-fd", "1",
        ]
    else:
        cmd = [
            "sipp",
            "-sn", "uas",
            "-i", term_ip,
            "-p", str(listen_port),
            "-trace_msg",
            "-trace_err",
            "-trace_stat",
            "-stf", stats_path, "-fd", "1",
        ]

    print(f"RX WS{workspace_id} CMD: {' '.join(cmd)}")
    # clear stale RX stats CSV
    try:
        os.remove(stats_path)
    except:
        pass
    process = subprocess.Popen(
        tied_to_parent(cmd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=RUN_DIR
    )

    # init script slot for RX
    ws["scripts"][1] = {
        "process": process,
        "running": True,
        "stats": {"sent": 0, "completed": 0, "failed": 0},
        "mos": None,
        "rtcp": None
    }
    ws["running"] = True
    ws["run_start_time"] = time.time()
    # reset stats for fresh run
    ws["scripts"][1] = {
        "process": process,
        "running": True,
        "stats": {"sent": 0, "completed": 0, "failed": 0},
        "mos": None,
        "rtcp": None
    }

    # give SIPp time to start
    await asyncio.sleep(1.0)
    if process.poll() is not None:
        # check error logs
        import glob as _glob
        err_files = _glob.glob(f"{RUN_DIR}/bscg_uas_{workspace_id}_*errors*")
        err_msg = ""
        if err_files:
            try:
                with open(max(err_files, key=os.path.getmtime)) as f:
                    err_msg = f.read()[-300:]
            except:
                pass
        print(f"RX WS{workspace_id} failed rc={process.returncode} err={err_msg}")
        log_workspace(workspace_id, f"RX listener failed (rc={process.returncode})", "err")
        ws["running"] = False
        return {"error": f"SIPp UAS failed to start — {err_msg or 'check logs'}"}

    log_workspace(workspace_id, f"RX listening on {term_ip}:{listen_port} PID={process.pid}", "ok")

    # RX has never started an RTP sender of its own before now — see
    # _start_rtp_sender_rx() for the honest scope/limitations of this.
    if script is not None and getattr(script, 'enable_rtp', False):
        _start_rtp_sender_rx(workspace_id, script, term_ip)

    asyncio.create_task(_monitor_rx_workspace(workspace_id, stats_path, enable_mos))
    return {"status": "listening", "pid": process.pid}

async def _monitor_rx_workspace(workspace_id: int, stats_path: str, enable_mos: bool):
    """Monitor RX workspace."""
    ws = _workspaces.get(workspace_id)
    if not ws:
        return

    while ws["running"]:
        state = ws["scripts"].get(1, {})
        proc = state.get("process")
        if proc and proc.poll() is not None:
            break

        stats = parse_stats_csv(stats_path, mode="uas")
        if stats:
            ws["scripts"][1]["stats"] = {
                "sent": stats["sent"],
                "completed": stats["completed"],
                "failed": stats["failed"]
            }
        await asyncio.sleep(1)

    # final stats
    stats = parse_stats_csv(stats_path, mode="uas")
    if stats and 1 in ws["scripts"]:
        ws["scripts"][1]["stats"] = {
            "sent": stats["sent"],
            "completed": stats["completed"],
            "failed": stats["failed"]
        }

    ws["running"] = False
    log_workspace(workspace_id, "RX listener stopped", "info")
