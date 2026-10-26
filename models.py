import ipaddress
import os
import re
from pydantic import BaseModel, field_validator
from typing import Literal, Optional, List, Dict

# ─── Input rules ──────────────────────────────────────────────────────────────
# Everything below ends up in a SIPp command line, a CSV file or a file path, so it is
# checked here, once, at the API boundary. Nothing may start with "-" (SIPp would read
# it as an option) and no field may contain line breaks or the CSV separator.
MAX_CPS = float(os.environ.get("SIPPTESTER_MAX_CPS", "1000"))
MAX_INTERVAL_S = 24 * 3600
CODECS = {"PCMU", "PCMA", "G729"}
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$")
_NUMBER = re.compile(r"^[0-9A-Za-z+*#\[\]\-._]{0,64}$")        # digits, ranges like 555[0001-0100]
_DIGITS = re.compile(r"^[0-9A-Da-d*#]{0,64}$")                    # DTMF
_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ \-]{0,127}$")  # a file name, never a path
_LABEL = re.compile(r"^[^\x00-\x1f\x7f]{0,64}$")
_SECRET = re.compile(r"^[^\x00-\x1f\x7f;\[\]]{0,128}$")        # would break the CSV / [authentication] keyword


def _check(rx, value: str, what: str) -> str:
    if not isinstance(value, str) or not rx.match(value):
        raise ValueError(f"{what} contains characters that are not allowed")
    return value


def _port(value, what: str, allow_empty: bool = False) -> str:
    v = str(value).strip()
    if allow_empty and v == "":
        return v
    if not (v.isdigit() and 0 < int(v) < 65536):
        raise ValueError(f"{what} must be a port number between 1 and 65535")
    return v


def _ipv4(value: str, what: str) -> str:
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        raise ValueError(f"{what} must be an IPv4 address")
    return value


class SUTConfig(BaseModel):
    ip: str = "127.0.0.1"
    port: str = "5060"

# ─── Script ───────────────────────────────────────────────────────────────────
class NumberPair(BaseModel):
    calling: str = "5550001"
    called: str = "9723612348"
    auth_username: str = ""    # used when ScriptConfig.auth_mode == "per_row"
    auth_password: str = ""    # used when ScriptConfig.auth_mode == "per_row"
    stir_attest: str = ""      # used when ScriptConfig.stir_mode == "per_row"; empty = inherit script default

    @field_validator("calling", "called")
    @classmethod
    def _numbers(cls, v):
        return _check(_NUMBER, v, "Phone number")

    @field_validator("auth_username", "auth_password")
    @classmethod
    def _secrets(cls, v):
        return _check(_SECRET, v, "Credential")

    @field_validator("stir_attest")
    @classmethod
    def _attest(cls, v):
        if v not in ("", "A", "B", "C"):
            raise ValueError("Attestation must be A, B or C")
        return v

