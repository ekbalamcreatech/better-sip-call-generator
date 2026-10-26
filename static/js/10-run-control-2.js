function setExtra(t) {
  const a = document.getElementById('ws-active'), r = document.getElementById('ws-retrans');
  if(a) a.textContent = t.active||0;
  if(r) r.textContent = t.retransmissions||0;
}
function startPolling(wsIdOverride) {
  clearInterval(pollTimer);
  const pollingWsId = wsIdOverride || activeWsId;
  const ws = workspaces[pollingWsId];
  const interval = ws?.role === 'rx' ? 2000 : 1500;
  pollTimer = setInterval(async () => {
    if(!activeWsId) return;
    if(activeWsId !== pollingWsId) {
      // workspace switched — stop this poll
      clearInterval(pollTimer);
      return;
    }
    try {
      const r = await fetch(`/workspaces/${pollingWsId}/status`);
      const d = await r.json();

      // store stats on workspace object
      if(workspaces[pollingWsId]) {
        workspaces[pollingWsId].stats = d.totals || {};
        workspaces[pollingWsId].scriptStats = d.scripts || {};
      }

      // Sync displayed IP/port from the backend's authoritative values —
      // the fields are disabled while running (see selectWorkspace/
      // startWorkspace) so this should normally be a no-op, but it's a
      // self-correcting safety net rather than trusting local state to
      // never drift from what's actually bound.
      if(workspaces[pollingWsId] && d.ip && d.port){
        workspaces[pollingWsId].ip = d.ip;
        workspaces[pollingWsId].port = d.port;
        if(activeWsId === pollingWsId){
          const portInputEl = document.getElementById('ws-port-input');
          if(portInputEl && document.activeElement !== portInputEl) portInputEl.value = d.port;
          const ipSelEl = document.getElementById('ws-ip-select');
          if(ipSelEl && document.activeElement !== ipSelEl) ipSelEl.value = d.ip;
        }
      }

      // only update display if this is still the active workspace
      if(activeWsId !== pollingWsId) return;

      const t = d.totals || {};
      const sentEl = document.getElementById('ws-sent');
      const okEl   = document.getElementById('ws-completed');
      const failEl = document.getElementById('ws-failed');
      if(sentEl) sentEl.textContent = t.sent||0;
      if(okEl)   okEl.textContent   = t.completed||0;
      if(failEl) failEl.textContent = t.failed||0;
      setExtra(t);

      workspaces[pollingWsId].stats = t;

      // update per-script stats
      if(activeWsId !== pollingWsId) return;
      Object.entries(d.scripts||{}).forEach(([sid, state]) => {
        const s = getScript(parseInt(sid));
        if(s) { s.stats = state.stats; s.mos = state.mos; }
        const sentEl2 = document.getElementById(`s${sid}-sent`);
        const okEl2   = document.getElementById(`s${sid}-ok`);
        const failEl2 = document.getElementById(`s${sid}-fail`);
        const mosEl2  = document.getElementById(`s${sid}-mos`);
        if(sentEl2) sentEl2.textContent = state.stats?.sent||0;
        if(okEl2)   okEl2.textContent   = state.stats?.completed||0;
        if(failEl2) failEl2.textContent = state.stats?.failed||0;
        if(mosEl2)  mosEl2.textContent  = state.mos?.mos||'—';
        if(state.mos?.mos) {
          const mosWs = document.getElementById('ws-mos');
          if(mosWs) mosWs.textContent = state.mos.mos;
        }
      });
      // update RX listening banner
      if(workspaces[activeWsId]?.role === 'rx') {
        const banner = document.getElementById('rx-listen-banner');
        if(banner) banner.style.display = d.running ? 'block' : 'none';
      }

      // update interval progress
      renderIntervalProgress(d.current_interval, workspaces[activeWsId]?.intervals?.length||0);

      // update log — only show new entries
      if(d.log?.length) {
        const logEl = document.getElementById('ws-log');
        const lastLogCount = parseInt(logEl?.dataset.logCount||'0');
        if(logEl && d.log.length > lastLogCount) {
          d.log.slice(lastLogCount).forEach(entry => {
            const line = document.createElement('div');
            line.className = entry.level||'info';
            line.textContent = `[${entry.time}] ${entry.msg}`;
            logEl.appendChild(line);
          });
          logEl.dataset.logCount = d.log.length;
          logEl.scrollTop = logEl.scrollHeight;
        }
      }

      if(!d.running) {
        // update display with final stats BEFORE resetting
        const ft = d.totals || {};
        const sentEl = document.getElementById('ws-sent');
        const okEl   = document.getElementById('ws-completed');
        const failEl = document.getElementById('ws-failed');
        if(sentEl) sentEl.textContent = ft.sent||0;
        if(okEl)   okEl.textContent   = ft.completed||0;
        if(failEl) failEl.textContent = ft.failed||0;
        setExtra(ft);

        // Same fix as the during-run branch above — this is the FINAL
        // totals for the completed run, and it's exactly what Diagnosis
        // will read if run right after. Must persist to ws.stats, not
        // just the DOM.
        workspaces[pollingWsId].stats = ft;
        // ...and must actually be SAVED, not just held in memory — same
        // gap-class as the earlier autosave hardening: setting the value
        // isn't enough if nothing tells the server to persist it, and
        // this specific value (completed-run stats) had no other save
        // trigger anywhere in the completion path.
        saveWorkspaces();

        // update per-script stats
        Object.entries(d.scripts||{}).forEach(([sid, state]) => {
          const sentEl2 = document.getElementById(`s${sid}-sent`);
          const okEl2   = document.getElementById(`s${sid}-ok`);
          const failEl2 = document.getElementById(`s${sid}-fail`);
          if(sentEl2) sentEl2.textContent = state.stats?.sent||0;
          if(okEl2)   okEl2.textContent   = state.stats?.completed||0;
          if(failEl2) failEl2.textContent = state.stats?.failed||0;
        });

        if(activeWsId === pollingWsId) {
          addLog(`Complete — sent:${ft.sent||0} ok:${ft.completed||0} fail:${ft.failed||0}`, 'ok');
          resetControls();
          populateScriptDropdowns();
          // auto-refresh SIP stats after run
          setTimeout(() => loadSipStats(), 500);
        }
        clearInterval(pollTimer);
        pollTimer = null;
      }

    } catch(e) {
      addLog('Lost contact with server', 'err');
      resetControls();
    }
  }, 1000);
}

