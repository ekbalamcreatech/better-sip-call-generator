"""
PCAP export engine.
Builds valid PCAP file from SIPp messages log.
Output can be opened directly in Wireshark.
"""
import struct
import re
import os
import glob
import subprocess
from datetime import datetime
from config import RUN_DIR

# PCAP global header constants
PCAP_MAGIC = 0xa1b2c3d4
PCAP_VERSION_MAJOR = 2
PCAP_VERSION_MINOR = 4
PCAP_THISZONE = 0
PCAP_SIGFIGS = 0
PCAP_SNAPLEN = 65535
PCAP_NETWORK = 1  # Ethernet

def pcap_global_header() -> bytes:
    return struct.pack('<IHHiIII',
        PCAP_MAGIC,
        PCAP_VERSION_MAJOR,
        PCAP_VERSION_MINOR,
        PCAP_THISZONE,
        PCAP_SIGFIGS,
        PCAP_SNAPLEN,
        PCAP_NETWORK
    )

def pcap_record_header(ts_sec: int, ts_usec: int, data_len: int) -> bytes:
    return struct.pack('<IIII',
        ts_sec,
        ts_usec,
        data_len,
        data_len
    )

def build_udp_packet(
    src_ip: str, dst_ip: str,
    src_port: int, dst_port: int,
    payload: bytes
) -> bytes:
    """Build Ethernet + IP + UDP packet wrapping SIP payload."""

    def ip_to_bytes(ip: str) -> bytes:
        return bytes(int(x) for x in ip.split('.'))

    # UDP header
    udp_len = 8 + len(payload)
    udp = struct.pack('!HHHH',
        src_port, dst_port,
        udp_len, 0  # checksum=0 (ignored by Wireshark)
    ) + payload

    # IP header (no options)
    ip_len = 20 + len(udp)
    ip = struct.pack('!BBHHHBBH4s4s',
        0x45,           # version=4, IHL=5
        0,              # DSCP/ECN
        ip_len,
        0,              # identification
        0x4000,         # flags: don't fragment
        64,             # TTL
        17,             # protocol: UDP
        0,              # checksum (ignored)
        ip_to_bytes(src_ip),
        ip_to_bytes(dst_ip)
    )

    # Ethernet header (fake MACs)
    eth = bytes([
        0x00, 0x00, 0x00, 0x00, 0x00, 0x02,  # dst MAC
        0x00, 0x00, 0x00, 0x00, 0x00, 0x01,  # src MAC
        0x08, 0x00                             # EtherType: IPv4
    ])

    return eth + ip + udp

def parse_timestamp(ts_str: str) -> tuple:
    """Parse ISO timestamp to (sec, usec)."""
    try:
        # format: 2026-06-03T14:14:38.226821-05:00
        ts_str = ts_str.split('+')[0].split('-05:00')[0].split('-06:00')[0]
        ts_str = ts_str.replace('T', ' ')
        if '.' in ts_str:
            base, frac = ts_str.split('.')
            dt = datetime.strptime(base, '%Y-%m-%d %H:%M:%S')
            usec = int(frac[:6].ljust(6, '0'))
        else:
            dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            usec = 0
        return int(dt.timestamp()), usec
    except Exception:
        return int(datetime.now().timestamp()), 0

def extract_sip_messages(log_file: str) -> list:
    """Extract SIP messages from SIPp messages log."""
    messages = []
    if not os.path.exists(log_file):
        return messages

    with open(log_file) as f:
        content = f.read()

    blocks = content.split("-----------------------------------------------")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        direction = None
        if "UDP message sent" in block:
            direction = "sent"
        elif "UDP message received" in block:
            direction = "received"
        else:
            continue

        # extract timestamp
        ts_match = re.search(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\.\d+)', block)
        timestamp = ts_match.group(1).replace(" ", "T") if ts_match else None

        # extract IPs/ports from Via header
        src_ip, dst_ip = "127.0.0.1", "127.0.0.1"
        src_port, dst_port = 5080, 5060

        via_match = re.search(r'Via: SIP/2.0/UDP (\d+\.\d+\.\d+\.\d+):(\d+)', block)
        if via_match:
            if direction == "sent":
                src_ip = via_match.group(1)
                src_port = int(via_match.group(2))
            else:
                dst_ip = via_match.group(1)
                dst_port = int(via_match.group(2))

        # extract raw SIP message
        lines = block.split("\n")
        sip_lines = []
        capture = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("INVITE","ACK","BYE","CANCEL","REGISTER","OPTIONS","SIP/2.0")):
                capture = True
            if capture:
                sip_lines.append(line)

        if sip_lines:
            sip_payload = "\r\n".join(l.strip() for l in sip_lines) + "\r\n"
            messages.append({
                "direction": direction,
                "timestamp": timestamp,
                "src_ip": src_ip,
                "src_port": src_port,
                "dst_ip": dst_ip,
                "dst_port": dst_port,
                "payload": sip_payload.encode('utf-8', errors='replace')
            })

    return messages

def merge_pcaps(input_files: list, output_file: str) -> bool:
    """Merge multiple PCAP files into one, sorted by timestamp."""
    try:
        result = subprocess.run(
            ["mergecap", "-w", output_file] + input_files,
            capture_output=True
        )
        if result.returncode == 0:
            return True
        # fallback — just concatenate packets
        all_packets = []
        for pcap_file in input_files:
            if not os.path.exists(pcap_file):
                continue
            with open(pcap_file, 'rb') as f:
                f.read(24)  # skip global header
                while True:
                    hdr = f.read(16)
                    if len(hdr) < 16:
                        break
                    ts_sec, ts_usec, incl_len, orig_len = struct.unpack('<IIII', hdr)
                    data = f.read(incl_len)
                    all_packets.append((ts_sec, ts_usec, data))

        # sort by timestamp
        all_packets.sort(key=lambda x: (x[0], x[1]))

        with open(output_file, 'wb') as f:
            f.write(pcap_global_header())
            for ts_sec, ts_usec, data in all_packets:
                f.write(pcap_record_header(ts_sec, ts_usec, len(data)))
                f.write(data)
        return True
    except Exception as e:
        print(f"Merge PCAP error: {e}")
        return False

def build_pcap(log_file: str, output_path: str) -> bool:
    """Build PCAP file from SIPp messages log."""
    try:
        messages = extract_sip_messages(log_file)
        if not messages:
            print(f"No messages found in {log_file}")
            return False

        with open(output_path, 'wb') as f:
            f.write(pcap_global_header())
            for msg in messages:
                pkt = build_udp_packet(
                    msg["src_ip"], msg["dst_ip"],
                    msg["src_port"], msg["dst_port"],
                    msg["payload"]
                )
                ts_sec, ts_usec = parse_timestamp(msg["timestamp"]) if msg["timestamp"] else (0, 0)
                f.write(pcap_record_header(ts_sec, ts_usec, len(pkt)))
                f.write(pkt)

        size = os.path.getsize(output_path)
        print(f"PCAP built: {output_path} ({size} bytes, {len(messages)} packets)")
        return True

    except Exception as e:
        print(f"PCAP build error: {e}")
        return False

def get_latest_log(prefix: str = "uac") -> str:
    """Get latest messages log for given prefix."""
    files = glob.glob(f"{RUN_DIR}/scenario_{prefix}_*_messages.log")
    if not files:
        return None
    return max(files, key=os.path.getmtime)
