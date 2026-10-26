// ═══════════════════════════════════════════════════════════════════════════════
// AUDIO SETTINGS
// ═══════════════════════════════════════════════════════════════════════════════
function updateAudioScriptDropdown() {
  const sel = document.getElementById('audio-script-select');
  if(!sel || !activeWsId) return;
  const ws = workspaces[activeWsId];
  if(!ws.scripts.length) {
    sel.innerHTML = '<option value="">No scripts</option>';
    return;
  }
  sel.innerHTML = ws.scripts.map(s =>
    `<option value="${escapeHtml(s.id)}">Script ${escapeHtml(s.id)} — ${escapeHtml(s.sut_name||'UAS Listener')}</option>`
  ).join('');
  loadAudioSettings();
}

function updateSaveScriptDropdown() {
  const sel = document.getElementById('save-script-sel');
  if(!sel || !activeWsId) return;
  const ws = workspaces[activeWsId];
  sel.innerHTML = ws.scripts.map(s =>
    `<option value="${escapeHtml(s.id)}">Script ${escapeHtml(s.id)}</option>`
  ).join('');
}

function loadAudioSettings() {
  if(!activeWsId) return;
  const sel = document.getElementById('audio-script-select');
  if(!sel) return;
  const sid = parseInt(sel.value);
  const s = getScript(sid);
  if(!s) return;

  const fileSel = document.getElementById('audio-file-select');
  if(fileSel) fileSel.innerHTML = audioFiles.map(f =>
    `<option value="${escapeHtml(f.filename)}" ${f.filename===s.audio_file?'selected':''}>${escapeHtml(f.filename)} (${escapeHtml(f.duration_s)}s)</option>`
  ).join('');

  const modeSel = document.getElementById('audio-mode-select');
  if(modeSel) modeSel.value = s.audio_mode||'plays';
  const valInput = document.getElementById('audio-val-input');
  if(valInput) valInput.value = s.audio_value||2;
  const codecSel = document.getElementById('audio-codec');
  if(codecSel) codecSel.value = s.codec||'PCMU';
  const rtpCheck = document.getElementById('audio-rtp');
  if(rtpCheck) rtpCheck.checked = s.enable_rtp||false;
  const errPanel = document.getElementById('error-insertion-panel');
  if(errPanel) errPanel.style.display = s.enable_rtp ? 'block' : 'none';
  const lossInput = document.getElementById('rtp-loss-pct');
  if(lossInput) lossInput.value = s.rtp_loss_pct||0;
  const jitterInput = document.getElementById('rtp-jitter-ms');
  if(jitterInput) jitterInput.value = s.rtp_jitter_ms||0;
  const burstInput = document.getElementById('rtp-burst-ms');
  if(burstInput) burstInput.value = s.rtp_burst_loss_ms||0;
  const burstEveryInput = document.getElementById('rtp-burst-every');
  if(burstEveryInput) burstEveryInput.value = s.rtp_burst_loss_every_s||0;
  const dtmfCheck = document.getElementById('dtmf-enable');
  if(dtmfCheck) dtmfCheck.checked = s.dtmf_enabled||false;
  const dtmfDigs = document.getElementById('dtmf-digits');
  if(dtmfDigs) dtmfDigs.value = s.dtmf_digits||'';

  toggleAudioModeLabel();
  updateAudioDurationDisplay(sid);
}

function toggleAudioModeLabel() {
  const mode = document.getElementById('audio-mode-select')?.value;
  const lbl  = document.getElementById('audio-val-label');
  if(lbl) lbl.textContent = mode==='plays' ? 'Number of plays' : 'Duration (seconds)';
}

async function applyAudioSetting() {
  if(!activeWsId) return;
  const sel = document.getElementById('audio-script-select');
  if(!sel) return;
  const sid = parseInt(sel.value);
  const s = getScript(sid);
  if(!s) return;

  s.audio_file    = document.getElementById('audio-file-select')?.value || s.audio_file;
  s.audio_mode    = document.getElementById('audio-mode-select')?.value || s.audio_mode;
  s.audio_value   = parseInt(document.getElementById('audio-val-input')?.value)||s.audio_value;
  s.codec         = document.getElementById('audio-codec')?.value || s.codec;
  s.enable_rtp    = document.getElementById('audio-rtp')?.checked||false;
  s.rtp_loss_pct  = parseFloat(document.getElementById('rtp-loss-pct')?.value)||0;
  s.rtp_jitter_ms = parseInt(document.getElementById('rtp-jitter-ms')?.value)||0;
  s.rtp_burst_loss_ms = parseInt(document.getElementById('rtp-burst-ms')?.value)||0;
  s.rtp_burst_loss_every_s = parseInt(document.getElementById('rtp-burst-every')?.value)||0;

  const errPanel = document.getElementById('error-insertion-panel');
  if(errPanel) errPanel.style.display = s.enable_rtp ? 'block' : 'none';
  s.dtmf_enabled  = document.getElementById('dtmf-enable')?.checked||false;
  s.dtmf_digits   = document.getElementById('dtmf-digits')?.value||'';
  s.dtmf_gap_ms   = parseInt(document.getElementById('dtmf-gap')?.value)||100;

  await updateAudioDurationDisplay(sid);
  saveWorkspaces();
}

async function updateAudioDurationDisplay(sid) {
  const s = getScript(sid);
  if(!s) return;
  try {
    const r = await fetch('/audio/duration', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({filename:s.audio_file, mode:s.audio_mode, value:s.audio_value})
    });
    const d = await r.json();
    s.duration_ms = d.duration_ms;
    const disp = document.getElementById('audio-duration-display');
    if(disp) disp.textContent = d.display;
  } catch(e) {}
}
