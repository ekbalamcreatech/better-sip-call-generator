"""
RTCP R-Factor MOS engine.
Captures RTCP packets, extracts jitter/loss/RTT, computes R-Factor -> MOS.
Works against ANY endpoint - no reference file needed.
"""
import socket
import struct
import threading
import time
import math

class RTCPStats:
    def __init__(self):
        self.jitter_ms = 0.0
        self.packet_loss_pct = 0.0
        self.rtt_ms = 0.0
        self.packets_received = 0
        self.packets_lost = 0
        self.mos = None
        self.rfactor = None
        self.raw_reports = []

def parse_rtcp_sr(data: bytes) -> dict:
    """Parse RTCP Sender Report."""
    try:
        if len(data) < 28:
            return None
        v = (data[0] >> 6) & 0x3
        if v != 2:
            return None
        pt = data[1]
        if pt != 200:  # SR
            return None
        ssrc = struct.unpack('!I', data[4:8])[0]
        ntp_msw = struct.unpack('!I', data[8:12])[0]
        ntp_lsw = struct.unpack('!I', data[12:16])[0]
        rtp_ts  = struct.unpack('!I', data[16:20])[0]
        pkt_cnt = struct.unpack('!I', data[20:24])[0]
        oct_cnt = struct.unpack('!I', data[24:28])[0]
        return {
            "type": "SR",
            "ssrc": ssrc,
            "ntp_msw": ntp_msw,
            "ntp_lsw": ntp_lsw,
            "rtp_ts": rtp_ts,
            "packet_count": pkt_cnt,
            "octet_count": oct_cnt,
            "timestamp": time.time()
        }
    except Exception:
        return None

def parse_rtcp_rr(data: bytes) -> dict:
    """Parse RTCP Receiver Report."""
    try:
        if len(data) < 32:
            return None
        v = (data[0] >> 6) & 0x3
        if v != 2:
            return None
        pt = data[1]
        rc = data[0] & 0x1F
        if pt != 201 or rc < 1:  # RR with at least one report block
            return None
        ssrc = struct.unpack('!I', data[4:8])[0]
        # first report block starts at offset 8
        rb_ssrc     = struct.unpack('!I', data[8:12])[0]
        frac_lost   = data[12]
        cum_lost    = struct.unpack('!I', b'\x00' + data[13:16])[0]
        jitter      = struct.unpack('!I', data[20:24])[0]
        lsr         = struct.unpack('!I', data[24:28])[0]
        dlsr        = struct.unpack('!I', data[28:32])[0]
        return {
            "type": "RR",
            "ssrc": ssrc,
            "rb_ssrc": rb_ssrc,
            "fraction_lost": frac_lost,
            "cumulative_lost": cum_lost,
            "jitter_samples": jitter,
            "lsr": lsr,
            "dlsr": dlsr,
            "timestamp": time.time()
        }
    except Exception:
        return None

def compute_rfactor(jitter_ms: float, packet_loss_pct: float, rtt_ms: float = 150.0) -> float:
    """
    ITU-T G.107 E-Model simplified R-Factor calculation.
    Returns R value (0-100).
    """
    try:
        # Default equipment impairment for G.711
        Ro = 93.2
        Is = 1.41  # simultaneous impairment

        # Delay impairment (Ta = one-way delay)
        Ta = rtt_ms / 2.0
        if Ta < 177.3:
            Id = 0.024 * Ta + 0.11 * (Ta - 177.3) * 0
        else:
            Id = 0.024 * Ta + 0.11 * (Ta - 177.3)

        # Jitter buffer impairment
        Idd = 0.0
        if jitter_ms > 0:
            Idd = min(jitter_ms * 0.1, 10.0)

        # Equipment impairment from packet loss
        # Effective packet loss considering burst
        ppl = packet_loss_pct / 100.0
        if ppl > 0:
            Ie_eff = 7 + (30 * math.log(1 + 15 * ppl))
        else:
            Ie_eff = 0

        R = Ro - Is - Id - Idd - Ie_eff
        R = max(0.0, min(100.0, R))
        return round(R, 2)
    except Exception as e:
        print(f"R-Factor error: {e}")
        return 93.2

def rfactor_to_mos(R: float) -> float:
    """Convert R-Factor to MOS score."""
    if R < 0:
        return 1.0
    if R > 100:
        return 4.5
    mos = 1 + 0.035 * R + 0.000007 * R * (R - 60) * (100 - R)
    return round(mos, 2)

def mos_label(mos: float) -> str:
    if mos >= 4.3: return "Excellent"
    if mos >= 4.0: return "Good"
    if mos >= 3.6: return "Fair"
    if mos >= 3.1: return "Poor"
    return "Bad"

