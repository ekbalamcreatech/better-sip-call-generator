"""Central paths and settings. Everything is derived from one base directory.

Environment overrides:
  SIPPTESTER_HOME           app data root (default: the directory containing this file)
  SIPPTESTER_CAPTURE_IFACE  force the tcpdump interface (default: auto-detected per target)
  SIPPTESTER_SUDO           "auto" (default: use `sudo -n` when not root), "0" to never use sudo
"""
import os

BASE_DIR = os.path.abspath(os.environ.get("SIPPTESTER_HOME") or os.path.dirname(os.path.abspath(__file__)))

STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
STIR_DIR = os.path.join(BASE_DIR, "stir")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
SCENARIOS_DIR = os.path.join(BASE_DIR, "scenarios")
WORKSPACE_TEMPLATES_DIR = os.path.join(STORAGE_DIR, "workspace_templates")
SCRIPT_TEMPLATES_DIR = os.path.join(STORAGE_DIR, "script_templates")
HISTORY_FILE = os.path.join(STORAGE_DIR, "history.json")
REFERENCE_WAV = os.path.join(AUDIO_DIR, "reference.wav")
REFERENCE_PCMU = os.path.join(AUDIO_DIR, "reference.pcmu")

# Private runtime directory: generated scenario XML, stats CSVs, SIPp message
# logs, captures. Kept inside the app (mode 0700) instead of world-writable /tmp.
RUN_DIR = os.path.join(BASE_DIR, "run")

for _d in (SCENARIOS_DIR, WORKSPACE_TEMPLATES_DIR, SCRIPT_TEMPLATES_DIR, STORAGE_DIR, STIR_DIR, RUN_DIR):
    os.makedirs(_d, exist_ok=True)
os.chmod(RUN_DIR, 0o700)

TX_SIP_PORT = 5080
RX_SIP_PORT = 5060
TX_RTP_PORT = 6000
RX_RTP_PORT = 7000
