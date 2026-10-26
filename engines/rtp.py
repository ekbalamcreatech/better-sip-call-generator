import socket
import struct
import time
import os
import random

RTP_HEADER_SIZE = 12
PCMU_PAYLOAD_TYPE = 0
G729_PAYLOAD_TYPE = 18
PCMA_PAYLOAD_TYPE = 8
PACKET_DURATION_MS = 20
SAMPLES_PER_PACKET = 160

def build_rtp_header(seq, timestamp, ssrc, payload_type=PCMU_PAYLOAD_TYPE):
    first_byte = 0x80
    second_byte = payload_type & 0x7F
    return struct.pack('!BBHII',
        first_byte, second_byte,
        seq & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc & 0xFFFFFFFF
    )

def send_rtp(src_ip, src_port, dst_ip, dst_port, pcmu_file, duration_s, payload_type=PCMU_PAYLOAD_TYPE,
             loss_pct=0, jitter_ms=0, burst_loss_ms=0, burst_loss_every_s=0):
    """
    loss_pct: 0-100, percent chance each packet is dropped (random loss)
    jitter_ms: max random delay added/subtracted from each packet's send timing
    burst_loss_ms: if >0, drop all packets for this many ms during a burst event
    burst_loss_every_s: if >0, trigger a burst-loss event every N seconds
    """
    if not os.path.exists(pcmu_file):
        print(f"RTP sender: file not found {pcmu_file}")
        return

    with open(pcmu_file, 'rb') as f:
        audio_data = f.read()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((src_ip, src_port))

    seq = 0
    timestamp = 0
    ssrc = 0x12345678
    offset = 0
    total_packets = int(duration_s * 1000 / PACKET_DURATION_MS)

    impairment_desc = []
    if loss_pct > 0: impairment_desc.append(f"{loss_pct}% loss")
    if jitter_ms > 0: impairment_desc.append(f"±{jitter_ms}ms jitter")
    if burst_loss_ms > 0: impairment_desc.append(f"{burst_loss_ms}ms burst every {burst_loss_every_s}s")
    desc = f" [{', '.join(impairment_desc)}]" if impairment_desc else ""
    print(f"RTP sender: {src_ip}:{src_port} -> {dst_ip}:{dst_port}, {total_packets} packets{desc}")

    start = time.time()
    sent = 0
    dropped = 0
    in_burst_until = 0.0
    next_burst_at = burst_loss_every_s if burst_loss_every_s > 0 else None

    for i in range(total_packets):
        chunk = audio_data[offset:offset + SAMPLES_PER_PACKET]
        if len(chunk) == 0:
            offset = 0
            chunk = audio_data[0:SAMPLES_PER_PACKET]
        if len(chunk) < SAMPLES_PER_PACKET:
            chunk = chunk + b'\x7f' * (SAMPLES_PER_PACKET - len(chunk))
        offset += SAMPLES_PER_PACKET

        header = build_rtp_header(seq, timestamp, ssrc, payload_type)
        packet = header + chunk

        now = time.time()
        elapsed_total = now - start

        # check if a new burst-loss window should start
        if next_burst_at is not None and elapsed_total >= next_burst_at:
            in_burst_until = now + (burst_loss_ms / 1000.0)
            next_burst_at += burst_loss_every_s

        should_drop = False
        if now < in_burst_until:
            should_drop = True  # burst loss in effect
        elif loss_pct > 0 and random.random() * 100 < loss_pct:
            should_drop = True  # random loss

        if should_drop:
            dropped += 1
        else:
            try:
                sock.sendto(packet, (dst_ip, dst_port))
                sent += 1
            except Exception as e:
                print(f"RTP send error: {e}")

        seq = (seq + 1) & 0xFFFF
        timestamp = (timestamp + SAMPLES_PER_PACKET) & 0xFFFFFFFF

        elapsed = time.time() - start
        expected = (i + 1) * PACKET_DURATION_MS / 1000.0

        # apply jitter — randomize the target timing slightly
        if jitter_ms > 0:
            expected += random.uniform(-jitter_ms, jitter_ms) / 1000.0

        sleep_time = expected - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    sock.close()
    print(f"RTP sender: sent {sent} packets, dropped {dropped} packets ({round(dropped/total_packets*100,1) if total_packets else 0}%)")

def receive_rtp(listen_ip, listen_port, output_pcmu, duration_s, timeout=5):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind((listen_ip, listen_port))
    sock.settimeout(1.0)
    payloads = []
    start = time.time()
    deadline = start + duration_s + timeout
    print(f"RTP receiver: listening on {listen_ip}:{listen_port}")
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(4096)
            if len(data) < RTP_HEADER_SIZE:
                continue
            version = (data[0] >> 6) & 0x3
            if version != 2:
                continue
            payload_type = data[1] & 0x7F
            if payload_type != PCMU_PAYLOAD_TYPE:
                continue
            cc = data[0] & 0x0F
            header_len = RTP_HEADER_SIZE + (cc * 4)
            if len(data) > header_len:
                payloads.append(data[header_len:])
        except socket.timeout:
            if payloads and time.time() > start + duration_s:
                break
            continue
        except Exception as e:
            print(f"RTP recv error: {e}")
            break
    sock.close()
    if not payloads:
        print("RTP receiver: no packets captured")
        return False
    with open(output_pcmu, 'wb') as f:
        for p in payloads:
            f.write(p)
    print(f"RTP receiver: captured {len(payloads)} packets, {os.path.getsize(output_pcmu)} bytes")
    return True
