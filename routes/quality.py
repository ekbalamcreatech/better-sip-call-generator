from fastapi import Request
import re
import os
import glob

from workspaces.manager import (
    get_workspace
)

from fastapi import APIRouter
from security import workspace_guard
from config import RUN_DIR
router = APIRouter()


# ─── Quality per call ─────────────────────────────────────────────────────────
@router.get("/quality/{workspace_id}")
async def get_call_quality(request: Request, workspace_id: int, script_id: int = 1):
    workspace_guard(request, workspace_id)
    from engines.sipp import parse_messages_log
    from engines.sip_extract import extract_sip_messages, correlate_streams_to_calls_generic
    from engines.rtp_extract import extract_rtp_streams, compute_per_stream_quality
    ws = get_workspace(workspace_id)
    files = glob.glob(f"{RUN_DIR}/bscg_uac_{workspace_id}_{script_id}_*_messages.log")
    files += glob.glob(f"{RUN_DIR}/bscg_uas_{workspace_id}_*_messages.log")
    if ws and ws.get("run_start_time"):
        run_start = ws["run_start_time"]
        recent = sorted([f for f in files if os.path.getmtime(f) >= run_start - 5],
                        key=os.path.getmtime)
    else:
        # workspace not in memory (e.g. after a service restart) —
        # fall back to just the single most recent log rather than showing all history
        recent = sorted(files, key=os.path.getmtime)[-1:]
    if not recent:
        return {"calls": [], "total": 0}
    # merge all calls from all recent logs
    all_calls_raw = {}
    for log_file in recent:
        calls = parse_messages_log(log_file)
        all_calls_raw.update(calls)

    # per-call RTP correlation, using the same tcpdump capture used for PCAP export
    per_call_rtp = {}
    pcap_path = f"{RUN_DIR}/rtp_ws{workspace_id}_capture.pcap"
    ws_ip = ws.get("ip") if ws else None
    if os.path.exists(pcap_path) and os.path.getsize(pcap_path) > 100:
        try:
            sip_msgs = extract_sip_messages(pcap_path)
            streams = extract_rtp_streams(pcap_path)
            correlation = correlate_streams_to_calls_generic(streams, sip_msgs)
            for cid, matched_streams in correlation.items():
                qualities = [compute_per_stream_quality(s) for s in matched_streams]
                mos_vals = [q["mos"] for q in qualities if q.get("mos") is not None]
                loss_vals = [q["packet_loss_pct"] for q in qualities if q.get("packet_loss_pct") is not None]
                stream_details = []
                for s, q in zip(matched_streams, qualities):
                    stream_details.append({
                        "ssrc": s.get("ssrc"),
                        "direction": "out" if s.get("src_ip") == ws_ip else "in",
                        "src": f"{s.get('src_ip')}:{s.get('src_port')}",
                        "dst": f"{s.get('dst_ip')}:{s.get('dst_port')}",
                        "codec": s.get("codec"),
                        "quality": q,
                    })
                per_call_rtp[cid] = {
                    "mos": round(min(mos_vals), 2) if mos_vals else None,  # worst direction drives perceived quality
                    "packet_loss_pct": round(max(loss_vals), 2) if loss_vals else None,
                    "stream_count": len(matched_streams),
                    "streams": stream_details,
                }

        except Exception as e:
            print(f"Per-call RTP correlation error: {e}")

    calls = []
    for call_id, messages in all_calls_raw.items():
        timestamps = [m["timestamp"] for m in messages if m["timestamp"]]
        if not timestamps:
            continue
        invite_ts = bye_ts = error_code = None
        got_error_response = False
        for msg in messages:
            m  = msg["method"]
            ts = msg["timestamp"]
            if m == "INVITE" and msg["direction"] == "sent":
                invite_ts = ts
            if m == "BYE":
                bye_ts = ts
            if msg["direction"] == "received":
                if m and (m.startswith("4") or m.startswith("5") or m.startswith("6")):
                    error_code = m
                    got_error_response = True
        # A call that never completed cleanly (timeout, rejection, no answer) is a failure.
        if bye_ts and invite_ts:
            status = "completed"
        elif got_error_response:
            status = "failed"
        elif invite_ts:
            status = "failed"
        else:
            status = "unknown"  # no INVITE seen at all for this call_id — shouldn't normally happen
        duration_s = 0
        if invite_ts and bye_ts:
            try:
                def ts_to_ms(ts):
                    p = ts.split(':')
                    s, ms = p[2].split('.')
                    return (int(p[0])*3600 + int(p[1])*60 + int(s))*1000 + int(ms[:3])
                duration_s = round((ts_to_ms(bye_ts) - ts_to_ms(invite_ts)) / 1000, 2)
            except:
                pass
        rtp_info = per_call_rtp.get(call_id, {})
        calls.append({
            "call_id": call_id,
            "status": status,
            "error_code": error_code,
            "duration_s": duration_s,
            "invite_ts": invite_ts,
            "bye_ts": bye_ts,
            "message_count": len(messages),
            "mos": rtp_info.get("mos"),
            "packet_loss_pct": rtp_info.get("packet_loss_pct"),
            "streams": rtp_info.get("streams", [])
        })
    return {"calls": calls, "total": len(calls)}