function populateScriptDropdowns() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const options = ws.scripts.map(s =>
    `<option value="${escapeHtml(s.id)}">Script ${escapeHtml(s.id)} — ${escapeHtml(s.sut_name)}</option>`
  ).join('');
  ['ladder-script-select', 'pcap-script-select', 'sipstats-script-select'].forEach(id => {
    const el = document.getElementById(id);
    if(el) el.innerHTML = options;
  });
}

function refreshWorkspaceDisplay() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];

  // if not running, show dashes not cached stats
  if(!ws.running) {
    ['ws-sent','ws-completed','ws-failed','ws-mos'].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.textContent = '—';
    });
    // clear per-script displays too
    ws.scripts.forEach(s => {
      ['sent','ok','fail','mos'].forEach(f => {
        const el = document.getElementById(`s${s.id}-${f}`);
        if(el) el.textContent = '—';
      });
    });
    // clear RX stats
    ['s1-sent','s1-ok','s1-fail'].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.textContent = '—';
    });
    return;
  }

  // running — restore cached stats
  const t = ws.stats || {};
  const sentEl = document.getElementById('ws-sent');
  const okEl   = document.getElementById('ws-completed');
  const failEl = document.getElementById('ws-failed');
  const mosEl  = document.getElementById('ws-mos');
  if(sentEl) sentEl.textContent = t.sent !== undefined ? t.sent : '—';
  if(okEl)   okEl.textContent   = t.completed !== undefined ? t.completed : '—';
  if(failEl) failEl.textContent = t.failed !== undefined ? t.failed : '—';
  if(mosEl)  mosEl.textContent  = ws.mos || '—';

  const scriptStats = ws.scriptStats || {};
  Object.entries(scriptStats).forEach(([sid, state]) => {
    const s = getScript(parseInt(sid));
    if(s) { s.stats = state.stats; }
    const sentEl2 = document.getElementById(`s${sid}-sent`);
    const okEl2   = document.getElementById(`s${sid}-ok`);
    const failEl2 = document.getElementById(`s${sid}-fail`);
    const mosEl2  = document.getElementById(`s${sid}-mos`);
    if(sentEl2) sentEl2.textContent = state.stats?.sent||0;
    if(okEl2)   okEl2.textContent   = state.stats?.completed||0;
    if(failEl2) failEl2.textContent = state.stats?.failed||0;
    if(mosEl2)  mosEl2.textContent  = state.mos?.mos||'—';
  });
}

function renderIntervalProgress(currentInterval, totalIntervals) {
  const badge = document.getElementById('ws-badge');
  const lbl = document.getElementById('interval-progress-label');
  if(currentInterval > 0 && totalIntervals > 0) {
    if(badge) { badge.className='badge running'; badge.textContent=`Interval ${currentInterval}/${totalIntervals}`; }
    if(lbl) lbl.textContent = `Running interval ${currentInterval} of ${totalIntervals}`;
    // update chart to highlight current interval
    if(activeWsId) workspaces[activeWsId].currentInterval = currentInterval;
    renderIntervalChart();
  }
}
