"""TX workspace run loop: intervals, monitoring and shutdown."""
import os
import subprocess
import asyncio
import time

from engines.sipp import parse_stats_csv
from workspaces.capture import _start_tcpdump, _stop_tcpdump
from workspaces.sipp_cmd import _start_script, script_share
from workspaces.state import _workspaces, log_workspace
from config import RUN_DIR

# ─── Interval runner ──────────────────────────────────────────────────────────
async def run_workspace(workspace_id: int, scripts: list, intervals: list, continuous: bool = False):
    ws = _workspaces.get(workspace_id)
    if not ws:
        return
    if ws["running"]:
        print(f"WS{workspace_id} already running — ignoring duplicate start")
        return {"error": "Already running"}
    ws["running"] = True
    ws["current_interval"] = 0
    ws["cumulative"] = {}
    ws["run_start_time"] = time.time()
    # reset all script stats for fresh run
    for sid in ws["scripts"]:
        ws["scripts"][sid]["stats"] = {"sent": 0, "completed": 0, "failed": 0}
        ws["scripts"][sid]["last_stats"] = {"sent": 0, "completed": 0, "failed": 0}
        ws["scripts"][sid]["base_stats"] = {"sent": 0, "completed": 0, "failed": 0}

    await _start_tcpdump(workspace_id, scripts)

    if not intervals:
        # no intervals — create a default one: run at CPS=1 for 60s
        log_workspace(workspace_id, "No intervals defined — running default 60s at 1 CPS", "info")
        default_interval = type('obj', (object,), {
            'interval_id': 1,
            'duration_s': 60,
            'label': 'Default',
            'script_cps': {str(s.script_id): 1 for s in scripts}
        })()
        intervals = [default_interval]

    async def _run_with_error_catch():
        try:
            await _run_intervals(workspace_id, scripts, intervals, continuous)
        except Exception as e:
            print(f"WS{workspace_id} interval error: {e}")
            import traceback
            traceback.print_exc()
            ws = _workspaces.get(workspace_id)
            if ws: ws["running"] = False

    asyncio.create_task(_run_with_error_catch())
    return {"status": "running intervals"}

def _collect_interval_stats(workspace_id: int, sid: int) -> int:
    """Add one finished interval's SIPp counters to the workspace totals, then retire the CSV.
    Returns how many calls SIPp actually started in that interval."""
    started = 0
    ws = _workspaces.get(workspace_id)
    csv_path = f"{RUN_DIR}/sipp_tx_stats_{workspace_id}_{sid}.csv"
    stats = parse_stats_csv(csv_path)
    if stats:
        started = stats["sent"]
    if ws and stats and stats["sent"] > 0 and sid in ws["scripts"]:
        cur = ws["scripts"][sid].get("stats", {})
        ws["scripts"][sid]["stats"] = {k: cur.get(k, 0) + stats[k]
                                       for k in ("sent", "completed", "failed", "retransmissions")}
    try:
        os.replace(csv_path, csv_path + ".prev")
    except OSError:
        pass
    return started


async def _run_intervals(workspace_id: int, scripts: list, intervals: list, continuous: bool = False):
    ws = _workspaces.get(workspace_id)
    if not ws:
        return

    script_map = {s.script_id: s for s in scripts}
    loop_count = 0
    # Where each script is in its number plan. It only moves forward, by the calls SIPp
    # really started, so pauses, later intervals and loops all continue the same sequence.
    number_offsets = {s.script_id: 0 for s in scripts}

    while ws["running"]:
        loop_count += 1
        if continuous:
            log_workspace(workspace_id,
                f"{'Loop ' + str(loop_count) if loop_count > 1 else 'Starting'} — {len(intervals)} intervals", "info")

        for i, interval in enumerate(intervals):
            if not ws["running"]:
                break

            ws["current_interval"] = i + 1
            duration_s = interval.duration_s or 30
            log_workspace(workspace_id,
                f"{'Loop '+str(loop_count)+' ' if continuous else ''}Interval {i+1}/{len(intervals)}: {interval.label or ''} {duration_s}s", "info")

            await _stop_all_scripts(workspace_id)
            await asyncio.sleep(0.5)

            active_scripts = []
            for script_id_str, cps in interval.script_cps.items():
                sid = int(script_id_str)
                if cps <= 0:
                    log_workspace(workspace_id, f"Script {sid}: paused", "info")
                    continue
                if sid in script_map:
                    script = script_map[sid]
                    if script_share(script) <= 0:
                        log_workspace(workspace_id, f"Script {sid}: 0% share, not started", "info")
                        continue
                    pid = await _start_script(workspace_id, script,
                                             cps=cps, duration_s=duration_s,
                                             start_offset=number_offsets[sid])
                    if pid > 0:
                        active_scripts.append(script)

            # wait for interval duration, then let SIPp finish its -m burst
            # (grace period capped to avoid hanging if SUT never responds)
            elapsed = 0
            # SIPp's default INVITE retransmission timeout is ~15.5s
            # (5 retries, T1=500ms doubling: .5+1+2+4+8). Grace cap must
            # comfortably exceed that, even for very short intervals.
            grace_cap = max(duration_s * 2 + 10, 30)
            while elapsed < duration_s and ws["running"]:
                await asyncio.sleep(1)
                elapsed += 1

            # interval clock expired — wait for scripts to truly finish.
            # Primary signal: process has exited AND CSV sent-count matches target.
            # grace_cap is a safety-net ceiling only, not the primary completion signal.
            while ws["running"] and elapsed < grace_cap:
                still_running = False
                for script in active_scripts:
                    sid = script.script_id
                    state = ws["scripts"].get(sid, {})
                    proc = state.get("process")
                    if proc and proc.poll() is None:
                        still_running = True
                if not still_running:
                    break
                await asyncio.sleep(0.5)
                elapsed += 0.5

            # extra confirmation: even after process exit, poll the CSV
            # briefly until sent-count stops changing (file fully flushed)
            for script in active_scripts:
                sid = script.script_id
                stats_path = f"{RUN_DIR}/sipp_tx_stats_{workspace_id}_{sid}.csv"
                last_sent = -1
                stable_count = 0
                for settle_i in range(20):
                    candidate = parse_stats_csv(stats_path)
                    cur_sent = candidate.get("sent", 0) if candidate else 0
                    if cur_sent == last_sent and cur_sent > 0:
                        stable_count += 1
                        if stable_count >= 2:
                            break
                    else:
                        stable_count = 0
                    last_sent = cur_sent
                    await asyncio.sleep(0.3)

            # this interval is finished: add its numbers to the run totals, once,
            # then clear the file so the next interval starts from zero
            await asyncio.sleep(1.0)
            for script in active_scripts:
                number_offsets[script.script_id] += _collect_interval_stats(workspace_id, script.script_id)

        # check if we should loop
        if not continuous or not ws["running"]:
            break

        log_workspace(workspace_id, f"Loop {loop_count} complete — restarting", "ok")

    # done
    await _stop_all_scripts(workspace_id)
    await asyncio.sleep(0.5)
    ws["running"] = False
    ws["current_interval"] = 0
    _stop_tcpdump(workspace_id)
    if continuous:
        log_workspace(workspace_id, f"Continuous test stopped after {loop_count} loop(s)", "ok")
    else:
        log_workspace(workspace_id, "All intervals complete", "ok")

