"""
RTP Extraction and Playback engine.
Extracts RTP streams from PCAP, decodes to WAV, serves for browser playback.
Per-call quality metrics from SSRC correlation.
"""
import os
import shutil
import subprocess
import struct
import wave
from config import RUN_DIR

AUDIO_OUTPUT_DIR = os.path.join(RUN_DIR, "sipp_audio")
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

def extract_rtp_streams(pcap_file: str, rtp_ports: list = None) -> list:
    """
    Extract RTP streams from PCAP using raw packet parsing.
    No tshark dependency.
    """
    if not os.path.exists(pcap_file):
        return []

    try:
        streams = {}

        with open(pcap_file, 'rb') as f:
            # read global header
            magic = f.read(4)
            if magic == b'\xd4\xc3\xb2\xa1':
                endian = '<'
            elif magic == b'\xa1\xb2\xc3\xd4':
                endian = '>'
            else:
                print(f"Not a valid PCAP file: {pcap_file}")
                return []

            ver_maj, ver_min, thiszone, sigfigs, snaplen, network = struct.unpack(endian+'HHiIII', f.read(20))

            # network type: 1=Ethernet, 101=raw IP
            eth_offset = 14 if network == 1 else 0

            frame_time = 0
            while True:
                hdr = f.read(16)
                if len(hdr) < 16:
                    break

                ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian+'IIII', hdr)
                frame_time = ts_sec + ts_usec / 1e6
                data = f.read(incl_len)

                if len(data) < incl_len:
                    break

                try:
                    # skip Ethernet header
                    pos = eth_offset

                    # IP header
                    if len(data) < pos + 20:
                        continue
                    ip_ver_ihl = data[pos]
                    ip_ihl = (ip_ver_ihl & 0x0F) * 4
                    proto = data[pos + 9]

                    if proto != 17:  # UDP only
                        continue

                    src_ip = '.'.join(str(b) for b in data[pos+12:pos+16])
                    dst_ip = '.'.join(str(b) for b in data[pos+16:pos+20])

                    pos += ip_ihl

                    # UDP header
                    if len(data) < pos + 8:
                        continue
                    src_port = struct.unpack('!H', data[pos:pos+2])[0]
                    dst_port = struct.unpack('!H', data[pos+2:pos+4])[0]
                    udp_len  = struct.unpack('!H', data[pos+4:pos+6])[0]

                    pos += 8
                    payload = data[pos:pos + udp_len - 8]

                    if len(payload) < 12:
                        continue

                    # skip SIP, ICMP, RTCP ports
                    if src_port in [5060, 5061, 5080, 5081, 5082] or \
                       dst_port in [5060, 5061, 5080, 5081, 5082]:
                        continue

                    # skip RTCP (odd ports typically)
                    # RTP header validation
                    v = (payload[0] >> 6) & 0x3
                    if v != 2:  # RTP version must be 2
                        continue

                    pt = payload[1] & 0x7F

                    # skip telephone-event and unknown payload types
                    if pt not in [0, 8, 18, 96, 97, 98, 101]:
                        continue

                    seq = struct.unpack('!H', payload[2:4])[0]
                    ts  = struct.unpack('!I', payload[4:8])[0]
                    ssrc = struct.unpack('!I', payload[8:12])[0]
                    ssrc_hex = f"0x{ssrc:08x}"

                    # RTP payload starts after 12-byte header
                    rtp_payload = payload[12:]

                    key = ssrc_hex
                    if key not in streams:
                        streams[key] = {
                            "ssrc": ssrc_hex,
                            "src_ip": src_ip,
                            "dst_ip": dst_ip,
                            "src_port": str(src_port),
                            "dst_port": str(dst_port),
                            "payload_type": pt,
                            "codec": _pt_to_codec(pt),
                            "packets": [],
                            "first_time": frame_time,
                            "last_time": frame_time,
                            "raw_payloads": bytearray()
                        }

                    streams[key]["packets"].append({
                        "time": frame_time,
                        "seq": seq,
                        "ts": ts,
                    })
                    streams[key]["raw_payloads"].extend(rtp_payload)
                    streams[key]["last_time"] = frame_time

                except Exception:
                    continue

        return list(streams.values())

    except Exception as e:
        print(f"RTP extract error: {e}")
        return []

def _pt_to_codec(pt: int) -> str:
    return {0: "PCMU", 8: "PCMA", 18: "G729", 101: "telephone-event"}.get(pt, f"PT{pt}")


