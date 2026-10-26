// ═══════════════════════════════════════════════════════════════════════════════
// INTERVALS
// ═══════════════════════════════════════════════════════════════════════════════
function addInterval() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const id = nextIntervalId[activeWsId]++;
  const scriptCps = {};
  ws.scripts.forEach(s => { scriptCps[s.id] = 1; });  // default 1 CPS
  ws.intervals.push({id, duration_s:30, label:'', script_cps:scriptCps});
  renderIntervals();
  updateStartBtn();
  saveWorkspaces();
}

function removeInterval(id) {
  if(!activeWsId) return;
  workspaces[activeWsId].intervals = workspaces[activeWsId].intervals.filter(i => i.id !== id);
  renderIntervals();
  saveWorkspaces();
}

function updateIntervalField(id, field, value) {
  if(!activeWsId) return;
  const interval = workspaces[activeWsId].intervals.find(i => i.id === id);
  if(interval) interval[field] = value;
  updateIntervalTimeline();
  saveWorkspaces();  // Was: missing — interval edits (duration, etc.) weren't persisted.
}

function updateIntervalScriptCps(intervalId, scriptId, cps) {
  if(!activeWsId) return;
  const interval = workspaces[activeWsId].intervals.find(i => i.id === intervalId);
  if(interval) interval.script_cps[scriptId] = Math.max(0, parseFloat(cps)||0);
  renderIntervalChart();
  saveWorkspaces();  // Was: missing — per-script CPS within an interval wasn't persisted.
}

function renderIntervalChart() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const canvas = document.getElementById('interval-canvas');
  const emptyEl = document.getElementById('interval-chart-empty');
  if(!canvas) return;

  if(ws.role === 'rx' || !ws.intervals.length) {
    canvas.style.display = 'none';
    if(emptyEl) {
      emptyEl.style.display = 'block';
      emptyEl.textContent = ws.role === 'rx' ?
        'RX workspace — listening until stopped' :
        'Add intervals to see the CPS profile';
    }
    return;
  }
  canvas.style.display = 'block';
  if(emptyEl) emptyEl.style.display = 'none';

  const ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth || 600;
  canvas.width = W;
  const H = 100;

  ctx.clearRect(0, 0, W, H);

  // colors per script
  const colors = ['#185FA5', '#16a34a', '#d97706', '#dc2626', '#7c3aed'];
  const scripts = ws.scripts;
  const intervals = ws.intervals;
  const n = intervals.length;
  const barGroupW = (W - 40) / n;
  const barW = Math.max(4, (barGroupW - 4) / Math.max(scripts.length, 1));

  // find max CPS for scaling
  let maxCPS = 1;
  intervals.forEach(iv => {
    Object.values(iv.script_cps||{}).forEach(cps => {
      if(cps > maxCPS) maxCPS = cps;
    });
  });

  // draw bars
  intervals.forEach((iv, idx) => {
    const x = 20 + idx * barGroupW;
    const isActive = ws.currentInterval === idx + 1;

    // highlight active interval
    if(isActive) {
      ctx.fillStyle = 'rgba(220,38,38,0.08)';
      ctx.fillRect(x, 0, barGroupW - 2, H - 15);
    }

    scripts.forEach((s, si) => {
      const cps = iv.script_cps?.[s.id] || 0;
      const barH = cps > 0 ? Math.max(3, (cps / maxCPS) * (H - 20)) : 2;
      const bx = x + si * barW + 2;
      const by = H - 15 - barH;

      ctx.fillStyle = isActive ? '#dc2626' : colors[si % colors.length];
      ctx.fillRect(bx, by, barW - 1, barH);

      // CPS label on bar
      if(barH > 14 && barW > 20) {
        ctx.fillStyle = '#fff';
        ctx.font = '9px system-ui';
        ctx.textAlign = 'center';
        ctx.fillText(cps, bx + (barW-1)/2, by + barH - 3);
      }
    });

    // interval number below
    ctx.fillStyle = isActive ? '#dc2626' : '#888';
    ctx.font = isActive ? 'bold 10px system-ui' : '10px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText(idx + 1, x + barGroupW/2, H - 3);

    // duration label
    ctx.fillStyle = '#aaa';
    ctx.font = '9px system-ui';
    ctx.fillText(`${iv.duration_s}s`, x + barGroupW/2, H - 12);
  });

  // legend
  // (scripts already labeled in script cards)
}

function renderIntervals() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const container = document.getElementById('interval-slots');
  if(!container) return;

  if(!ws.intervals.length) {
    container.innerHTML = '<p style="color:#888;font-size:13px">No intervals — workspace runs until stopped.</p>';
    updateIntervalTimeline();
    return;
  }

  container.innerHTML = ws.intervals.map((interval,idx) => `
    <div class="interval-card">
      <div class="interval-header">
        <div class="interval-num">${escapeHtml(idx+1)}</div>
        <input value="${escapeHtml(interval.label||'')}" placeholder="Interval label (optional)"
          onchange="updateIntervalField(${escapeHtml(interval.id)},'label',this.value)"
          style="flex:1;border:1px solid #e5e5e5;border-radius:6px;padding:5px 8px;font-size:13px;outline:none"/>
        <span style="font-size:12px;color:#888;margin-left:8px;white-space:nowrap">Duration (s):</span>
        <input type="number" value="${escapeHtml(interval.duration_s)}" min="1"
          onchange="updateIntervalField(${escapeHtml(interval.id)},'duration_s',parseInt(this.value)||30);updateIntervalTimeline()"
          style="width:70px;border:1px solid #e5e5e5;border-radius:6px;padding:5px 8px;font-size:13px;outline:none"/>
        <button onclick="removeInterval(${escapeHtml(interval.id)})" style="padding:3px 8px;font-size:11px;color:#dc2626;border:1px solid #fca5a5;border-radius:4px;background:transparent;cursor:pointer;margin-left:8px">✕</button>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px">
        ${ws.scripts.map(s => `
          <div style="background:#fafafa;border:1px solid #e5e5e5;border-radius:6px;padding:8px">
            <div style="font-size:11px;color:#888;margin-bottom:4px">Script ${escapeHtml(s.id)} — ${escapeHtml(s.sut_name)}</div>
            <div style="display:flex;align-items:center;gap:6px">
              <span style="font-size:11px;color:#888">CPS:</span>
              <input type="number" value="${escapeHtml(interval.script_cps[s.id]||0)}" min="0" step="0.1"
                onchange="updateIntervalScriptCps(${escapeHtml(interval.id)},${escapeHtml(s.id)},this.value)"
                style="width:60px;border:1px solid #e5e5e5;border-radius:4px;padding:4px 6px;font-size:12px;outline:none"/>
              <span style="font-size:10px;color:#aaa">(0=pause)</span>
            </div>
          </div>`).join('')}
      </div>
    </div>`).join('');

  updateIntervalTimeline();
  renderIntervalChart();
}

function updateIntervalTimeline() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const el = document.getElementById('interval-timeline');
  if(!el) return;
  if(!ws.intervals.length) {
    el.textContent = 'No intervals — workspace runs until stopped.';
    return;
  }
  const total = ws.intervals.reduce((s,i) => s + (i.duration_s||0), 0);
  const parts = ws.intervals.map((i,idx) =>
    `Interval ${idx+1}: ${i.duration_s}s${i.label?' ('+i.label+')':''}`
  ).join(' → ');
  el.textContent = `${parts}  |  Total: ${total}s`;
}
