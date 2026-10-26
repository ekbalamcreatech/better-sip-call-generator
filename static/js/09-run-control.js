// ═══════════════════════════════════════════════════════════════════════════════
// WORKSPACE START/STOP
// ═══════════════════════════════════════════════════════════════════════════════
async function startWorkspace() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  // Captured now, not re-read after the await below — activeWsId is a
  // global the user can change (by clicking another workspace) while
  // this function's fetch is still in flight. See the fetch's .then
  // block for why this matters.
  const startedWsId = activeWsId;

  // clear all displays immediately before anything else
  ['ws-sent','ws-completed','ws-failed','ws-active','ws-retrans','ws-mos'].forEach(id => {
    const el = document.getElementById(id); if(el) el.textContent='—';
  });
  ws.scripts.forEach(s => {
    ['sent','ok','fail','mos'].forEach(f => {
      const el = document.getElementById(`s${s.id}-${f}`); if(el) el.textContent='—';
    });
  });
  // clear RX stats explicitly if RX workspace
  if(ws.role === 'rx') {
    ['s1-sent','s1-ok','s1-fail'].forEach(id => {
      const el = document.getElementById(id); if(el) el.textContent='—';
    });
  }

  const logEl = document.getElementById('ws-log');
  if(logEl) { logEl.innerHTML = ''; logEl.dataset.logCount = '0'; }
  const tableEl = document.getElementById('quality-table');
  if(tableEl) tableEl.innerHTML = '<p style="color:#888;font-size:13px;padding:8px">No call data — run a test first</p>';
  const summEl = document.getElementById('quality-summary');
  if(summEl) summEl.textContent = '';
  const sipEl = document.getElementById('sipstats-content');
  if(sipEl) sipEl.innerHTML = '';
  const sipSumEl = document.getElementById('sipstats-summary');
  if(sipSumEl) sipSumEl.textContent = '';
  const ladderEl = document.getElementById('ladder-container-svg');
  if(ladderEl) ladderEl.innerHTML = '';
  const rawPanel = document.getElementById('ladder-raw-panel');
  if(rawPanel) rawPanel.style.display = 'none';

  // reset frontend workspace stats cache
  if(workspaces[activeWsId]) {
    workspaces[activeWsId].stats = {sent:0, completed:0, failed:0};
    workspaces[activeWsId].scripts.forEach(s => {
      s.stats = {sent:0, completed:0, failed:0};
      s.mos = null;
    });
  }

  addLog('Starting workspace...', 'info');

  // force stop any lingering backend state then re-init
  await fetch(`/workspaces/${activeWsId}/stop`, {method:'POST'});
  const initResp = await fetch(`/workspaces/${activeWsId}/init`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      workspace_id: activeWsId,
      label: ws.label,
      role: ws.role,
      ip: ws.ip,
      sip_port: ws.port,
      scripts: [],
      intervals: []
    })
  });

  if(!initResp.ok){
    const err = await initResp.json().catch(()=>({detail:'Failed to initialize workspace'}));
    addLog('Error: ' + (err.detail || err.error || 'Failed to initialize workspace'), 'err');
    alert(err.detail || err.error || 'Could not start — the server rejected this configuration.');
    return;
  }

  // reset frontend script stats after backend re-init
  const ws2 = workspaces[activeWsId];
  if(ws2) {
    ws2.stats = {sent:0, completed:0, failed:0};
    ws2.scripts.forEach(s => {
      s.stats = {sent:0, completed:0, failed:0};
      s.mos = null;
    });
    // also reset RX script directly
    const rxScript = ws2.scripts.find(s => s.id === 1);
    if(rxScript) {
      rxScript.stats = {sent:0, completed:0, failed:0};
    }
  }

  const payload = {
    workspace_id: activeWsId,
    scripts: ws.scripts.map(s => ({
      script_id: s.id,
      sut_name: s.sut_name,
      sut_ip: s.sut_ip,
      sut_port: s.sut_port,
      orig_ip: s.orig_ip,
      sip_port: s.sip_port,
      cps: s.cps,
      pct: s.pct,
      max_calls: s.max_calls,
      called_num: s.called || (s.number_pairs?.[0]?.called || ''),
      calling_num: s.calling || (s.number_pairs?.[0]?.calling || ''),
      number_pairs: s.number_pairs || [],
      audio_file: s.audio_file || 'reference.wav',
      audio_mode: s.audio_mode || 'plays',
      audio_value: s.audio_value || 2,
      codec: s.codec || 'PCMU',
      duration_ms: s.duration_ms || 60000,
      dtmf_enabled: s.dtmf_enabled || false,
      dtmf_digits: s.dtmf_digits || '',
      dtmf_gap_ms: s.dtmf_gap_ms || 100,
      enable_rtp: s.enable_rtp || false,
      rtp_loss_pct: s.rtp_loss_pct || 0,
      rtp_jitter_ms: s.rtp_jitter_ms || 0,
      rtp_burst_loss_ms: s.rtp_burst_loss_ms || 0,
      rtp_burst_loss_every_s: s.rtp_burst_loss_every_s || 0,
      stir_enabled: s.stir_enabled || false,
      stir_attest: s.stir_attest || 'A',
      auth_enabled: s.auth_enabled || false,
      auth_mode: s.auth_mode || 'single',
      auth_username: s.auth_username || '',
      auth_password: s.auth_password || '',
      xml: s.xml
    })),
    continuous: document.getElementById('ws-continuous')?.checked || false,
    intervals: ws.intervals.map(i => ({
      interval_id: i.id,
      duration_s: i.duration_s,
      label: i.label || '',
      script_cps: i.script_cps
    }))
  };

  try {
    const r = await fetch(`/workspaces/${activeWsId}/start`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json().catch(()=>({}));
    // Two different error shapes to handle: a 200-status "soft failure"
    // like {"error": "Workspace already running"}, AND a real HTTP error
    // status from a raised HTTPException (403 ownership violation, 409
    // conflict, etc.) which comes back as {"detail": "..."} — previously
    // only the first shape was checked, so the second was silently
    // treated as a successful start.
    if(!r.ok){ addLog('Error: ' + (d.detail || 'Failed to start'), 'err'); alert(d.detail || 'Failed to start workspace.'); return; }
    if(d.error){ addLog('Error: '+d.error, 'err'); return; }

    // reset all cached stats now that backend confirmed start
    ws.stats = {sent:0, completed:0, failed:0};
    ws.scriptStats = {};
    ws.scripts.forEach(s => {
      s.stats = {sent:0, completed:0, failed:0};
      s.mos = null;
    });
    ws.runStartTime = Date.now();
    ws.running = true;
    pollStartTime = Date.now();

    if(activeWsId === startedWsId) {
      document.getElementById('ws-start-btn').disabled = true;
      document.getElementById('ws-stop-btn').disabled = false;
      document.getElementById('ws-badge').className = 'badge running';
      document.getElementById('ws-badge').textContent = ws.role === 'rx' ? 'Listening' : 'Running';
      const portInputEl = document.getElementById('ws-port-input');
      if(portInputEl){ portInputEl.disabled = true; portInputEl.title = 'Stop the workspace to change the port'; }
      const ipSelEl = document.getElementById('ws-ip-select');
      if(ipSelEl){ ipSelEl.disabled = true; ipSelEl.title = 'Stop the workspace to change the IP'; }
    }
    renderSidePanel();
    startPolling(startedWsId);
    addLog('Workspace started', 'ok');
  } catch(e) {
    addLog('Start error: '+e.message, 'err');
  }
}

