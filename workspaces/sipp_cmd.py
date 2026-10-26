"""Builds and starts SIPp processes for a script."""
import asyncio
import subprocess
import os
from models import ScriptConfig

from workspaces.rtp_sender import _start_rtp_sender
from workspaces.state import _init_script_state, _workspaces, log_workspace
from config import RUN_DIR
from procutil import tied_to_parent
from engines.scenario_guard import prepare_scenario_xml

def script_share(script: ScriptConfig) -> float:
    """This script's share of the interval CPS, 0.0-1.0. A share of 0 means 'do not run'."""
    pct = getattr(script, "pct", 100)
    return max(0.0, min(100.0, 100.0 if pct is None else float(pct))) / 100.0


def script_rate(script: ScriptConfig, cps: float) -> float:
    """Exact calls per second for this script (SIPp's -r accepts fractions, so no rounding up)."""
    return cps * script_share(script)


def script_bind(script: ScriptConfig, workspace_id: int):
    """The (ip, port) this script's SIPp process will bind to."""
    port = int(script.sip_port) if script.sip_port else 5080 + workspace_id * 10 + script.script_id
    return script.orig_ip, port


def _build_sipp_cmd(script: ScriptConfig, workspace_id: int,
                    cps: float = 1, duration_s: int = 30, start_offset: int = 0) -> list:
    """Build SIPp UAC command for a script."""
    xml_path   = f"{RUN_DIR}/bscg_uac_{workspace_id}_{script.script_id}.xml"
    stats_path = f"{RUN_DIR}/sipp_tx_stats_{workspace_id}_{script.script_id}.csv"

    # % allocation — must be defined before CSV generation. Use the exact
    # rate: rounding each script up to a whole CPS can multiply the offered load.
    rate = script_rate(script, cps)
    total_calls = max(1, int(rate * duration_s + 0.5))  # half-up (round() rounds 2.5 to 2)

    csv_name = f"{workspace_id}_{script.script_id}"   # one injection file per script, never shared

    # support multi-row number pairs
    from engines.numbers import generate_csv_multi, generate_csv
    if hasattr(script, 'number_pairs') and script.number_pairs:
        target = total_calls
        if getattr(script, 'auth_enabled', False):
            single_mode = getattr(script, 'auth_mode', 'single') != 'per_row'
            default_user = script.auth_username if single_mode else ''
            default_pass = script.auth_password if single_mode else ''
            csv_path, total_calls = generate_csv_multi(
                script.number_pairs, max_calls=target,
                include_auth=True,
                default_username=default_user, default_password=default_pass,
                stir_enabled=getattr(script, 'stir_enabled', False),
                default_attest=getattr(script, 'stir_attest', 'A'),
                csv_name=csv_name, start_offset=start_offset)
        else:
            csv_path, total_calls = generate_csv_multi(
                script.number_pairs, max_calls=target,
                stir_enabled=getattr(script, 'stir_enabled', False),
                default_attest=getattr(script, 'stir_attest', 'A'),
                csv_name=csv_name, start_offset=start_offset)
        effective_max = str(total_calls)
    else:
        csv_path = generate_csv(script.calling_num, script.called_num,
                                total_calls,
                                stir_enabled=getattr(script, 'stir_enabled', False),
                                default_attest=getattr(script, 'stir_attest', 'A'),
                csv_name=csv_name, start_offset=start_offset)
        effective_max = str(total_calls)

    # write scenario XML
    clean_xml = prepare_scenario_xml(script.xml)  # validates the exact text that gets written


    with open(xml_path, "w") as f:
        f.write(clean_xml)

    effective_cps = f"{rate:.3f}".rstrip("0").rstrip(".") or "0"
    sip_port = script_bind(script, workspace_id)[1]

    return [
        "sipp", f"{script.sut_ip}:{script.sut_port}",
        "-sf", xml_path,
        "-i", script.orig_ip,
        "-p", str(sip_port),
        "-r", effective_cps,
        "-l", str(effective_max),
        "-m", str(effective_max),
        "-max_retrans", "4",
        "-trace_msg",
        "-trace_err",
        "-trace_stat",
        "-stf", stats_path,
        "-fd", "1",          # SIPp writes its counters every 60 s by default; we want them each second
        "-inf", csv_path,
    ], csv_path

async def _start_script(workspace_id: int, script: ScriptConfig, cps: float = 1, duration_s: int = 30,
                        start_offset: int = 0) -> int:
    """Start a single SIPp script process."""
    _init_script_state(workspace_id, script.script_id)
    ws = _workspaces[workspace_id]

    cmd, csv_path = _build_sipp_cmd(script, workspace_id, cps, duration_s, start_offset)

    log_workspace(workspace_id, f"Script {script.script_id} starting: {cps} CPS, {duration_s}s", "info")

    process = subprocess.Popen(
        tied_to_parent(cmd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=RUN_DIR
    )

    ws["scripts"][script.script_id]["process"] = process
    ws["scripts"][script.script_id]["running"] = True

    # check immediate death
    await asyncio.sleep(0.2)
    if process.poll() is not None:
        log_workspace(workspace_id, f"Script {script.script_id} failed to start (rc={process.returncode})", "err")
        return -1

    # start RTP sender if enabled
    if script.enable_rtp:
        _start_rtp_sender(workspace_id, script)

    opt = lambda flag: cmd[cmd.index(flag) + 1] if flag in cmd else "?"
    try:
        with open(csv_path) as f:
            rows = sum(1 for _ in f) - 1   # first line is the SEQUENTIAL header
    except OSError:
        rows = "?"
    log_workspace(workspace_id,
        f"Script {script.script_id} started — PID {process.pid}, -r {opt('-r')} -m {opt('-m')}, "
        f"{rows} numbers in {os.path.basename(csv_path)}", "ok")
    return process.pid
