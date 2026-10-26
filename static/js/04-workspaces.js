// ═══════════════════════════════════════════════════════════════════════════════
// WORKSPACE MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════
function validateNumberField(input, scriptId, field) {
  const val = input.value.trim();
  let error = '';

  if(val.includes('[') && !val.includes(']')) {
    error = 'Missing closing ]';
  } else if(val.includes(']') && !val.includes('[')) {
    error = 'Missing opening [';
  } else if(val.includes('[')) {
    // validate range format [0000-9999]
    const match = val.match(/\[(\d+)-(\d+)\]/);
    if(!match) {
      error = 'Invalid range — use [0000-9999] format';
    } else if(parseInt(match[1]) >= parseInt(match[2])) {
      error = 'Range start must be less than end';
    }
  }

  // show/hide error
  const errEl = document.getElementById(`s${scriptId}-${field}-err`);
  if(errEl) {
    errEl.textContent = error;
    errEl.style.display = error ? 'block' : 'none';
  }
  input.style.borderColor = error ? '#dc2626' : '#e5e5e5';

  if(!error) updateScriptField(scriptId, field, val);
}

async function addWorkspace() {
  if(Object.keys(workspaces).length >= 4) {
    alert('Maximum 4 workspaces'); return;
  }

  let id;
  try{
    const r = await fetch('/workspaces/claim', {method:'POST'});
    if(!r.ok){
      const err = await r.json().catch(()=>({detail:'No free workspace slots'}));
      alert(err.detail);
      return;
    }
    id = (await r.json()).workspace_id;
  }catch(e){
    alert('Could not reach the server to claim a workspace slot.');
    return;
  }

  const defaultIP = availableIPs[0] || '127.0.0.1';
  const defaultPort = 5080 + id;

  workspaces[id] = {
    id, label: `Workspace ${id}`,
    role: 'tx', ip: defaultIP, port: defaultPort,
    scripts: [], intervals: [],
    running: false, stats: {sent:0,completed:0,failed:0}
  };
  nextScriptId[id] = 1;
  nextIntervalId[id] = 1;

  // register the actual config with backend (claim already reserved the slot)
  const r = await fetch(`/workspaces/${id}/init`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({workspace_id:id, label:workspaces[id].label,
      role:'tx', ip:defaultIP, sip_port:defaultPort, scripts:[], intervals:[]})
  });
  if(!r.ok){
    const err = await r.json().catch(()=>({detail:'Failed to initialize workspace'}));
    alert(err.detail || err.error || 'Failed to initialize workspace');
    delete workspaces[id];
    return;
  }

  renderSidePanel();
  selectWorkspace(id);
  saveWorkspaces();
}

