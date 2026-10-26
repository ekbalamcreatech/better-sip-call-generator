import re
import os
import subprocess
import tempfile
from engines.pcapread import read_packets

# ITU-T Q.850 cause codes — standard, publicly-published telecom reference
# values, used to give a human-readable fallback when a carrier's Reason
# header carries only "cause=N" with no text="..." param (common in the
# wild — many SBCs/carriers omit the optional text). Not exhaustive, just
# the values that actually show up in real PSTN-interworking traces.
Q850_CAUSES = {
    1: "Unallocated (unassigned) number", 2: "No route to specified transit network",
    3: "No route to destination", 6: "Channel unacceptable",
    16: "Normal call clearing", 17: "User busy", 18: "No user responding",
    19: "No answer from user (user alerted)", 20: "Subscriber absent",
    21: "Call rejected", 22: "Number changed", 26: "Non-selected user clearing",
    27: "Destination out of order", 28: "Invalid number format (incomplete)",
    29: "Facility rejected", 31: "Normal, unspecified",
    34: "No circuit/channel available", 38: "Network out of order",
    41: "Temporary failure", 42: "Switching equipment congestion",
    43: "Access information discarded", 44: "Requested circuit/channel not available",
    47: "Resource unavailable, unspecified", 50: "Requested facility not subscribed",
    55: "Incoming calls barred within CUG", 57: "Bearer capability not authorized",
    58: "Bearer capability not presently available",
    63: "Service/option not available, unspecified",
    65: "Bearer capability not implemented", 69: "Requested facility not implemented",
    79: "Service/option not implemented, unspecified",
    81: "Invalid call reference value", 88: "Incompatible destination",
    95: "Invalid message, unspecified", 96: "Mandatory information element missing",
    97: "Message type non-existent or not implemented",
    98: "Message not compatible with call state",
    99: "Information element non-existent or not implemented",
    100: "Invalid information element contents",
    102: "Recovery on timer expiry", 111: "Protocol error, unspecified",
    127: "Interworking, unspecified",
}


def _parse_reason_headers(raw_text: str) -> list:
    """
    Parse RFC 3326 Reason header(s) from a raw SIP message. A message can
    carry more than one (e.g. one Q.850 and one SIP protocol reason on
    the same BYE/CANCEL), so this always returns a list.

    Was: not handled anywhere in this pipeline at all — every finding
    and every AI diagnosis only ever saw the bare SIP status code (e.g.
    "486 Busy Here" or a plain BYE/CANCEL), even when the message
    carried an explicit "Reason: Q.850;cause=17;text=\"User busy\""
    header giving the actual PSTN-side disconnect cause. For interworked
    (SIP<->PSTN/ISUP) traces this is often the more authoritative
    signal — the SIP code alone can be a generic mapping that loses
    detail the carrier's own Reason header preserved.

    Returns: [{"protocol": "Q.850"|"SIP"|other, "cause": int|None,
               "text": str|None}, ...]
    """
    results = []
    for line in raw_text.split('\r\n'):
        if not line.lower().startswith('reason:'):
            continue
        value = line.split(':', 1)[1].strip()
        # Reason: <protocol> ;cause=<N> ;text="<text>"
        proto_match = re.match(r'^([^;]+)', value)
        protocol = proto_match.group(1).strip() if proto_match else None
        cause_match = re.search(r'cause\s*=\s*(\d+)', value, re.IGNORECASE)
        cause = int(cause_match.group(1)) if cause_match else None
        text_match = re.search(r'text\s*=\s*"([^"]*)"', value, re.IGNORECASE)
        text = text_match.group(1) if text_match else None
        if not text and protocol and protocol.upper() == 'Q.850' and cause in Q850_CAUSES:
            text = Q850_CAUSES[cause]  # fill in the standard meaning when the carrier omitted text=
        if protocol or cause is not None:
            results.append({"protocol": protocol, "cause": cause, "text": text})
    return results


