// ═══════════════════════════════════════════════════════════════════════════════
// LADDER
// ═══════════════════════════════════════════════════════════════════════════════
async function loadLadder() {
  if(!activeWsId) return;
  const sid = parseInt(document.getElementById('ladder-script-select')?.value)||1;
  try {
    const r = await fetch(`/workspaces/${activeWsId}/ladder?script_id=${sid}`);
    const d = await r.json();

    // update script dropdown with available scripts
    if(d.available_scripts?.length) {
      const sel = document.getElementById('ladder-script-select');
      if(sel) {
        const ws = workspaces[activeWsId];
        sel.innerHTML = d.available_scripts.map(s => {
          const script = ws.scripts.find(x => x.id === s);
          const label = script ? `Script ${s} — ${script.sut_name}` : `Script ${s}`;
          return `<option value="${escapeHtml(s)}" ${s===sid?'selected':''}>${escapeHtml(label)}</option>`;
        }).join('');
      }
    }

    const ws = workspaces[activeWsId];
    let srcLabel, dstLabel;

    if(ws.role === 'rx') {
      // RX: left=remote caller, right=our UAS listener
      srcLabel = 'Remote Caller';
      dstLabel = `${escapeHtml(ws.ip)}:${escapeHtml(ws.port)} (UAS)`;
    } else {
      const script = ws?.scripts.find(x=>x.id===sid);
      srcLabel = script ? `${script.orig_ip}:${script.sip_port}` : `${ws?.ip||'UAC'}:${ws?.port||5081}`;
      dstLabel = script ? `${script.sut_ip}:${script.sut_port}` : 'SUT:5060';
    }

    let streamPresence = {};
    try {
      const qr = await fetch(`/quality/${activeWsId}?script_id=${sid}`);
      const qd = await qr.json();
      (qd.calls||[]).forEach(c => {
        const streams = c.streams || [];
        streamPresence[c.call_id] = {
          hasOut: streams.some(s => s.direction === 'out'),
          hasIn:  streams.some(s => s.direction === 'in')
        };
      });
    } catch(e) { /* fall back to SDP-only rendering if this fails */ }

    renderLadder('ladder-container-svg', d.calls, srcLabel, dstLabel, ws.role === 'rx', streamPresence);

  } catch(e) {
    addLog('Ladder error: '+e.message, 'err');
  }
}

function showRaw(containerId, raw, method) {
  document.getElementById('ladder-raw-title').textContent = 'Raw SIP — ' + method;
  document.getElementById('ladder-raw-content').textContent = raw;
  document.getElementById('ladder-raw-panel').style.display = 'block';
}
