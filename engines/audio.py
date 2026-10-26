import os
import subprocess
from config import BASE_DIR

AUDIO_DIR = os.path.join(BASE_DIR, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

def get_audio_files() -> list:
    """List available audio files."""
    files = []
    for f in os.listdir(AUDIO_DIR):
        if f.endswith(('.wav', '.pcmu', '.raw')):
            path = os.path.join(AUDIO_DIR, f)
            duration = get_audio_duration(path)
            files.append({
                "filename": f,
                "path": path,
                "duration_s": duration
            })
    return files

def get_audio_duration(path: str) -> float:
    """Get duration of audio file in seconds."""
    try:
        if path.endswith('.wav'):
            result = subprocess.run(
                ["soxi", "-D", path],
                capture_output=True, text=True
            )
            return round(float(result.stdout.strip()), 2)
        elif path.endswith('.pcmu') or path.endswith('.raw'):
            # G.711 PCMU: 8000 samples/sec, 1 byte/sample
            size = os.path.getsize(path)
            return round(size / 8000.0, 2)
    except Exception as e:
        print(f"Duration error: {e}")
    return 30.0

def calculate_call_duration(audio_file: str, mode: str, value: int) -> int:
    """
    Calculate call duration in milliseconds.
    mode: 'plays' → value = number of times to play
    mode: 'duration' → value = seconds
    Returns milliseconds for SIPp pause.
    """
    if mode == 'duration':
        return value * 1000
    elif mode == 'plays':
        file_duration = get_audio_duration(audio_file)
        # add 50ms gap between plays
        total = (file_duration * value) + (0.05 * (value - 1))
        return int(total * 1000)
    return 30000

def prepare_codec_file(wav_path: str, codec: str) -> str:
    """Prepare audio file in the right codec format."""
    if codec == 'PCMU':
        pcmu_path = wav_path.replace('.wav', '.pcmu')
        if not os.path.exists(pcmu_path):
            subprocess.run([
                "ffmpeg", "-y", "-i", wav_path,
                "-ar", "8000", "-ac", "1",
                "-acodec", "pcm_mulaw", "-f", "mulaw",
                pcmu_path
            ], capture_output=True)
        return pcmu_path
    elif codec == 'PCMA':
        pcma_path = wav_path.replace('.wav', '.pcma')
        if not os.path.exists(pcma_path):
            subprocess.run([
                "ffmpeg", "-y", "-i", wav_path,
                "-ar", "8000", "-ac", "1",
                "-acodec", "pcm_alaw", "-f", "alaw",
                pcma_path
            ], capture_output=True)
        return pcma_path
    elif codec == 'G729':
        from engines.g729 import prepare_g729_reference
        return prepare_g729_reference(wav_path)
    return wav_path