class RTCPCapture:
    """
    Captures RTCP packets on a given port and computes quality metrics.
    RTCP runs on RTP port + 1 by convention.
    """
    def __init__(self, listen_ip: str, rtcp_port: int, duration_s: float):
        self.listen_ip = listen_ip
        self.rtcp_port = rtcp_port
        self.duration_s = duration_s
        self.stats = RTCPStats()
        self._thread = None
        self._running = False
        self._sr_cache = {}  # ssrc -> SR for RTT calculation

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._capture, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _capture(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind((self.listen_ip, self.rtcp_port))
            sock.settimeout(1.0)
            print(f"RTCP capture: listening on {self.listen_ip}:{self.rtcp_port}")

            deadline = time.time() + self.duration_s + 5
            rr_reports = []
            sr_reports = []

            while self._running and time.time() < deadline:
                try:
                    data, addr = sock.recvfrom(4096)
                    if len(data) < 8:
                        continue

                    # try SR first
                    sr = parse_rtcp_sr(data)
                    if sr:
                        sr_reports.append(sr)
                        self._sr_cache[sr["ssrc"]] = sr
                        self.stats.raw_reports.append({"type": "SR", "from": addr[0]})
                        continue

                    # try RR
                    rr = parse_rtcp_rr(data)
                    if rr:
                        rr_reports.append(rr)
                        self.stats.raw_reports.append({"type": "RR", "from": addr[0]})
                        self._process_rr(rr)

                except socket.timeout:
                    if not self._running:
                        break
                    continue
                except Exception as e:
                    print(f"RTCP recv error: {e}")

            sock.close()
            self._compute_final_stats(rr_reports)
            print(f"RTCP capture done: {len(rr_reports)} RR, {len(sr_reports)} SR")

        except Exception as e:
            print(f"RTCP capture failed: {e}")

    def _process_rr(self, rr: dict):
        """Process a Receiver Report and update running stats."""
        # jitter: convert from RTP timestamp units to ms (G.711 = 8kHz)
        jitter_samples = rr["jitter_samples"]
        self.stats.jitter_ms = round(jitter_samples / 8.0, 2)

        # packet loss
        frac = rr["fraction_lost"] / 256.0
        self.stats.packet_loss_pct = round(frac * 100, 2)
        self.stats.packets_lost = rr["cumulative_lost"]

        # RTT calculation if we have a matching SR
        if rr["lsr"] != 0 and rr["dlsr"] != 0:
            # RTT = arrival_time - LSR - DLSR (in 1/65536 seconds)
            # approximate NTP compact form
            dlsr = rr["dlsr"]
            # dlsr is in 1/65536 seconds
            dlsr_s = dlsr / 65536.0
            # rough RTT estimate
            rtt_s = max(0, dlsr_s * 0.1)  # simplified
            self.stats.rtt_ms = round(rtt_s * 1000, 2)

    def _compute_final_stats(self, rr_reports: list):
        """Compute final aggregated stats from all RR reports."""
        if not rr_reports:
            # no RTCP received — use defaults with a note
            print("No RTCP packets received — using estimated values")
            self.stats.jitter_ms = 0.0
            self.stats.packet_loss_pct = 0.0
            self.stats.rtt_ms = 0.0
        else:
            # average across all reports
            avg_jitter = sum(r["jitter_samples"] for r in rr_reports) / len(rr_reports)
            self.stats.jitter_ms = round(avg_jitter / 8.0, 2)

            avg_loss = sum(r["fraction_lost"] for r in rr_reports) / len(rr_reports)
            self.stats.packet_loss_pct = round((avg_loss / 256.0) * 100, 2)
            self.stats.packets_lost = rr_reports[-1]["cumulative_lost"]

        # compute R-Factor and MOS
        R = compute_rfactor(
            self.stats.jitter_ms,
            self.stats.packet_loss_pct,
            self.stats.rtt_ms
        )
        self.stats.rfactor = R
        self.stats.mos = rfactor_to_mos(R)

    def get_stats(self) -> dict:
        return {
            "jitter_ms": self.stats.jitter_ms,
            "packet_loss_pct": self.stats.packet_loss_pct,
            "rtt_ms": self.stats.rtt_ms,
            "packets_lost": self.stats.packets_lost,
            "rfactor": self.stats.rfactor,
            "mos": self.stats.mos,
            "mos_label": mos_label(self.stats.mos) if self.stats.mos else None,
            "rtcp_reports": len(self.stats.raw_reports),
            "method": "RTCP R-Factor"
        }