def decode_stream_to_wav(stream: dict, output_path: str) -> bool:
    """Decode RTP stream to WAV."""
    codec = stream.get("codec", "PCMU")
    raw_payload = bytes(stream.get("raw_payloads", bytearray()))

    if not raw_payload:
        print(f"No payload data for stream {stream.get('ssrc')}")
        return False

    print(f"Decoding {len(raw_payload)} bytes of {codec} audio")

    try:
        if codec == 'PCMU':
            result = subprocess.run([
                "ffmpeg", "-y",
                "-f", "mulaw", "-ar", "8000", "-ac", "1",
                "-i", "pipe:0",
                output_path
            ], input=raw_payload, capture_output=True, timeout=30)
            return result.returncode == 0

        elif codec == 'PCMA':
            result = subprocess.run([
                "ffmpeg", "-y",
                "-f", "alaw", "-ar", "8000", "-ac", "1",
                "-i", "pipe:0",
                output_path
            ], input=raw_payload, capture_output=True, timeout=30)
            return result.returncode == 0

        elif codec == 'G729':
            from engines.g729 import G729Decoder
            decoder = G729Decoder()
            pcm_data = decoder.decode_bitstream(raw_payload)
            with wave.open(output_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(pcm_data)
            return True

    except Exception as e:
        print(f"Decode error for {codec}: {e}")
        return False

def compute_per_stream_quality(stream: dict) -> dict:
    """
    Compute quality metrics from RTP stream.
    Jitter, packet loss, duration.
    """
    packets = sorted(stream.get("packets", []), key=lambda p: p["seq"])
    if len(packets) < 2:
        return {}

    # jitter calculation (RFC 3550)
    jitter = 0.0
    jitter_samples = []

    for i in range(1, len(packets)):
        send_diff = packets[i]["ts"] - packets[i-1]["ts"]
        recv_diff = (packets[i]["time"] - packets[i-1]["time"]) * 8000
        d = abs(recv_diff - send_diff)
        jitter += (d - jitter) / 16.0
        jitter_samples.append(jitter / 8.0)  # convert to ms

    # packet loss
    if packets:
        expected = packets[-1]["seq"] - packets[0]["seq"] + 1
        received = len(packets)
        loss_pct = max(0, (expected - received) / expected * 100) if expected > 0 else 0
    else:
        loss_pct = 0

    avg_jitter = sum(jitter_samples) / len(jitter_samples) if jitter_samples else 0
    max_jitter = max(jitter_samples) if jitter_samples else 0
    duration = stream.get("last_time", 0) - stream.get("first_time", 0)

    # R-Factor → MOS
    from engines.rtcp import compute_rfactor, rfactor_to_mos, mos_label
    R = compute_rfactor(avg_jitter, loss_pct, 0)
    mos = rfactor_to_mos(R)

    return {
        "jitter_avg_ms": round(avg_jitter, 2),
        "jitter_max_ms": round(max_jitter, 2),
        "packet_loss_pct": round(loss_pct, 2),
        "packets_received": len(packets),
        "duration_s": round(duration, 2),
        "rfactor": round(R, 2),
        "mos": round(mos, 2),
        "mos_label": mos_label(mos),
        "codec": stream.get("codec"),
        "ssrc": stream.get("ssrc")
    }

def correlate_streams_to_calls(streams: list, messages_log: str) -> dict:
    """
    Correlate RTP streams to SIP Call-IDs via timing.
    Returns {call_id: {outbound: quality, inbound: quality}}
    """
    import re
    if not messages_log or not os.path.exists(messages_log):
        return {}

    # parse call timing from messages log
    call_windows = {}
    with open(messages_log) as f:
        content = f.read()

    blocks = content.split("-----------------------------------------------")
    for block in blocks:
        cid_match = re.search(r'Call-ID:\s*(.+)', block, re.IGNORECASE)
        ts_match  = re.search(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\.\d+)', block)
        if not cid_match or not ts_match:
            continue
        cid = cid_match.group(1).strip()
        if cid not in call_windows:
            call_windows[cid] = {"start": None, "end": None}
        ts = ts_match.group(1).replace(" ", "T")
        if call_windows[cid]["start"] is None:
            call_windows[cid]["start"] = ts
        call_windows[cid]["end"] = ts

    return call_windows

def get_playback_streams(workspace: str) -> list:
    """Get available RTP streams for playback."""
    pcap = f"{RUN_DIR}/rtp_{workspace}_capture.pcap"
    converted = f"{RUN_DIR}/rtp_{workspace}_converted.pcap"

    if not os.path.exists(pcap):
        return []

    # tcpdump already writes classic pcap; editcap (optional) only normalises it.
    if shutil.which("editcap") and (
            not os.path.exists(converted) or os.path.getmtime(converted) < os.path.getmtime(pcap)):
        subprocess.run(["editcap", "-F", "pcap", pcap, converted], capture_output=True)
    if not os.path.exists(converted):
        converted = pcap

    streams = extract_rtp_streams(converted)

    # compute quality for each stream
    result = []
    for s in streams:
        if s.get("codec") == "telephone-event":
            continue
        quality = compute_per_stream_quality(s)
        result.append({
            "ssrc": s["ssrc"],
            "src": f"{s['src_ip']}:{s['src_port']}",
            "dst": f"{s['dst_ip']}:{s['dst_port']}",
            "codec": s["codec"],
            "packets": len(s["packets"]),
            "duration_s": quality.get("duration_s", 0),
            "quality": quality
        })

    return result