class ScriptConfig(BaseModel):
    script_id: int
    sut_name: str = "Local-UAS"
    sut_ip: str = "127.0.0.1"
    sut_port: str = "5060"
    orig_ip: str = "127.0.0.1"
    sip_port: str = "5081"
    pct: int = 100                 # % allocation — must sum to 100
    number_pairs: List[NumberPair] = []
    called_num: str = ""
    calling_num: str = ""
    audio_file: str = "reference.wav"
    audio_mode: str = "plays"
    audio_value: int = 2
    codec: str = "PCMU"
    duration_ms: int = 60000
    dtmf_enabled: bool = False
    dtmf_digits: str = ""
    dtmf_gap_ms: int = 100
    enable_rtp: bool = False
    rtp_loss_pct: float = 0
    rtp_jitter_ms: int = 0
    rtp_burst_loss_ms: int = 0
    rtp_burst_loss_every_s: int = 0
    stir_enabled: bool = False
    stir_attest: str = "A"         # used when stir_mode == "single" (the uniform attestation level); also the fallback default for any per-row entry that doesn't override it
    stir_mode: str = "single"      # "single" or "per_row" — mirrors auth_mode exactly
    auth_enabled: bool = False
    auth_mode: str = "single"      # "single" or "per_row"
    auth_username: str = ""        # used when auth_mode == "single"
    auth_password: str = ""        # used when auth_mode == "single"
    xml: str = ""

    @field_validator("sut_ip")
    @classmethod
    def _sut_ip(cls, v):
        return _check(_HOST, v, "Target address")

    @field_validator("orig_ip")
    @classmethod
    def _orig_ip(cls, v):
        return _ipv4(v, "Originating IP")

    @field_validator("sut_port")
    @classmethod
    def _sut_port(cls, v):
        return _port(v, "Target port")

    @field_validator("sip_port")
    @classmethod
    def _sip_port(cls, v):
        return _port(v, "Source port", allow_empty=True)

    @field_validator("pct")
    @classmethod
    def _pct(cls, v):
        if not 0 <= v <= 100:
            raise ValueError("% share must be between 0 and 100")
        return v

    @field_validator("sut_name")
    @classmethod
    def _sut_name(cls, v):
        return _check(_LABEL, v, "SUT name")

    @field_validator("called_num", "calling_num")
    @classmethod
    def _nums(cls, v):
        return _check(_NUMBER, v, "Phone number")

    @field_validator("audio_file")
    @classmethod
    def _audio_file(cls, v):
        if ".." in v:
            raise ValueError("Audio file must be a plain file name")
        return _check(_FILENAME, v, "Audio file name")

    @field_validator("audio_mode")
    @classmethod
    def _audio_mode(cls, v):
        if v not in ("plays", "seconds"):
            raise ValueError("audio_mode must be 'plays' or 'seconds'")
        return v

    @field_validator("codec")
    @classmethod
    def _codec(cls, v):
        if v not in CODECS:
            raise ValueError(f"codec must be one of {sorted(CODECS)}")
        return v

    @field_validator("duration_ms")
    @classmethod
    def _duration(cls, v):
        if not 0 <= v <= MAX_INTERVAL_S * 1000:
            raise ValueError("duration_ms is out of range")
        return v

    @field_validator("audio_value", "dtmf_gap_ms", "rtp_jitter_ms", "rtp_burst_loss_ms", "rtp_burst_loss_every_s")
    @classmethod
    def _small_ints(cls, v):
        if not 0 <= v <= 86400:
            raise ValueError("value is out of range")
        return v

    @field_validator("rtp_loss_pct")
    @classmethod
    def _loss(cls, v):
        if not 0 <= v <= 100:
            raise ValueError("rtp_loss_pct must be between 0 and 100")
        return v

    @field_validator("dtmf_digits")
    @classmethod
    def _dtmf(cls, v):
        return _check(_DIGITS, v, "DTMF digits")

    @field_validator("stir_attest")
    @classmethod
    def _attest(cls, v):
        if v not in ("A", "B", "C"):
            raise ValueError("Attestation must be A, B or C")
        return v

    @field_validator("stir_mode", "auth_mode")
    @classmethod
    def _modes(cls, v):
        if v not in ("single", "per_row"):
            raise ValueError("mode must be 'single' or 'per_row'")
        return v

    @field_validator("auth_username", "auth_password")
    @classmethod
    def _secrets(cls, v):
        return _check(_SECRET, v, "Credential")

# ─── Interval ─────────────────────────────────────────────────────────────────
class IntervalConfig(BaseModel):
    interval_id: int
    duration_s: int = 30
    label: str = ""
    script_cps: Dict[str, float] = {}

    @field_validator("duration_s")
    @classmethod
    def _dur(cls, v):
        if not 1 <= v <= MAX_INTERVAL_S:
            raise ValueError(f"duration_s must be between 1 and {MAX_INTERVAL_S}")
        return v

    @field_validator("label")
    @classmethod
    def _lbl(cls, v):
        return _check(_LABEL, v, "Label")

    @field_validator("script_cps")
    @classmethod
    def _cps(cls, v):
        for sid, cps in v.items():
            if not str(sid).isdigit() or not 0 <= cps <= MAX_CPS:
                raise ValueError(f"CPS must be between 0 and {MAX_CPS:g} (set SIPPTESTER_MAX_CPS to raise the limit)")
        return v

# ─── Workspace ────────────────────────────────────────────────────────────────
class WorkspaceConfig(BaseModel):
    workspace_id: int
    label: str = ""
    role: str = "tx"               # "tx" or "rx"
    ip: str = "127.0.0.1"
    sip_port: int = 5060
    scripts: List[ScriptConfig] = []
    intervals: List[IntervalConfig] = []

    @field_validator("label")
    @classmethod
    def _label(cls, v):
        return _check(_LABEL, v, "Workspace label")

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ("tx", "rx"):
            raise ValueError("role must be 'tx' or 'rx'")
        return v

    @field_validator("ip")
    @classmethod
    def _ip(cls, v):
        return _ipv4(v, "Workspace IP")

    @field_validator("sip_port")
    @classmethod
    def _port_range(cls, v):
        _port(v, "Workspace port")
        return v

class WorkspaceStart(BaseModel):
    workspace_id: int
    scripts: List[ScriptConfig]
    intervals: List[IntervalConfig] = []
    continuous: bool = False

class WorkspaceStop(BaseModel):
    workspace_id: int

# ─── RX ───────────────────────────────────────────────────────────────────────
class RXStart(BaseModel):
    workspace_id: int
    term_ip: str = "127.0.0.1"
    listen_port: str = "5060"
    enable_mos: bool = False
    xml: Optional[str] = None

class ScenarioSave(BaseModel):
    name: str
    description: str = ""
    xml: str
    mode: Literal["tx", "rx"] = "tx"

class WorkspaceTemplateSave(BaseModel):
    name: str
    description: str = ""
    role: str = "tx"
    ip: str = "127.0.0.1"
    port: int = 5081
    scripts: list = []
    intervals: list = []

class ScriptTemplateSave(BaseModel):
    name: str
    description: str = ""
    script: dict = {}
