// ═══════════════════════════════════════════════════════════════════════════════
// SCRIPTS
// ═══════════════════════════════════════════════════════════════════════════════
function addScript() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  if(ws.scripts.length >= 5) { alert('Maximum 5 scripts per workspace'); return; }

  // RX workspace only allows 1 script
  if(ws.role === 'rx' && ws.scripts.length >= 1) {
    alert('RX workspace only supports one UAS listener');
    return;
  }

  const id = nextScriptId[activeWsId]++;
  const defaultSUT = availableSUTs[0] || {name:'Local-UAS',ip:'127.0.0.1',port:'5060'};
  const baseSipPort = 5080 + (activeWsId * 10) + id;
  const sipPort = nextAvailablePort(baseSipPort, ws.ip);

  ws.scripts.push({
    id, sut_name:defaultSUT.name, sut_ip:defaultSUT.ip, sut_port:defaultSUT.port,
    orig_ip:ws.ip, sip_port:String(sipPort),
    pct:100,
    called:'', calling:'',
    number_pairs: [{calling:'', called:''}],
    audio_file:'reference.wav', audio_mode:'plays', audio_value:2,
    codec:'PCMU', duration_ms:60000,
    dtmf_enabled:false, dtmf_digits:'', dtmf_gap_ms:100,
    enable_rtp:false, stir_enabled:false, stir_attest:'A',
    auth_enabled:false, auth_mode:'single', auth_username:'', auth_password:'',
    xml:'', ready:false, desc:''
  });

  updatePercentages();
  renderScripts();
  renderIntervals(); // update interval script columns
  updateAudioScriptDropdown();
  updateSaveScriptDropdown();
  // Was missing — the side-panel workspace card's "N scripts" label
  // (renderSidePanel()) is only ever populated at initial workspace
  // creation/selection, so adding a script here left that count stale
  // at whatever it was before (e.g. "0 scripts" even after a script
  // genuinely exists and Intervals correctly shows it) until something
  // ELSE unrelated happened to call renderSidePanel() later.
  renderSidePanel();
  saveWorkspaces();
}

function removeScript(id) {
  if(!activeWsId) return;
  workspaces[activeWsId].scripts = workspaces[activeWsId].scripts.filter(s => s.id !== id);
  updatePercentages();
  renderScripts();
  renderIntervals();
  updateAudioScriptDropdown();
  updateSaveScriptDropdown();
  renderSidePanel(); // same staleness gap as addScript() — fixed alongside it
  saveWorkspaces();
}

function getScript(id) {
  if(!activeWsId) return null;
  return workspaces[activeWsId].scripts.find(s => s.id === id);
}

function updateScriptField(id, field, value) {
  const s = getScript(id);
  if(!s) return;
  s[field] = value;
  if(field === 'sut_name') {
    const sut = availableSUTs.find(x => x.name === value);
    if(sut) { s.sut_ip = sut.ip; s.sut_port = sut.port; }
    // update header label
    const headerLabel = document.querySelector(`#script-card-${id} .script-header span[style*="185FA5"]`);
    if(headerLabel) headerLabel.textContent = value;
    updateAudioScriptDropdown();
  }
  if(field === 'pct') {
    // update header % label
    const pctLabel = document.querySelector(`#script-card-${id} .script-header span[style*="888"]`);
    if(pctLabel) pctLabel.textContent = value+'%';
    updatePercentages();
  }
  if(['cps'].includes(field)) updatePercentages();
  saveWorkspaces();
}

function updatePercentages() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const totalPct = ws.scripts.reduce((sum,s) => sum + (parseInt(s.pct)||0), 0);

  const bar = document.getElementById('pct-bar');
  const lbl = document.getElementById('pct-label');
  if(bar) {
    bar.style.width = Math.min(totalPct,100)+'%';
    bar.style.background = totalPct===100 ? '#4ade80' : totalPct>100 ? '#f87171' : '#fbbf24';
  }
  if(lbl) {
    lbl.style.color = totalPct===100 ? '#16a34a' : '#f59e0b';
    lbl.textContent = totalPct+'%';
  }

  const countLbl = document.getElementById('script-count-label');
  if(countLbl) countLbl.textContent = `${ws.scripts.length}/5`;

  updateStartBtn();
}