async def _monitor_workspace(workspace_id: int, scripts: list):
    """Monitor workspace scripts (no intervals)."""
    ws = _workspaces.get(workspace_id)
    if not ws:
        return

    # start RTCP if needed
    rtcp_captures = {}
    for script in scripts:
        if script.enable_rtp:
            from engines.rtcp import RTCPCapture
            rtcp_port = 6002
            cap = RTCPCapture(script.orig_ip, rtcp_port, (script.duration_ms or 60000) / 1000 + 5)
            cap.start()
            rtcp_captures[script.script_id] = cap

    while ws["running"]:
        all_done = True
        for script in scripts:
            sid = script.script_id
            if sid not in ws["scripts"]:
                continue
            state = ws["scripts"][sid]
            proc = state["process"]
            if proc and proc.poll() is None:
                all_done = False
                stats = parse_stats_csv(f"{RUN_DIR}/sipp_tx_stats_{workspace_id}_{sid}.csv")
                if stats and stats["sent"] > 0:
                    state["stats"] = stats
            else:
                if state["running"]:
                    stats = parse_stats_csv(f"{RUN_DIR}/sipp_tx_stats_{workspace_id}_{sid}.csv")
                    if stats and stats["sent"] > 0:
                        state["stats"] = stats
                    state["running"] = False

        if all_done:
            break
        await asyncio.sleep(1)

    # stop RTCP
    for sid, cap in rtcp_captures.items():
        cap.stop()
        rtcp_stats = cap.get_stats()
        if sid in ws["scripts"]:
            ws["scripts"][sid]["rtcp"] = rtcp_stats
            if rtcp_stats.get("mos"):
                ws["scripts"][sid]["mos"] = {
                    "mos": rtcp_stats["mos"],
                    "label": rtcp_stats.get("mos_label", ""),
                    "method": "RTCP R-Factor",
                    "jitter_ms": rtcp_stats.get("jitter_ms", 0),
                    "packet_loss_pct": rtcp_stats.get("packet_loss_pct", 0),
                    "rtt_ms": rtcp_stats.get("rtt_ms", 0)
                }

    _stop_tcpdump(workspace_id)
    ws["running"] = False
    log_workspace(workspace_id, "Workspace complete", "ok")

async def _stop_all_scripts(workspace_id: int):
    """Stop all running scripts in a workspace."""
    ws = _workspaces.get(workspace_id)
    if not ws:
        return

    # terminate processes
    for sid, state in ws["scripts"].items():
        if state.get("process"):
            try:
                state["process"].terminate()
            except:
                pass
            state["process"] = None
            state["running"] = False

    subprocess.run(["pkill", "-f", rf"bscg_uac_{workspace_id}_"], capture_output=True)

async def stop_workspace(workspace_id: int):
    """Stop a workspace completely."""
    ws = _workspaces.get(workspace_id)
    if not ws:
        return
    ws["running"] = False
    await _stop_all_scripts(workspace_id)
    _stop_tcpdump(workspace_id)
    log_workspace(workspace_id, "Workspace stopped", "err")