# ─── SIP STATS ────────────────────────────────────────────────────────────────
@router.get("/sipstats/{workspace_id}")
async def get_sip_stats(request: Request, workspace_id: int, script_id: int = 1):
    workspace_guard(request, workspace_id)

    ws = get_workspace(workspace_id)

    files = glob.glob(f"{RUN_DIR}/bscg_uac_{workspace_id}_{script_id}_*_messages.log")
    files += glob.glob(f"{RUN_DIR}/bscg_uas_{workspace_id}_*_messages.log")

    if ws and ws.get("run_start_time"):
        run_start = ws["run_start_time"]
        recent = sorted([f for f in files if os.path.getmtime(f) >= run_start - 5],
                        key=os.path.getmtime)
    else:
        # workspace not in memory (e.g. after a service restart) —
        # fall back to just the single most recent log
        recent = sorted(files, key=os.path.getmtime)[-1:]

    if not recent:
        return {"sent": {}, "received": {}, "total_calls": 0}

    sent, received, retrans = {}, {}, {}
    invite_calls = set()
    seen = set()   # (direction, call-id, cseq, first line): a repeat is a retransmission, not a new message
    requests = ("INVITE", "BYE", "ACK", "CANCEL", "OPTIONS", "REGISTER", "REFER", "NOTIFY",
                "SUBSCRIBE", "INFO", "PRACK", "UPDATE", "MESSAGE")

    for log_file in recent:
        try:
            with open(log_file) as f:
                content = f.read()
        except OSError as e:
            print(f"SIP stats error {log_file}: {e}")
            continue
        for block in content.split("-----------------------------------------------"):
            if "UDP message sent" in block:
                direction, table = "sent", sent
            elif "UDP message received" in block:
                direction, table = "received", received
            else:
                continue
            first = next((l.strip() for l in block.strip().split("\n")
                          if l.strip().startswith(requests) or l.strip().startswith("SIP/2.0 ")), "")
            if not first:
                continue
            parts = first.split()
            key = parts[0] if first.startswith(requests) else (parts[1] if direction == "sent" else " ".join(parts[1:3]))
            cid = re.search(r"Call-ID:\s*(\S+)", block, re.IGNORECASE)
            cseq = re.search(r"CSeq:\s*(.+)", block, re.IGNORECASE)
            ident = (direction, cid.group(1) if cid else "", cseq.group(1).strip() if cseq else "", first)
            if cid and ident in seen:
                retrans[key] = retrans.get(key, 0) + 1
                continue
            seen.add(ident)
            table[key] = table.get(key, 0) + 1
            if direction == "sent" and key == "INVITE" and cid:
                invite_calls.add(cid.group(1))
    total_calls = len(invite_calls)

    summary = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "6xx": 0}
    # for RX workspace, count codes from sent (our responses) + received
    ws = get_workspace(workspace_id)
    role = ws.get("role", "tx") if ws else "tx"
    codes_to_count = dict(received)
    if role == "rx":
        codes_to_count.update(sent)  # add our sent responses to summary
    for code, count in codes_to_count.items():
        try:
            c = int(str(code).split()[0])
            if 200 <= c < 300: summary["2xx"] += count
            elif 300 <= c < 400: summary["3xx"] += count
            elif 400 <= c < 500: summary["4xx"] += count
            elif 500 <= c < 600: summary["5xx"] += count
            elif 600 <= c < 700: summary["6xx"] += count
        except:
            pass

    return {
        "sent": dict(sorted(sent.items())),
        "received": dict(sorted(received.items())),
        "summary": summary,
        "total_calls": total_calls,
        "retransmissions": dict(sorted(retrans.items())),
        "log_files": len(recent)
    }