function updateStatsLabels() {
  if(!activeWsId) return;
  const role = workspaces[activeWsId]?.role;
  const l1 = document.getElementById('ws-stat-label-1');
  const l2 = document.getElementById('ws-stat-label-2');
  if(l1) l1.textContent = role === 'rx' ? 'Received' : 'Sent';
  if(l2) l2.textContent = role === 'rx' ? 'Answered' : 'Completed';
}

function updateStartBtn() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const btn = document.getElementById('ws-start-btn');
  const addScriptBtn = document.getElementById('add-script-btn');

  if(!btn) return;

  // hide + Script button for RX
  if(addScriptBtn) {
    addScriptBtn.style.display = ws.role === 'rx' ? 'none' : 'inline';
  }

  if(ws.role === 'rx') {
    btn.disabled = ws.running;
    btn.textContent = '● Listen';
    return;
  }

  btn.textContent = '▶ Start';
  const totalPct = ws.scripts.reduce((sum,s) => sum + (parseInt(s.pct)||0), 0);
  const allReady = ws.scripts.length > 0 &&
                   ws.scripts.every(s => s.ready) &&
                   totalPct === 100 &&
                   ws.intervals.length > 0;
  btn.disabled = !allReady || ws.running;

  const lbl = document.getElementById('interval-progress-label');
  if(lbl && !ws.intervals.length && ws.scripts.length > 0) {
    lbl.textContent = '⚠ Add at least one interval to start';
    lbl.style.color = '#f59e0b';
  } else if(lbl) {
    lbl.textContent = '';
  }
}

