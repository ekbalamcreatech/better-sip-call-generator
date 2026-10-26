// ═══════════════════════════════════════════════════════════════════════════════
// PERSISTENCE
// ═══════════════════════════════════════════════════════════════════════════════
// ─── Script Templates (save/load a WHOLE script — SUT, numbers, codec,
// DTMF, RTP impairment, auth, STIR, XML — as one named unit). The middle
// layer between raw XML (Scenarios, which only saves the XML string) and
// a whole Workspace Template above — pulls a fully-configured script
// straight into any slot, not just its XML into an empty one.
async function saveScriptTemplateAs(scriptId) {
  const s = getScript(scriptId);
  if(!s) return;
  const name = prompt('Save this script as:', s.sut_name ? `${escapeHtml(s.sut_name)} script` : '');
  if(!name) return;
  const description = prompt('Description (optional):', '') || '';

  try {
    const r = await fetch('/script-templates/save', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ name, description, script: s })
    });
    if(r.ok) {
      addLog(`Script saved as template "${name}"`, 'ok');
    } else {
      const err = await r.json().catch(()=>({detail:'Failed to save'}));
      alert(err.detail || 'Failed to save script template.');
    }
  } catch(e) {
    alert('Could not reach the server to save this script template.');
  }
}

async function loadScriptTemplate(scriptId) {
  const s = getScript(scriptId);
  if(!s) return;
  try {
    const r = await fetch('/script-templates/list');
    const d = await r.json();
    const templates = d.templates || [];
    if(!templates.length){ alert('No saved script templates yet — use the 💾 button first.'); return; }

    const listText = templates.map(t =>
      `${t.name} (${t.sut_name||'no SUT'}, ${t.codec}, by ${t.saved_by||'?'})`
    ).join('\n');
    const name = prompt('Enter the exact template name to load:\n\n' + listText);
    if(!name) return;
    const found = templates.find(t => t.name === name);
    if(!found){ alert('No template with that exact name.'); return; }

    if(!confirm(`Load "${found.name}" into Script ${scriptId}? This replaces its current settings.`)) return;

    const lr = await fetch(`/script-templates/load/${found.filename}`);
    if(!lr.ok){ alert('Failed to load that template.'); return; }
    const data = await lr.json();

    const loadedScript = data.script || {};
    Object.keys(loadedScript).forEach(key => {
      if(key !== 'id') s[key] = loadedScript[key];  // keep this slot's own id
    });

    renderScripts();
    revealScriptXml(scriptId);
    updateAudioScriptDropdown();
    updateSaveScriptDropdown();
    saveWorkspaces();
    addLog(`Loaded script template "${found.name}" into Script ${scriptId}`, 'ok');
  } catch(e) {
    addLog('Load script template error: ' + e.message, 'err');
  }
}

// ─── Workspace Templates (save/load a WHOLE workspace as one named unit) ───
// The autosave (saveWorkspaces() below) silently keeps one workspace SLOT
// up to date in the background. This is different and complementary: an
// explicit, named library of full workspace configurations — role, IP,
// port, every script (with its generated XML), every interval — that you
// can pull into ANY slot whenever you want, independent of whatever's
// currently sitting in your 4 live slots. Shared/global library, same as
// the existing Scenarios feature this mirrors.
async function saveWorkspaceTemplateAs() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const name = prompt('Save this workspace as:', ws.label || '');
  if(!name) return;
  const description = prompt('Description (optional):', '') || '';

  try {
    const r = await fetch('/workspace-templates/save', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        name, description, role: ws.role, ip: ws.ip, port: ws.port,
        scripts: ws.scripts, intervals: ws.intervals
      })
    });
    if(r.ok) {
      addLog(`Workspace saved as "${name}"`, 'ok');
    } else {
      const err = await r.json().catch(()=>({detail:'Failed to save'}));
      alert(err.detail || 'Failed to save workspace template.');
    }
  } catch(e) {
    alert('Could not reach the server to save this workspace template.');
  }
}