def _normalize_pcap(pcap_file: str) -> str:
    """
    Detect the capture file format by magic bytes and convert to standard
    libpcap if needed. Returns the path to read from (may be a temp file).
    Handles: Sun/Oracle Snoop (v2), pcapng, and standard libpcap.
    editcap (wireshark-common) must be installed on the system.
    """
    with open(pcap_file, 'rb') as f:
        magic = f.read(4)

    # Sun Snoop magic: 0x736e6f6f ("snoo")
    if magic[:4] == b'\x73\x6e\x6f\x6f':
        tmp = tempfile.NamedTemporaryFile(suffix='.pcap', delete=False)
        tmp.close()
        result = subprocess.run(
            ['editcap', '-F', 'pcap', pcap_file, tmp.name],
            capture_output=True, timeout=30
        )
        if result.returncode != 0:
            os.unlink(tmp.name)
            raise ValueError(f"editcap conversion failed: {result.stderr.decode()}")
        return tmp.name  # caller must unlink this

    # pcapng magic: 0x0A0D0D0A
    if magic[:4] == b'\x0a\x0d\x0d\x0a':
        tmp = tempfile.NamedTemporaryFile(suffix='.pcap', delete=False)
        tmp.close()
        result = subprocess.run(
            ['editcap', '-F', 'pcap', pcap_file, tmp.name],
            capture_output=True, timeout=30
        )
        if result.returncode != 0:
            os.unlink(tmp.name)
            raise ValueError(f"editcap conversion failed: {result.stderr.decode()}")
        return tmp.name

    # Standard libpcap (big or little endian): pass through unchanged
    return pcap_file


def extract_sip_messages(pcap_file: str, sip_ports: list = None) -> list:
    """
    Extract SIP messages from an arbitrary PCAP file.
    Returns list of dicts: {timestamp, src_ip, src_port, dst_ip, dst_port,
                             first_line, call_id, raw_text}
    Works on real-world captures including Sun Snoop, pcapng, and libpcap.
    """
    converted_path = None
    try:
        normalized = _normalize_pcap(pcap_file)
        # track if we created a temp file to clean up
        if normalized != pcap_file:
            converted_path = normalized
        packets = list(read_packets(normalized))
    finally:
        if converted_path and os.path.exists(converted_path):
            os.unlink(converted_path)
    messages = []

    for pkt in packets:
        # 0.0.0.0 source is a Wireshark/capture-tool synthetic annotation packet,
        # never real SIP traffic — skip it before doing anything else
        if pkt.src == '0.0.0.0':
            continue
        payload, src_port, dst_port = pkt.payload, pkt.sport, pkt.dport

        if not payload:
            continue

        text = payload.decode('utf-8', errors='ignore')
        if not (text.startswith('SIP/2.0') or
                any(text.startswith(m) for m in
                    ['INVITE ', 'ACK ', 'BYE ', 'CANCEL ', 'OPTIONS ', 'REGISTER ',
                     'REFER ', 'NOTIFY ', 'SUBSCRIBE ', 'INFO ', 'PRACK ', 'UPDATE ',
                     'MESSAGE '])):
            continue

        call_id = None
        for line in text.split('\r\n'):
            if line.lower().startswith('call-id:'):
                call_id = line.split(':', 1)[1].strip()
                break

        first_line = text.split('\r\n')[0]

        messages.append({
            "timestamp": float(pkt.time),
            "src_ip": pkt.src,
            "src_port": src_port,
            "dst_ip": pkt.dst,
            "dst_port": dst_port,
            "first_line": first_line,
            "call_id": call_id,
            "raw_text": text,
            "reason_headers": _parse_reason_headers(text)
        })

    return sorted(messages, key=lambda m: m["timestamp"])


def group_by_call(messages: list) -> dict:
    """Group SIP messages by Call-ID into per-call dialogs."""
    calls = {}
    for msg in messages:
        cid = msg.get("call_id") or "unknown"
        if cid not in calls:
            calls[cid] = []
        calls[cid].append(msg)
    return calls