function renderScripts() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const container = document.getElementById('script-slots');
  if(!container) return;
  // RX role — show simplified listener config
  if(ws.role === 'rx') {
    renderRXConfig();
    populateScriptDropdowns();
    updateAudioScriptDropdown();
    return;
  }

  container.innerHTML = ws.scripts.map(s => `
    <div class="script-card" id="script-card-${escapeHtml(s.id)}">
      <div class="script-header" onclick="toggleScript(${escapeHtml(s.id)})">
        <div class="script-num">${escapeHtml(s.id)}</div>
        <span style="font-size:13px;font-weight:500;flex:1">Script ${escapeHtml(s.id)}</span>
        <span style="font-size:12px;color:#185FA5">${escapeHtml(s.sut_name)}</span>
        <span style="font-size:11px;color:#888;margin-left:8px">${escapeHtml(s.pct)}%</span>
        <div style="width:7px;height:7px;border-radius:50%;background:${s.ready?'#4ade80':'#e5e5e5'};margin-left:8px" id="s${escapeHtml(s.id)}-dot" title="${s.ready?'Ready':'Needs scenario'}"></div>
        <button onclick="event.stopPropagation();saveScriptTemplateAs(${escapeHtml(s.id)})" title="Save this script as a reusable template" style="padding:2px 7px;font-size:11px;color:#185FA5;border:1px solid #b3d1f0;border-radius:4px;background:transparent;cursor:pointer;margin-left:6px">💾</button>
        <button onclick="event.stopPropagation();loadScriptTemplate(${escapeHtml(s.id)})" title="Load a saved script template into this slot" style="padding:2px 7px;font-size:11px;color:#555;border:1px solid #ddd;border-radius:4px;background:transparent;cursor:pointer">📂</button>
        <button onclick="event.stopPropagation();removeScript(${escapeHtml(s.id)})" style="padding:2px 7px;font-size:11px;color:#dc2626;border:1px solid #fca5a5;border-radius:4px;background:transparent;cursor:pointer">✕</button>
      </div>
      <div class="script-body" id="s${escapeHtml(s.id)}-body">
        <div class="field-grid">
          <div class="field">
            <label>SUT</label>
            <select onchange="updateScriptField(${escapeHtml(s.id)},'sut_name',this.value)" style="width:100%;border:1px solid #e5e5e5;border-radius:8px;padding:7px 10px;font-size:13px;background:#fafafa;outline:none">
              ${availableSUTs.map(sut=>`<option value="${escapeHtml(sut.name)}" ${sut.name===s.sut_name?'selected':''}>${escapeHtml(sut.name)} (${escapeHtml(sut.ip)}:${escapeHtml(sut.port)})</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label>Orig IP</label>
            <select onchange="updateScriptField(${escapeHtml(s.id)},'orig_ip',this.value)" style="width:100%;border:1px solid #e5e5e5;border-radius:8px;padding:7px 10px;font-size:13px;background:#fafafa;outline:none">
              ${availableIPs.map(ip=>`<option value="${escapeHtml(ip)}" ${ip===s.orig_ip?'selected':''}>${escapeHtml(ip)}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label>Src SIP Port</label>
            <input type="number" value="${escapeHtml(s.sip_port)}"
              onchange="updateScriptField(${escapeHtml(s.id)},'sip_port',this.value);checkAllPortConflicts()"
              style="width:100%;border:1px solid #e5e5e5;border-radius:8px;padding:7px 10px;font-size:13px;background:#fafafa;outline:none"
              id="s${escapeHtml(s.id)}-port-input"/>
            <span id="s${escapeHtml(s.id)}-port-conflict" style="display:none;color:#dc2626;font-size:11px">⚠ Port conflict</span>
          </div>
          <div class="field">
            <label>% Share</label>
            <input type="number" value="${escapeHtml(s.pct)}" min="0" max="100" onchange="updateScriptField(${escapeHtml(s.id)},'pct',parseInt(this.value)||0);updatePercentages()" style="width:100%;border:1px solid #e5e5e5;border-radius:8px;padding:7px 10px;font-size:13px;background:#fafafa;outline:none"/>
          </div>

          <!-- Number Plan -->
          <div style="margin-bottom:10px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
              <label style="font-size:11px;color:#888;font-weight:500;text-transform:uppercase;letter-spacing:.04em">Number Plan</label>
              <div style="display:flex;align-items:center;gap:8px">
                <span style="font-size:11px;color:#888" id="s${escapeHtml(s.id)}-total-combinations"></span>
                <button onclick="addNumberPair(${escapeHtml(s.id)})" style="padding:2px 8px;font-size:11px;border:1px solid #e5e5e5;border-radius:4px;background:#fff;cursor:pointer">+ Row</button>
              </div>
            </div>
            ${(s.auth_enabled && s.auth_mode==='per_row') || (s.stir_enabled && s.stir_mode==='per_row') ? `
            <div style="font-size:10px;color:#aaa;margin-bottom:4px">Per-row Auth/Attestation columns below come from the Authentication and STIR/SHAKEN sections further down this card.</div>` : ''}
            <table style="width:100%;border-collapse:collapse;font-size:12px">
              <thead>
                <tr style="background:#fafafa">
                  <th style="padding:4px 6px;text-align:left;font-size:10px;color:#888;font-weight:500;width:20px">#</th>
                  <th style="padding:4px 6px;text-align:left;font-size:10px;color:#888;font-weight:500">Calling</th>
                  <th style="padding:4px 6px;text-align:left;font-size:10px;color:#888;font-weight:500">Called</th>
                  ${s.auth_enabled && s.auth_mode==='per_row' ? `
                  <th style="padding:4px 6px;text-align:left;font-size:10px;color:#888;font-weight:500">Auth User</th>
                  <th style="padding:4px 6px;text-align:left;font-size:10px;color:#888;font-weight:500">Auth Pass</th>` : ''}
                  ${s.stir_enabled && s.stir_mode==='per_row' ? `
                  <th style="padding:4px 6px;text-align:left;font-size:10px;color:#888;font-weight:500">Attest</th>` : ''}
                 <th style="width:24px"></th>
                </tr>
              </thead>
              <tbody id="s${escapeHtml(s.id)}-number-rows">
                ${(s.number_pairs||[{calling:s.calling||'',called:s.called||''}]).map((pair,idx) => `
                <tr style="border-bottom:1px solid #f5f5f5">
                  <td style="padding:3px 6px;color:#aaa;font-size:11px">${escapeHtml(idx+1)}</td>
                  <td style="padding:3px 6px">
                    <input value="${escapeHtml(pair.calling||'')}"
                      oninput="updateNumberPair(${escapeHtml(s.id)},${escapeHtml(idx)},'calling',this.value)"
                      placeholder="5550001 or 555[0001-0100]"
                      style="width:100%;border:1px solid #e5e5e5;border-radius:4px;padding:4px 6px;font-size:12px;outline:none"/>
                    <span id="s${escapeHtml(s.id)}-pair${escapeHtml(idx)}-calling-err" style="display:none;color:#dc2626;font-size:10px"></span>
                  </td>
                  <td style="padding:3px 6px">
                    <input value="${escapeHtml(pair.called||'')}"
                      oninput="updateNumberPair(${escapeHtml(s.id)},${escapeHtml(idx)},'called',this.value)"
                      placeholder="9721234[001-100] or 972@carrier.com"
                      style="width:100%;border:1px solid #e5e5e5;border-radius:4px;padding:4px 6px;font-size:12px;outline:none"/>
                    <span id="s${escapeHtml(s.id)}-pair${escapeHtml(idx)}-called-err" style="display:none;color:#dc2626;font-size:10px"></span>
                  </td>
                  ${s.auth_enabled && s.auth_mode==='per_row' ? `
                  <td style="padding:3px 6px">
                    <input value="${escapeHtml(pair.auth_username||'')}"
                      oninput="updateNumberPair(${escapeHtml(s.id)},${escapeHtml(idx)},'auth_username',this.value)"
                      placeholder="username"
                      style="width:100%;border:1px solid #e5e5e5;border-radius:4px;padding:4px 6px;font-size:12px;outline:none"/>
                  </td>
                  <td style="padding:3px 6px">
                    <input value="${escapeHtml(pair.auth_password||'')}" type="password"
                      oninput="updateNumberPair(${escapeHtml(s.id)},${escapeHtml(idx)},'auth_password',this.value)"
                      placeholder="password"
                      style="width:100%;border:1px solid #e5e5e5;border-radius:4px;padding:4px 6px;font-size:12px;outline:none"/>
                  </td>` : ''}
                  ${s.stir_enabled && s.stir_mode==='per_row' ? `
                  <td style="padding:3px 6px">
                    <select onchange="updateNumberPair(${escapeHtml(s.id)},${escapeHtml(idx)},'stir_attest',this.value)" style="width:100%;border:1px solid #e5e5e5;border-radius:4px;padding:4px 2px;font-size:11px;outline:none">
                      <option value="" ${!pair.stir_attest?'selected':''}>default (${escapeHtml(s.stir_attest)})</option>
                      <option value="A" ${pair.stir_attest==='A'?'selected':''}>A</option>
                      <option value="B" ${pair.stir_attest==='B'?'selected':''}>B</option>
                      <option value="C" ${pair.stir_attest==='C'?'selected':''}>C</option>
                    </select>
                  </td>` : ''}
                  <td style="padding:3px 6px">
                    ${(s.number_pairs||[]).length > 1 ?
                      `<button onclick="removeNumberPair(${escapeHtml(s.id)},${escapeHtml(idx)})" style="padding:1px 5px;font-size:10px;color:#dc2626;border:1px solid #fca5a5;border-radius:3px;background:transparent;cursor:pointer">✕</button>` : ''}
                  </td>
                </tr>`).join('')}
              </tbody>
           </table>
          </div>

          <!-- Authentication -->
          <div class="field" style="margin-bottom:10px">
            <label>Authentication</label>
            <div style="display:flex;align-items:center;gap:6px;margin-top:6px">
              <input type="checkbox" ${s.auth_enabled?'checked':''} onchange="toggleAuthEnabled(${escapeHtml(s.id)},this.checked)" style="width:15px;height:15px"/>
              <span style="font-size:12px;color:#333">Enable (401/407 challenge-response)</span>
            </div>
            ${s.auth_enabled ? `
            <div style="display:flex;gap:12px;margin-top:8px;padding-left:21px">
              <label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer">
                <input type="radio" name="auth-mode-${escapeHtml(s.id)}" ${s.auth_mode!=='per_row'?'checked':''} onchange="updateScriptField(${escapeHtml(s.id)},'auth_mode','single');renderScripts()"/> Single (all UAs)
              </label>
              <label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer">
                <input type="radio" name="auth-mode-${escapeHtml(s.id)}" ${s.auth_mode==='per_row'?'checked':''} onchange="updateScriptField(${escapeHtml(s.id)},'auth_mode','per_row');renderScripts()"/> Per-Row
              </label>
            </div>
            ${s.auth_mode!=='per_row' ? `
            <div style="display:flex;gap:8px;margin-top:6px;padding-left:21px">
              <input placeholder="Username" value="${escapeHtml(s.auth_username||'')}" oninput="updateScriptField(${escapeHtml(s.id)},'auth_username',this.value)" style="flex:1;border:1px solid #e5e5e5;border-radius:6px;padding:5px 8px;font-size:12px;outline:none"/>
              <input placeholder="Password" type="password" value="${escapeHtml(s.auth_password||'')}" oninput="updateScriptField(${escapeHtml(s.id)},'auth_password',this.value)" style="flex:1;border:1px solid #e5e5e5;border-radius:6px;padding:5px 8px;font-size:12px;outline:none"/>
            </div>` : `
            <div style="font-size:11px;color:#888;margin-top:4px;padding-left:21px">Set Auth User/Pass per row in the Number Plan table above ↑</div>`}
            ` : ''}
          </div>

          <div class="field">
            <label>STIR/SHAKEN</label>
            <div style="display:flex;align-items:center;gap:6px;margin-top:6px">
              <input type="checkbox" ${s.stir_enabled?'checked':''} onchange="updateScriptField(${escapeHtml(s.id)},'stir_enabled',this.checked);renderScripts()" style="width:15px;height:15px"/>
              <span style="font-size:12px;color:#333">Enable (per-call PASSporT / Identity header)</span>
            </div>
            ${s.stir_enabled ? `
            <div style="display:flex;gap:12px;margin-top:8px;padding-left:21px">
              <label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer">
                <input type="radio" name="stir-mode-${escapeHtml(s.id)}" ${s.stir_mode!=='per_row'?'checked':''} onchange="updateScriptField(${escapeHtml(s.id)},'stir_mode','single');renderScripts()"/> Single (all calls)
              </label>
              <label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer">
                <input type="radio" name="stir-mode-${escapeHtml(s.id)}" ${s.stir_mode==='per_row'?'checked':''} onchange="updateScriptField(${escapeHtml(s.id)},'stir_mode','per_row');renderScripts()"/> Per-Row
              </label>
            </div>
            ${s.stir_mode!=='per_row' ? `
            <div style="display:flex;gap:8px;margin-top:6px;padding-left:21px;align-items:center">
              <span style="font-size:12px;color:#888">Attestation:</span>
              <select onchange="updateScriptField(${escapeHtml(s.id)},'stir_attest',this.value)" style="border:1px solid #e5e5e5;border-radius:6px;padding:4px 8px;font-size:12px;background:#fff;outline:none">
                <option value="A" ${s.stir_attest==='A'?'selected':''}>A — Full Attestation</option>
                <option value="B" ${s.stir_attest==='B'?'selected':''}>B — Partial Attestation</option>
                <option value="C" ${s.stir_attest==='C'?'selected':''}>C — Gateway Attestation</option>
              </select>
            </div>` : `
            <div style="font-size:11px;color:#888;margin-top:4px;padding-left:21px">Set Attestation per row in the Number Plan table above ↑ (blank = use this script's default)</div>`}
            <div style="font-size:10px;color:#aaa;margin-top:6px;padding-left:21px">Note: this generates a fresh, correctly-scoped token per call — not the same token reused across every call in a range/volume test.</div>
            ` : ''}
          </div>
        </div>

        <div class="field" style="margin-bottom:10px">
          <label>Describe this script</label>
          <textarea id="s${escapeHtml(s.id)}-desc" rows="2" placeholder="e.g. Basic SIP call at 1 CPS, 30 seconds, UAC hangs up">${escapeHtml(s.desc||'')}</textarea>
        </div>

        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
          <button id="s${escapeHtml(s.id)}-gen-btn" onclick="generateScript(${escapeHtml(s.id)})" style="padding:6px 14px;font-size:12px;background:#185FA5;color:#fff;border:none;border-radius:6px;cursor:pointer">✨ Generate</button>
          <button id="s${escapeHtml(s.id)}-view-btn" onclick="viewScriptXml(${escapeHtml(s.id)})" ${!s.xml?'disabled':''} style="padding:6px 12px;font-size:12px;border:1px solid #e5e5e5;border-radius:6px;background:#fff;cursor:pointer">View XML</button>
          <button id="s${escapeHtml(s.id)}-save-btn" onclick="saveScriptScenario(${escapeHtml(s.id)})" ${!s.xml?'disabled':''} style="padding:6px 12px;font-size:12px;border:1px solid #e5e5e5;border-radius:6px;background:#fff;cursor:pointer">💾 Save As...</button>
          <button onclick="loadScriptScenario(${escapeHtml(s.id)})" style="padding:6px 12px;font-size:12px;border:1px solid #e5e5e5;border-radius:6px;background:#fff;cursor:pointer">Load saved</button>
          <span id="s${escapeHtml(s.id)}-ready" style="font-size:12px">${s.ready?'<span style="color:#16a34a">✓ Ready</span>':'<span style="color:#aaa">needs scenario</span>'}</span>
          <span style="font-size:11px;color:#888;margin-left:auto">
            ${(s.duration_ms/1000).toFixed(1)}s | <span onclick="showContentTab('audio')" style="cursor:pointer;color:#185FA5">⚙ Audio</span>
          </span>
        </div>

        <div id="s${escapeHtml(s.id)}-xml-panel" style="display:none;margin-bottom:8px">
          <button onclick="copyEl('s${escapeHtml(s.id)}-xml')" style="padding:3px 8px;font-size:11px;float:right">Copy</button>
          <pre id="s${escapeHtml(s.id)}-xml" style="background:#fafafa;border:1px solid #e5e5e5;border-radius:8px;padding:10px;font-size:11px;max-height:180px;overflow:auto;margin:0;white-space:pre-wrap">${escapeHtml(s.xml||'')}</pre>
        </div>

        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
          <div class="stat-card"><div class="label">Sent</div><div class="value" id="s${escapeHtml(s.id)}-sent" style="font-size:16px">—</div></div>
          <div class="stat-card"><div class="label">Completed</div><div class="value ok" id="s${escapeHtml(s.id)}-ok" style="font-size:16px">—</div></div>
          <div class="stat-card"><div class="label">Failed</div><div class="value fail" id="s${escapeHtml(s.id)}-fail" style="font-size:16px">—</div></div>
          <div class="stat-card"><div class="label">MOS</div><div class="value mos" id="s${escapeHtml(s.id)}-mos" style="font-size:16px">—</div></div>
        </div>
      </div>
    </div>`).join('');

  updatePercentages();
  populateScriptDropdowns();

}