async function stopWorkspace() {
  if(!activeWsId) return;
  const stoppedWsId = activeWsId;
  clearInterval(pollTimer); pollTimer=null;
  const r = await fetch(`/workspaces/${stoppedWsId}/stop`, {method:'POST'});
  if(!r.ok){
    const err = await r.json().catch(()=>({detail:'Failed to stop workspace'}));
    addLog('Stop failed: ' + (err.detail || 'unknown error'), 'err');
    alert(err.detail || 'Failed to stop this workspace — it may still be running.');
    return;
  }
  workspaces[stoppedWsId].running = false;
  if(activeWsId === stoppedWsId){
    resetControls();
  }
  renderSidePanel(); // side panel shows every workspace's card, not just the active one
  addLog('Workspace stopped', 'err');
}

function resetControls() {
  clearInterval(pollTimer); pollTimer=null; pollStartTime=null;
  const startBtn = document.getElementById('ws-start-btn');
  const stopBtn  = document.getElementById('ws-stop-btn');
  const badge    = document.getElementById('ws-badge');
  if(startBtn) { startBtn.disabled=false; updateStartBtn(); }
  if(stopBtn)  stopBtn.disabled = true;
  if(badge)    { badge.className='badge idle'; badge.textContent='Idle'; }
  if(activeWsId) workspaces[activeWsId].running = false;
  const portInputEl = document.getElementById('ws-port-input');
  if(portInputEl){ portInputEl.disabled = false; portInputEl.title = ''; }
  const ipSelEl = document.getElementById('ws-ip-select');
  if(ipSelEl){ ipSelEl.disabled = false; ipSelEl.title = ''; }
  renderSidePanel();
  updateStartBtn();
}