async function loadWorkspaceTemplate() {
  if(!activeWsId) return;
  try {
    const r = await fetch('/workspace-templates/list');
    const d = await r.json();
    const templates = d.templates || [];
    if(!templates.length){ alert('No saved workspace templates yet — use "Save As..." first.'); return; }

    const listText = templates.map(t =>
      `${t.name} (${t.role.toUpperCase()}, ${t.script_count} script(s), ${t.interval_count} interval(s), by ${t.saved_by||'?'})`
    ).join('\n');
    const name = prompt('Enter the exact template name to load:\n\n' + listText);
    if(!name) return;
    const found = templates.find(t => t.name === name);
    if(!found){ alert('No template with that exact name.'); return; }

    if(!confirm(`Load "${found.name}" into this workspace? This replaces the current scripts and intervals here.`)) return;

    const lr = await fetch(`/workspace-templates/load/${found.filename}`);
    if(!lr.ok){ alert('Failed to load that template.'); return; }
    const data = await lr.json();

    const ws = workspaces[activeWsId];
    ws.role = data.role;
    ws.ip = data.ip;
    ws.port = data.port;
    ws.scripts = data.scripts || [];
    ws.intervals = data.intervals || [];
    nextScriptId[activeWsId] = ws.scripts.length > 0 ? Math.max(...ws.scripts.map(s => s.id)) + 1 : 1;
    nextIntervalId[activeWsId] = ws.intervals.length > 0 ? Math.max(...ws.intervals.map(i => i.id)) + 1 : 1;

    selectWorkspace(activeWsId);  // full re-render, reuses all existing rendering logic
    renderSidePanel();  // Was missing — selectWorkspace() only toggles the .active
                         // class on existing sidebar cards, it doesn't regenerate
                         // them, so a role change here (tx->rx) never updated the
                         // sidebar's TX/RX badge even though the main content area
                         // correctly showed RX. Confirmed: updateWorkspaceRole()
                         // (the normal dropdown handler) already calls this — this
                         // was a gap specific to the new load-template path, not a
                         // pre-existing bug.
    saveWorkspaces();
    addLog(`Loaded workspace template "${found.name}"`, 'ok');
  } catch(e) {
    addLog('Load workspace template error: ' + e.message, 'err');
  }
}

async function saveWorkspaces() {
  try {
    await fetch('/workspaces/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        workspaces: Object.values(workspaces).map(ws => ({
          id: ws.id,
          label: ws.label,
          role: ws.role,
          ip: ws.ip,
          port: ws.port,
          scripts: ws.scripts,
          intervals: ws.intervals,
          // Was missing entirely — per-script stats already survive
          // reload via the scripts array above, but the workspace-level
          // aggregate (what AI Diagnosis actually reads) didn't. A
          // completed test's real numbers were being lost the moment
          // the page reloaded or the workspace was re-selected, even
          // with the during-run sync fix in place.
          stats: ws.stats
        })),
        nextWsId: nextWsId
      })
    });
  } catch(e) {
    console.error('Save error:', e);
  }
}

async function loadSavedWorkspaces() {
  try {
    const r = await fetch('/workspaces/saved');
    const d = await r.json();

    // restore whatever was locally cached (may be empty — that's fine,
    // reconciliation below still runs regardless)
    (d.workspaces || []).forEach(ws => {
      workspaces[ws.id] = {
        ...ws,
        running: false,
        stats: ws.stats || {sent:0, completed:0, failed:0},
        scriptStats: {}
      };
      nextScriptId[ws.id] = ws.scripts.length > 0
        ? Math.max(...ws.scripts.map(s => s.id)) + 1
        : 1;
      nextIntervalId[ws.id] = ws.intervals.length > 0
        ? Math.max(...ws.intervals.map(i => i.id)) + 1
        : 1;
    });
    if(d.nextWsId) nextWsId = d.nextWsId;

    try {
      // Determined here directly rather than trusting the `currentUsername`
      // global — loadAuthStatus() isn't awaited in init(), so relying on
      // that global risks a race where it hasn't been set yet.
      const authResp = await fetch('/auth/status');
      const authData = await authResp.json();
      const myUsername = authData.username;

      const liveResp = await fetch('/workspaces');
      const live = await liveResp.json();
      // For admin, GET /workspaces intentionally returns
      // EVERY workspace (including other users' AND released, unowned
      // ones) for oversight purposes — that's correct for the Admin
      // Workspaces panel, but wrong here: this side panel should only
      // ever reflect workspaces *I* actually own, same as a plain 'user'
      // account sees. Without this filter, an admin who released all
      // their workspaces would see them reappear on reload, since
      // every released slot is still present in this response with
      // owner:null and was being adopted unconditionally.
      const liveIds = new Set(
        Object.entries(live)
          .filter(([wid, s]) => s.owner === myUsername)
          .map(([wid]) => Number(wid))
      );

      Object.keys(workspaces).map(Number).forEach(id => {
        if(!liveIds.has(id)) {
          delete workspaces[id];
          delete nextScriptId[id];
          delete nextIntervalId[id];
        }
      });

      liveIds.forEach(id => {
        if(!workspaces[id]) {
          const status = live[id] ?? live[String(id)];
          workspaces[id] = {
            id, label: status.label, role: status.role, ip: status.ip, port: status.port,
            scripts: [], intervals: [],
            running: status.running, stats: status.totals || {sent:0,completed:0,failed:0}, scriptStats: {}
          };
          nextScriptId[id] = 1;
          nextIntervalId[id] = 1;
        }
      });
    } catch(e) {
      // Network hiccup reaching the backend — fall back to whatever the
      // local cache had rather than clearing everything on a fluke.
    }

    renderSidePanel();
    saveWorkspaces();  // persist the reconciled list, not the stale one

    const remainingIds = Object.keys(workspaces).map(Number);
    if(remainingIds.length) selectWorkspace(remainingIds[0]);

    return remainingIds.length > 0;
  } catch(e) {
    return false;
  }
}