function selectWorkspace(id) {
  activeWsId = id;
  const ws = workspaces[id];
  if(!ws) return;

  // update active state in side panel
  document.querySelectorAll('.ws-card').forEach(c => c.classList.remove('active'));
  const card = document.getElementById(`ws-card-${id}`);
  if(card) card.classList.add('active');

  // show workspace content
  document.getElementById('no-ws-panel').style.display = 'none';
  document.getElementById('config-panel').style.display = 'none';
  document.getElementById('history-panel').style.display = 'none';
  document.getElementById('ws-content').style.display = 'flex';

  // populate header
  document.getElementById('ws-name-input').value = ws.label;
  document.getElementById('ws-role-select').value = ws.role;
  document.getElementById('ws-port-input').value = ws.port;
  updatePortFieldVisibility(ws.role);

  // populate IP dropdown
  const ipSel = document.getElementById('ws-ip-select');
  ipSel.innerHTML = availableIPs.map(ip =>
    `<option value="${escapeHtml(ip)}" ${ip===ws.ip?'selected':''}>${escapeHtml(ip)}</option>`
  ).join('');

  const portInput = document.getElementById('ws-port-input');
  if(portInput){
    portInput.disabled = !!ws.running;
    portInput.title = ws.running ? 'Stop the workspace to change the port' : '';
  }
  ipSel.disabled = !!ws.running;
  ipSel.title = ws.running ? 'Stop the workspace to change the IP' : '';

  // render scripts and intervals
  renderScripts();
  renderIntervals();
  updateAudioScriptDropdown();
  updateSaveScriptDropdown();
  refreshWorkspaceDisplay();
  populateScriptDropdowns();
  updateStatsLabels();

  const rawPanel = document.getElementById('ladder-raw-panel');
  if(rawPanel) rawPanel.style.display = 'none';
  const rawContent = document.getElementById('ladder-raw-content');
  if(rawContent) rawContent.innerHTML = '';

  if(activeContentTab === 'ladder') loadLadder();
  else if(activeContentTab === 'sipstats') loadSipStats();
  else if(activeContentTab === 'quality') loadCallQuality();
  // Was missing here — the Scenarios list is fetched per-role
  // (/scenarios/list/tx vs /scenarios/list/rx via loadScenarios()), but
  // switching workspaces while already sitting on this tab never
  // re-fetched, so a TX workspace's scenario list stayed on screen after
  // switching to an RX workspace (and vice versa) until the user clicked
  // away to another tab and back — which happened to trigger a fresh
  // fetch via showContentTab(), making it look like the bug "cleared
  // itself" rather than being fixed.
  else if(activeContentTab === 'scenarios') loadScenarios();

  // sync running state with backend
  fetch(`/workspaces/${id}/status`)
    .then(r=>r.json())
    .then(d=>{
      if(activeWsId !== id) return;
      if(!d.running && ws.running) {
        ws.running = false;
        resetControls();
      } else if(d.running) {
        ws.running = true;
        const startBtn = document.getElementById('ws-start-btn');
        const stopBtn  = document.getElementById('ws-stop-btn');
        const badge    = document.getElementById('ws-badge');
        if(startBtn) startBtn.disabled = true;
        if(stopBtn)  stopBtn.disabled = false;
        if(badge) { badge.className='badge running'; badge.textContent = ws.role==='rx' ? 'Listening' : 'Running'; }
        startPolling();
      }
      // Was missing here (present in the polling-loop fix, but not this
      // on-select/reload reconciliation path): if the workspace turns out
      // to actually be running, the port/IP fields need to be locked and
      // their VALUES synced from backend truth too — otherwise reloading
      // the page while viewing a genuinely-running workspace could leave
      // stale, editable fields that don't match what's actually bound.
      if(d.running && d.ip && d.port){
        ws.ip = d.ip; ws.port = d.port;
        const portInputEl = document.getElementById('ws-port-input');
        if(portInputEl){ portInputEl.value = d.port; portInputEl.disabled = true; portInputEl.title = 'Stop the workspace to change the port'; }
        const ipSelEl = document.getElementById('ws-ip-select');
        if(ipSelEl){ ipSelEl.value = d.ip; ipSelEl.disabled = true; ipSelEl.title = 'Stop the workspace to change the IP'; }
      }
    }).catch(()=>{});
}

async function deleteWorkspace(id) {
  if(!confirm(`Delete "${workspaces[id]?.label}"?`)) return;

  try {
    const r = await fetch(`/workspaces/${id}/release`, {method:'POST'});
    if(!r.ok && r.status !== 404){  // 404 = never existed server-side, fine to just clear locally
      const err = await r.json().catch(()=>({detail:'Failed to release workspace on the server'}));
      alert(err.detail || 'Could not release this workspace on the server — it may still be held. Not removing it locally.');
      return;
    }
  } catch(e) {
    alert('Could not reach the server to release this workspace. It may still be held — try again.');
    return;
  }

  delete workspaces[id];
  if(activeWsId === id) {
    activeWsId = null;
    document.getElementById('ws-content').style.display = 'none';
    document.getElementById('no-ws-panel').style.display = 'flex';
  }
  renderSidePanel();
  saveWorkspaces();
}

