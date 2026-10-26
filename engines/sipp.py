import os
import glob
import re
from config import RUN_DIR



def parse_stats_csv(csv_path: str, mode: str = "uac") -> dict:
    """
    Read SIPp's own counters from its -stf file (columns are looked up by name).

      sent            calls started (OutgoingCall for a caller, IncomingCall for a receiver)
      completed       calls that finished successfully
      failed          calls SIPp itself counted as failed (includes max-retransmission timeouts)
      active          calls still in progress right now (CurrentCall)
      retransmissions SIP messages sent again because the far end did not answer

    Nothing is inferred: a call that has not finished yet is "active", not "failed".
    """
    try:
        if not os.path.exists(csv_path):
            return None
        with open(csv_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        if len(lines) < 2:
            return None
        header, last = lines[0].split(";"), lines[-1].split(";")
        col = {name.strip(): i for i, name in enumerate(header)}

        def num(name: str) -> int:
            i = col.get(name)
            try:
                return int(float(last[i])) if i is not None and i < len(last) and last[i] else 0
            except ValueError:
                return 0

        return {
            "sent":            num("IncomingCall(C)" if mode == "uas" else "OutgoingCall(C)"),
            "completed":       num("SuccessfulCall(C)"),
            "failed":          num("FailedCall(C)"),
            "active":          num("CurrentCall"),
            "retransmissions": num("Retransmissions(C)"),
        }
    except Exception:
        return None

def get_latest_messages_log(prefix="uac", workspace_id=None, script_id=None) -> str:
    """
    Get the most recent SIPp messages log file for a specific
    workspace (and, for TX, a specific script).

    Was: globbed for "scenario_{prefix}_*_messages.log" under this
    project's log directory — a filename pattern this project's own
    SIPp commands have never actually produced. Confirmed directly
    against real files on disk: the actual names are
    "bscg_uac_{workspace_id}_{script_id}_<pid>_messages.log" (TX) and
    "bscg_uas_{workspace_id}_<pid>_messages.log" (RX), because SIPp
    derives its trace filenames from the "-sf" scenario file's basename
    ("run/bscg_uac_{workspace_id}_{script_id}.xml" etc.), not from
    anything containing the word "scenario". This meant every call to
    this function always returned None — silently — and every caller
    that did `get_remote_rtp_port(log) or <fallback>` always hit the
    fallback, unconditionally, regardless of early media or anything
    else. Also fixed: the old version had no workspace/script scoping
    at all and picked whichever matching file was modified most
    recently ACROSS THE WHOLE SERVER — a real hazard for concurrent
    multi-workspace testing, since a busier unrelated workspace's log
    could "win" and get returned instead of the correct one.
    """
    base = RUN_DIR
    if workspace_id is not None:
        if script_id is not None:
            pattern = f"{base}/bscg_{prefix}_{workspace_id}_{script_id}_*_messages.log"
        else:
            pattern = f"{base}/bscg_{prefix}_{workspace_id}_*_messages.log"
    else:
        # unscoped fallback for any caller that genuinely can't provide an id
        pattern = f"{base}/bscg_{prefix}_*_messages.log"
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def parse_messages_log(log_file: str) -> dict:
    """Parse SIPp messages log into call groups."""
    if not log_file or not os.path.exists(log_file):
        return {}
    calls = {}
    with open(log_file) as f:
        content = f.read()
    blocks = content.split("-----------------------------------------------")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        direction = None
        method = None
        timestamp = None
        call_id = None
        if "UDP message sent" in block:
            direction = "sent"
        elif "UDP message received" in block:
            direction = "received"
        else:
            continue
        # SIPp prints "YYYY-MM-DD HH:MM:SS.ffffff" (older builds use a "T").
        ts_match = re.search(r'\d{4}-\d{2}-\d{2}[T ](\d{2}:\d{2}:\d{2}\.\d+)', block)
        if ts_match:
            timestamp = ts_match.group(1)[:12]
        cid_match = re.search(r'Call-ID:\s*(.+)', block, re.IGNORECASE)
        if cid_match:
            call_id = cid_match.group(1).strip()
        lines = block.split("\n")
        raw_lines = []
        capture = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("INVITE","ACK","BYE","CANCEL","REGISTER","OPTIONS","SIP/2.0")):
                capture = True
            if capture:
                raw_lines.append(line)
            if not method and capture:
                if stripped.startswith("SIP/2.0"):
                    parts = stripped.split(" ", 2)
                    if len(parts) >= 3:
                        method = parts[1] + " " + parts[2]
                elif stripped:
                    method = stripped.split()[0]
        raw = "\n".join(raw_lines).strip()
        raw = raw.replace('`', "'").replace('\\', '/')
        if method and direction and call_id:
            if call_id not in calls:
                calls[call_id] = []
            calls[call_id].append({
                "direction": direction,
                "method": method,
                "timestamp": timestamp or "",
                "raw": raw
            })
    # deduplicate — remove consecutive same method+direction within 100ms
    for call_id in calls:
        msgs = calls[call_id]
        deduped = [msgs[0]] if msgs else []
        for msg in msgs[1:]:
            prev = deduped[-1]
            if (msg['method'] == prev['method'] and
                msg['direction'] == prev['direction']):
                # only skip if within 50ms — true duplicate
                if msg['timestamp'] and prev['timestamp']:
                    try:
                        def ts_ms(ts):
                            p = ts.split(':')
                            s, ms = p[2].split('.')
                            return (int(p[0])*3600 + int(p[1])*60 + int(s))*1000 + int(ms[:3])
                        diff = abs(ts_ms(msg['timestamp']) - ts_ms(prev['timestamp']))
                        if diff < 50:
                            pass  # true duplicate within 50ms
                        else:
                            deduped.append(msg)  # keep — meaningful retransmission
                    except:
                        deduped.append(msg)
                else:
                    pass  # no timestamp — skip
            else:
                deduped.append(msg)

        calls[call_id] = deduped
    return calls

