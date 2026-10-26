"""
A small, dependency-free reader for classic libpcap files (what tcpdump writes).

It yields IPv4 UDP/TCP packets only, which is all the SIP and RTP analysis needs.
pcapng files are converted to classic pcap first (see sip_extract._normalize_pcap).
Supported link types: Ethernet (with VLAN tags), raw IP, BSD loopback, Linux
cooked capture v1 and v2.
"""
import socket
import struct
from typing import Iterator, NamedTuple

_ETHERNET, _NULL, _RAW, _RAW2, _SLL, _SLL2 = 1, 0, 101, 12, 113, 276


class Packet(NamedTuple):
    time: float
    src: str
    dst: str
    proto: str        # "UDP" or "TCP"
    sport: int
    dport: int
    payload: bytes


def _ip_offset(linktype: int, data: bytes):
    """Where the IPv4 header starts, or None if this frame isn't IPv4."""
    if linktype == _ETHERNET:
        off, ethertype = 14, struct.unpack("!H", data[12:14])[0] if len(data) >= 14 else 0
        while ethertype in (0x8100, 0x88A8) and len(data) >= off + 4:   # VLAN tags
            ethertype = struct.unpack("!H", data[off + 2:off + 4])[0]
            off += 4
        return off if ethertype == 0x0800 else None
    if linktype == _NULL:
        return 4 if len(data) > 4 and data[0:4] in (b"\x02\x00\x00\x00", b"\x00\x00\x00\x02") else None
    if linktype in (_RAW, _RAW2):
        return 0 if data and data[0] >> 4 == 4 else None
    if linktype == _SLL:
        return 16 if len(data) > 16 and data[14:16] == b"\x08\x00" else None
    if linktype == _SLL2:
        return 20 if len(data) > 20 and data[0:2] == b"\x08\x00" else None
    return None


def read_packets(path: str) -> Iterator[Packet]:
    with open(path, "rb") as f:
        head = f.read(24)
        if len(head) < 24:
            raise ValueError("Not a pcap file (too short)")
        magic = head[:4]
        if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
            endian = "<"
        elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
            endian = ">"
        else:
            raise ValueError("Not a classic pcap file")
        nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
        linktype = struct.unpack(endian + "I", head[20:24])[0]
        frac = 1e9 if nano else 1e6
        while True:
            rec = f.read(16)
            if len(rec) < 16:
                return
            sec, sub, caplen, _orig = struct.unpack(endian + "IIII", rec)
            data = f.read(caplen)
            if len(data) < caplen:
                return
            off = _ip_offset(linktype, data)
            if off is None or len(data) < off + 20:
                continue
            ihl = (data[off] & 0x0F) * 4
            proto = data[off + 9]
            if proto not in (6, 17) or ihl < 20:
                continue
            frag = struct.unpack("!H", data[off + 6:off + 8])[0] & 0x1FFF
            if frag:                       # later fragments carry no UDP/TCP header
                continue
            total = struct.unpack("!H", data[off + 2:off + 4])[0]
            ip_end = min(len(data), off + total) if total >= ihl else len(data)
            t = off + ihl
            if proto == 17:
                if ip_end < t + 8:
                    continue
                sport, dport, ulen = struct.unpack("!HHH", data[t:t + 6])
                payload = data[t + 8:min(ip_end, t + ulen)] if ulen >= 8 else data[t + 8:ip_end]
                name = "UDP"
            else:
                if ip_end < t + 20:
                    continue
                sport, dport = struct.unpack("!HH", data[t:t + 4])
                doff = (data[t + 12] >> 4) * 4
                payload = data[t + doff:ip_end]
                name = "TCP"
            yield Packet(sec + sub / frac, socket.inet_ntoa(data[off + 12:off + 16]),
                         socket.inet_ntoa(data[off + 16:off + 20]), name, sport, dport, payload)
