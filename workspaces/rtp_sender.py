"""Optional RTP media senders (TX and RX)."""
import os
from models import ScriptConfig

from workspaces.state import log_workspace
from config import AUDIO_DIR

def _start_rtp_sender(workspace_id: int, script: ScriptConfig):
    """Start RTP sender thread for a script."""
    import threading, time
    from engines.audio import prepare_codec_file
    audio_path = os.path.join(AUDIO_DIR, os.path.basename(script.audio_file))
    local_rtp_port = 6000
    duration_s = (script.duration_ms or 60000) / 1000

    def _sender():
        from engines.sipp import get_remote_rtp_port, get_latest_messages_log

        remote_port = None
        waited = 0.0
        poll_interval = 0.25
        max_wait_s = max(duration_s + 10, 20)  # generous — covers early-media hold periods
        while waited < max_wait_s:
            log = get_latest_messages_log("uac", workspace_id, script.script_id)
            remote_port = get_remote_rtp_port(log)
            if remote_port:
                break
            time.sleep(poll_interval)
            waited += poll_interval

        if not remote_port:
            log_workspace(workspace_id,
                f"Script {script.script_id} RTP aborted — no SDP-bearing response "
                f"(183/200) seen within {max_wait_s:.0f}s", "err")
            return

        try:
            codec_file = prepare_codec_file(audio_path, script.codec or 'PCMU')
            from engines.rtp import send_rtp, PCMU_PAYLOAD_TYPE, G729_PAYLOAD_TYPE, PCMA_PAYLOAD_TYPE
            pt_map = {'PCMU': PCMU_PAYLOAD_TYPE, 'G729': G729_PAYLOAD_TYPE, 'PCMA': PCMA_PAYLOAD_TYPE}
            pt = pt_map.get(script.codec or 'PCMU', PCMU_PAYLOAD_TYPE)
            send_rtp(script.orig_ip, local_rtp_port, script.sut_ip, remote_port, codec_file, duration_s, payload_type=pt,
                     loss_pct=getattr(script, 'rtp_loss_pct', 0) or 0,
                     jitter_ms=getattr(script, 'rtp_jitter_ms', 0) or 0,
                     burst_loss_ms=getattr(script, 'rtp_burst_loss_ms', 0) or 0,
                     burst_loss_every_s=getattr(script, 'rtp_burst_loss_every_s', 0) or 0)
            log_workspace(workspace_id, f"Script {script.script_id} RTP complete", "ok")
        except Exception as e:
            log_workspace(workspace_id, f"Script {script.script_id} RTP error: {e}", "err")

    threading.Thread(target=_sender, daemon=True).start()

def _start_rtp_sender_rx(workspace_id: int, script: ScriptConfig, term_ip: str):
    """
    RX/UAS counterpart to _start_rtp_sender(). This has never existed
    before — RX has never sent any RTP of its own, at all, which is why
    no audio ever flowed in the RX->caller direction (the RX Audio-tab
    Error Insertion panel has always been visually present but inert;
    this is the first real wiring of an actual sender behind it).

    Scope, stated honestly: this targets the FIRST call the UAS process
    handles, one-shot — it polls the live messages log for the caller's
    offered SDP (from the INVITE it received) and sends exactly one RTP
    stream to that target. This is sufficient for manual/single-call
    testing (e.g. validating early media, or any 1-call MOS check) but
    is NOT the full per-call, multi-concurrent-call dispatcher a real
    UAS load-test target would need — that remains its own larger,
    already-scoped effort (RX-side Error Insertion, v2.4), since SIPp's
    UAS process handles many calls over its lifetime, each negotiating
    its own port, and a single one-shot sender can only ever serve one
    of them correctly.
    """
    import threading, time
    from engines.audio import prepare_codec_file
    from engines.sipp import get_caller_offered_rtp_target, get_latest_messages_log

    if not getattr(script, 'enable_rtp', False):
        return

    audio_path = os.path.join(AUDIO_DIR, os.path.basename(script.audio_file))
    local_rtp_port = 6002  # distinct from TX's 6000 so both can run on the same box
    duration_s = (script.duration_ms or 60000) / 1000

    def _sender():
        target = None
        waited = 0.0
        poll_interval = 0.25
        max_wait_s = max(duration_s + 10, 20)
        while waited < max_wait_s:
            log = get_latest_messages_log("uas", workspace_id)
            target = get_caller_offered_rtp_target(log)
            if target:
                break
            time.sleep(poll_interval)
            waited += poll_interval

        if not target:
            log_workspace(workspace_id,
                f"RX RTP aborted — no caller SDP (INVITE) seen within {max_wait_s:.0f}s", "err")
            return

        remote_ip, remote_port = target
        try:
            codec_file = prepare_codec_file(audio_path, script.codec or 'PCMU')
            from engines.rtp import send_rtp, PCMU_PAYLOAD_TYPE, G729_PAYLOAD_TYPE, PCMA_PAYLOAD_TYPE
            pt_map = {'PCMU': PCMU_PAYLOAD_TYPE, 'G729': G729_PAYLOAD_TYPE, 'PCMA': PCMA_PAYLOAD_TYPE}
            pt = pt_map.get(script.codec or 'PCMU', PCMU_PAYLOAD_TYPE)
            send_rtp(term_ip, local_rtp_port, remote_ip, remote_port, codec_file, duration_s, payload_type=pt,
                     loss_pct=getattr(script, 'rtp_loss_pct', 0) or 0,
                     jitter_ms=getattr(script, 'rtp_jitter_ms', 0) or 0,
                     burst_loss_ms=getattr(script, 'rtp_burst_loss_ms', 0) or 0,
                     burst_loss_every_s=getattr(script, 'rtp_burst_loss_every_s', 0) or 0)
            log_workspace(workspace_id, "RX RTP complete", "ok")
        except Exception as e:
            log_workspace(workspace_id, f"RX RTP error: {e}", "err")

    threading.Thread(target=_sender, daemon=True).start()