def get_remote_rtp_port(messages_log: str) -> int:
    """
    Extract remote RTP port from the FIRST SDP-bearing response the UAC
    received — this may be a 183 Session Progress (early media) or the
    200 OK (normal answer), whichever the far end actually sends first
    with a real media offer.

    Was: only matched a literal "200" substring in the block, so a
    183-negotiated early-media SDP was invisible to this function
    entirely. Combined with _start_rtp_sender()'s old fixed 3-second
    firing delay, this meant: for any call that held in early media
    longer than 3s (the whole point of early media), this always
    returned None at the moment it was checked, and the caller silently
    fell back to using its OWN local port as the "remote" port —
    guaranteed wrong-port audio, confirmed via direct testing.
    """
    import re
    if not messages_log or not os.path.exists(messages_log):
        return None
    with open(messages_log) as f:
        content = f.read()
    blocks = content.split("-----------------------------------------------")
    for block in blocks:
        if "UDP message received" not in block or "m=audio" not in block:
            continue
        # any 1xx or 2xx carrying SDP is a valid media negotiation point —
        # 4xx/5xx/6xx never legitimately carry a media offer/answer
        if not re.search(r'SIP/2\.0\s+(1\d\d|2\d\d)\b', block):
            continue
        match = re.search(r'm=audio\s+(\d+)', block)
        if match:
            return int(match.group(1))
    return None

def get_caller_offered_rtp_target(messages_log: str):
    """
    RX/UAS counterpart to get_remote_rtp_port(): extracts the IP:port the
    CALLER offered in the INVITE's SDP (the message a UAS *receives*, not
    sends) — this is where the UAS's own outbound RTP needs to go. Used
    by the RX-side RTP sender (see workspaces/manager.py
    _start_rtp_sender_rx) so RX can actually send audio back to the
    caller instead of never sending any at all.
    Returns (ip, port) tuple, or None if no INVITE with SDP seen yet.
    """
    import re
    if not messages_log or not os.path.exists(messages_log):
        return None
    with open(messages_log) as f:
        content = f.read()
    blocks = content.split("-----------------------------------------------")
    for block in blocks:
        if "UDP message received" not in block or "INVITE" not in block or "m=audio" not in block:
            continue
        port_match = re.search(r'm=audio\s+(\d+)', block)
        ip_match = re.search(r'c=IN IP4\s+([\d.]+)', block)
        if port_match and ip_match:
            return (ip_match.group(1), int(port_match.group(1)))
    return None