// ─── NUMBER PLAN ─────────────────────────────────────────────────────────────
function toggleAuthEnabled(scriptId, checked) {
  const s = getScript(scriptId);
  if(!s) return;
  s.auth_enabled = checked;
  if(checked && !s.auth_mode) s.auth_mode = 'single';
  renderScripts();
  saveWorkspaces();
}

function addNumberPair(scriptId) {
  const s = getScript(scriptId);
  if(!s) return;
  if(!s.number_pairs) s.number_pairs = [{calling: s.calling||'', called: s.called||'', auth_username:'', auth_password:''}];
  s.number_pairs.push({calling:'', called:'', auth_username:'', auth_password:''});
  renderScripts();
  updateTotalCombinations(scriptId);
  saveWorkspaces();
}

function removeNumberPair(scriptId, idx) {
  const s = getScript(scriptId);
  if(!s || !s.number_pairs || s.number_pairs.length <= 1) return;
  s.number_pairs.splice(idx, 1);
  renderScripts();
  updateTotalCombinations(scriptId);
  saveWorkspaces();
}

function updateNumberPair(scriptId, idx, field, value) {
  const s = getScript(scriptId);
  if(!s) return;
  if(!s.number_pairs) s.number_pairs = [{calling: s.calling||'', called: s.called||''}];
  if(!s.number_pairs[idx]) s.number_pairs[idx] = {calling:'', called:''};
  s.number_pairs[idx][field] = value;

  // validate
  const errEl = document.getElementById(`s${scriptId}-pair${idx}-${field}-err`);
  if(errEl) {
    let error = '';
    if(value.includes('[') && !value.includes(']')) error = 'Missing ]';
    else if(value.includes(']') && !value.includes('[')) error = 'Missing [';
    else if(value.includes('[')) {
      const match = value.match(/\[(\d+)-(\d+)\]/);
      if(!match) error = 'Invalid range';
      else if(parseInt(match[1]) >= parseInt(match[2])) error = 'Start must be < end';
    }
    errEl.textContent = error;
    errEl.style.display = error ? 'block' : 'none';
    errEl.previousElementSibling.style.borderColor = error ? '#dc2626' : '#e5e5e5';
  }

  // sync to legacy fields for backward compat
  if(idx === 0) {
    s.calling = s.number_pairs[0].calling;
    s.called  = s.number_pairs[0].called;
  }

  updateTotalCombinations(scriptId);
  saveWorkspaces();
}

function updateTotalCombinations(scriptId) {
  const s = getScript(scriptId);
  if(!s) return;
  const pairs = s.number_pairs || [{calling: s.calling||'', called: s.called||''}];
  let total = 0;
  pairs.forEach(pair => {
    const callingMatch = pair.calling.match(/\[(\d+)-(\d+)\]/);
    const calledMatch  = pair.called.match(/\[(\d+)-(\d+)\]/);
    const callingCount = callingMatch ? (parseInt(callingMatch[2]) - parseInt(callingMatch[1]) + 1) : 1;
    const calledCount  = calledMatch  ? (parseInt(calledMatch[2])  - parseInt(calledMatch[1])  + 1) : 1;
    total += Math.max(callingCount, calledCount);
  });
  const el = document.getElementById(`s${scriptId}-total-combinations`);
  if(el) el.textContent = total > 1 ? `${total} combinations` : '';
}
