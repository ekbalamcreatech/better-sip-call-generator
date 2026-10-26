import subprocess
import os

def convert_pcmu_to_wav(pcmu_path: str, wav_path: str) -> bool:
    try:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "mulaw",
            "-ar", "8000",
            "-ac", "1",
            "-i", pcmu_path,
            wav_path
        ], capture_output=True)
        return result.returncode == 0 and os.path.exists(wav_path)
    except Exception as e:
        print(f"Convert error: {e}")
        return False

def compute_pesq(ref_wav: str, deg_wav: str) -> float:
    try:
        import soundfile as sf
        import numpy as np
        from pesq import pesq
        if not os.path.exists(deg_wav):
            return None
        ref, ref_sr = sf.read(ref_wav)
        deg, deg_sr = sf.read(deg_wav)
        min_len = min(len(ref), len(deg))
        if min_len < 8000:
            print(f"Audio too short: {min_len} samples")
            return None
        ref = ref[:min_len].astype(np.float32)
        deg = deg[:min_len].astype(np.float32)
        if np.max(np.abs(ref)) > 0:
            ref = ref / np.max(np.abs(ref))
        if np.max(np.abs(deg)) > 0:
            deg = deg / np.max(np.abs(deg))
        score = pesq(8000, ref, deg, 'nb')
        print(f"PESQ MOS: {score}")
        return round(float(score), 2)
    except Exception as e:
        print(f"PESQ error: {e}")
        return None

def compute_rfactor_mos(jitter_ms: float, packet_loss_pct: float, latency_ms: float = 150) -> float:
    """
    Compute R-Factor and MOS from network metrics.
    ITU-T G.107 E-Model simplified.
    """
    try:
        # Delay impairment
        if latency_ms < 177.3:
            Id = 0.024 * latency_ms + 0.11 * (latency_ms - 177.3) * 0
        else:
            Id = 0.024 * latency_ms + 0.11 * (latency_ms - 177.3)

        # Equipment impairment from packet loss and jitter
        Ie_eff = 7 + (30 * packet_loss_pct / 100)

        # Jitter buffer delay
        Idd = 0
        if jitter_ms > 0:
            Idd = jitter_ms * 0.1

        R = 93.2 - Id - Ie_eff - Idd
        R = max(0, min(100, R))

        # R to MOS conversion
        if R < 0:
            mos = 1.0
        elif R > 100:
            mos = 4.5
        else:
            mos = 1 + 0.035 * R + 0.000007 * R * (R - 60) * (100 - R)

        return round(float(mos), 2)
    except Exception as e:
        print(f"R-Factor error: {e}")
        return None

def mos_label(mos: float) -> str:
    if mos >= 4.3: return "Excellent"
    if mos >= 4.0: return "Good"
    if mos >= 3.6: return "Fair"
    if mos >= 3.1: return "Poor"
    return "Bad"