function updateWorkspaceLabel() {
  if(!activeWsId) return;
  workspaces[activeWsId].label = document.getElementById('ws-name-input').value;
  renderSidePanel();
  saveWorkspaces();
}

function updateWorkspaceRole() {
  if(!activeWsId) return;
  const role = document.getElementById('ws-role-select').value;
  workspaces[activeWsId].role = role;
  updatePortFieldVisibility(role);
  renderSidePanel();
  renderScripts();
  updateStartBtn();
  updateStatsLabels();
  saveWorkspaces();
}

function updatePortFieldVisibility(role) {
  const label = document.getElementById('ws-port-label');
  const input = document.getElementById('ws-port-input');
  if(!label || !input) return;
  if(role === 'rx') {
    label.style.display = 'inline';
    input.style.display = 'inline';
  } else {
    label.style.display = 'none';
    input.style.display = 'none';
  }
}

function updateWorkspaceIP() {
  if(!activeWsId) return;
  workspaces[activeWsId].ip = document.getElementById('ws-ip-select').value;
  // update RX banner
  const addr = document.getElementById('rx-listen-addr');
  if(addr) addr.textContent = `${workspaces[activeWsId].ip}:${workspaces[activeWsId].port}`;
  saveWorkspaces();
}

function updateWorkspacePort() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const port = parseInt(document.getElementById('ws-port-input').value);

  // check conflict
  let conflict = false;
  Object.entries(workspaces).forEach(([wsId, otherWs]) => {
    if(parseInt(wsId) === activeWsId) return;
    if(`${escapeHtml(ws.ip)}:${port}` === `${otherWs.ip}:${otherWs.port}`) conflict = true;
    otherWs.scripts.forEach(s => {
      if(`${escapeHtml(ws.ip)}:${port}` === `${s.orig_ip}:${s.sip_port}`) conflict = true;
    });
  });

  const input = document.getElementById('ws-port-input');
  if(input) {
    input.style.borderColor = conflict ? '#dc2626' : '#e5e5e5';
    input.title = conflict ? '⚠ Port conflict with another workspace' : '';
  }

  ws.port = port;
  const addr = document.getElementById('rx-listen-addr');
  if(addr) addr.textContent = `${escapeHtml(ws.ip)}:${escapeHtml(ws.port)}`;
  saveWorkspaces();
}

function renderSidePanel() {
  const container = document.getElementById('side-workspaces');
  const count = Object.keys(workspaces).length;
  document.getElementById('ws-count').textContent = `${count}/${MAX_WORKSPACES_UI}`;
  document.getElementById('add-ws-btn').disabled = count >= MAX_WORKSPACES_UI;

  container.innerHTML = Object.values(workspaces).map(ws => {
    const roleLabel = ws.role === 'tx' ? 'TX' : 'RX';
    const stats = ws.stats || {};
    const isRunning = ws.running;
    return `
    <div class="ws-card ${activeWsId===ws.id?'active':''}" id="ws-card-${escapeHtml(ws.id)}" onclick="selectWorkspace(${escapeHtml(ws.id)})">
      <div class="ws-card-header">
        <div class="ws-role-badge ${escapeHtml(ws.role)}">${escapeHtml(roleLabel)}</div>
        <span class="ws-label">${escapeHtml(ws.label)}</span>
        <div class="ws-status-dot ${isRunning?'running':''}" title="${isRunning?'Running':'Idle'}"></div>
      </div>
      <div class="ws-card-stats">
        <span>${ws.scripts.length} script${ws.scripts.length!==1?'s':''}</span>
        ${isRunning ? `<span style="color:#185FA5">▶ running</span>` : ''}
        ${stats.sent ? `<span>sent:${escapeHtml(stats.sent)}</span>` : ''}
      </div>
    </div>`;
  }).join('');
}