def characterize_capture(messages: list, calls: dict) -> dict:
    """
    Build a high-level summary of what this capture actually contains —
    needed because unlike our own tests, we don't know the shape going in.
    """
    if not messages:
        return {"call_count": 0, "summary": "No SIP traffic detected"}

    methods_seen = set()
    response_codes_seen = set()
    completed_calls = 0
    failed_calls = 0

    for cid, msgs in calls.items():
        has_200 = False
        has_failure = False
        for m in msgs:
            fl = m["first_line"]
            if fl.startswith("SIP/2.0"):
                parts = fl.split()
                code = parts[1] if len(parts) > 1 else "?"
                response_codes_seen.add(code)
                if code.startswith("2"):
                    has_200 = True
                elif code.startswith(("4", "5", "6")):
                    has_failure = True
            else:
                method = fl.split()[0] if fl.split() else "?"
                methods_seen.add(method)
        if has_200:
            completed_calls += 1
        elif has_failure:
            failed_calls += 1

    start_time = min(m["timestamp"] for m in messages)
    end_time = max(m["timestamp"] for m in messages)

    return {
        "call_count": len(calls),
        "completed_calls": completed_calls,
        "failed_calls": failed_calls,
        "methods_seen": sorted(methods_seen),
        "response_codes_seen": sorted(response_codes_seen),
        "capture_duration_s": round(end_time - start_time, 2),
        "total_sip_messages": len(messages)
    }


def extract_sdp_ports(sip_messages: list) -> dict:
    """
    For each call_id, find the RTP port(s) negotiated via SDP
    in INVITE/200 OK bodies (m=audio <port> ...).
    Returns {call_id: [ports]}
    """
    call_ports = {}
    for msg in sip_messages:
        cid = msg.get("call_id")
        if not cid:
            continue
        text = msg.get("raw_text", "")
        ports = re.findall(r'm=audio\s+(\d+)', text)
        if ports:
            call_ports.setdefault(cid, set()).update(int(p) for p in ports)
    return {cid: sorted(p) for cid, p in call_ports.items()}


def correlate_streams_to_calls_generic(streams: list, sip_messages: list) -> dict:
    """
    Correlate RTP streams to SIP Call-IDs using SDP-negotiated ports —
    works on any PCAP, no companion SIPp log file required.

    Was: matched purely by port number, with NO time-window check. RTP
    ports are commonly reused across separate calls in the same capture
    (SIPp typically declares a fixed local media port per script rather
    than randomizing it per call), so a call that never actually had real
    media — e.g. one that timed out, never answered — could inherit an
    EARLIER, unrelated call's real RTP stream purely because its INVITE's
    SDP OFFER happened to propose the same port number a previous call's
    stream used. Confirmed via a real report: a timed-out call (correct
    Call-ID, correct ladder) showed MOS/packet-loss data that could only
    have come from a different call earlier in the same capture.

    Fix: a stream must ALSO overlap (within a margin) this call's own
    signaling time window, not just share a port number by coincidence.
    Both `stream["first_time"]/["last_time"]` (rtp_extract.py) and
    `sip_messages[]["timestamp"]` (this file) are raw Unix-epoch floats
    from the same pcap frame headers, so they're directly comparable.

    Returns {call_id: [stream, ...]}
    """
    call_ports = extract_sdp_ports(sip_messages)

    # This call's own signaling time window, from its SIP messages
    call_time_range = {}
    for msg in sip_messages:
        cid = msg.get("call_id")
        ts = msg.get("timestamp")
        if not cid or ts is None:
            continue
        lo, hi = call_time_range.get(cid, (ts, ts))
        call_time_range[cid] = (min(lo, ts), max(hi, ts))

    MARGIN_S = 5.0  # generous margin around the call's own signaling window

    result = {}
    for cid, ports in call_ports.items():
        ports_str = set(str(p) for p in ports)
        call_lo, call_hi = call_time_range.get(cid, (None, None))
        matched = []
        for stream in streams:
            src_port = str(stream.get("src_port", ""))
            dst_port = str(stream.get("dst_port", ""))
            if src_port not in ports_str and dst_port not in ports_str:
                continue
            if call_lo is not None:
                stream_start = stream.get("first_time")
                stream_end = stream.get("last_time")
                if stream_start is None or stream_end is None:
                    continue
                # Stream must overlap this call's own window (with
                # margin) — a port match alone isn't enough, since ports
                # get reused across unrelated calls in the same capture.
                if stream_end < call_lo - MARGIN_S or stream_start > call_hi + MARGIN_S:
                    continue
            matched.append(stream)
        if matched:
            result[cid] = matched

    return result
