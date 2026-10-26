// ═══════════════════════════════════════════════════════════════════════════════
// HISTORY
// ═══════════════════════════════════════════════════════════════════════════════
async function loadHistory(){
  try{
    const r=await fetch('/history');
    const d=await r.json();
    const el=document.getElementById('history-list');
    if(!d.history?.length){el.innerHTML='<p style="padding:1rem;color:#888;font-size:13px">No history yet</p>';return;}
    el.innerHTML=d.history.map(h=>`
      <div style="display:grid;grid-template-columns:140px 60px 1fr 1fr 80px;gap:10px;padding:8px 12px;border-bottom:1px solid #f5f5f5;font-size:13px;align-items:center">
        <span style="font-family:monospace;font-size:11px">${escapeHtml(h.timestamp?.substring(0,16)||'')}</span>
        <span style="padding:2px 8px;border-radius:10px;font-size:11px;background:${h.mode==='tx'?'#dbeafe':'#dcfce7'};color:${h.mode==='tx'?'#1d4ed8':'#15803d'}">${escapeHtml(h.mode?.toUpperCase())}</span>
        <span style="color:#555;font-size:12px">${escapeHtml(h.params?JSON.stringify(h.params).substring(0,60):'')}...</span>
        <span style="color:#555;font-size:12px">${escapeHtml(h.stats?`sent:${h.stats.sent||0} ok:${h.stats.completed||h.stats.answered||0} fail:${h.stats.failed||0}`:'')}</span>
        <span style="font-weight:500;color:#185FA5">${escapeHtml(h.mos?.mos||'—')}</span>
      </div>`).join('');
  }catch(e){}
}

function getUsedPorts() {
  const ports = new Set();
  Object.values(workspaces).forEach(ws => {
    if(ws.role === 'rx') {
      ports.add(`${escapeHtml(ws.ip)}:${escapeHtml(ws.port)}`);
    }
    ws.scripts.forEach(s => {
      ports.add(`${s.orig_ip}:${s.sip_port}`);
    });
  });
  return ports;
}

function isPortConflict(ip, port, excludeWsId=null, excludeScriptId=null) {
  const key = `${ip}:${port}`;
  for(const [wsId, ws] of Object.entries(workspaces)) {
    // skip excluded workspace
    if(parseInt(wsId) === excludeWsId && excludeScriptId === null) continue;
    // check RX listen port
    if(ws.role === 'rx' && `${escapeHtml(ws.ip)}:${escapeHtml(ws.port)}` === key) {
      if(parseInt(wsId) !== excludeWsId) return `WS "${escapeHtml(ws.label)}" listen port`;
    }
    // check script SIP ports
    ws.scripts.forEach(s => {
      if(parseInt(wsId) === excludeWsId && s.id === excludeScriptId) return;
      if(`${s.orig_ip}:${s.sip_port}` === key) {
        return `WS "${escapeHtml(ws.label)}" Script ${s.id}`;
      }
    });
  }
  return null;
}

function nextAvailablePort(basePort, ip) {
  const used = getUsedPorts();
  let port = parseInt(basePort);
  while(used.has(`${ip}:${port}`)) port++;
  return port;
}

function checkAllPortConflicts() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  ws.scripts.forEach(s => {
    const conflictEl = document.getElementById(`s${s.id}-port-conflict`);
    if(!conflictEl) return;
    // check against all other workspaces/scripts
    let conflict = false;
    Object.entries(workspaces).forEach(([wsId, otherWs]) => {
      if(parseInt(wsId) === activeWsId) {
        // check against other scripts in same workspace
        otherWs.scripts.forEach(os => {
          if(os.id !== s.id && os.orig_ip === s.orig_ip && os.sip_port === s.sip_port) {
            conflict = true;
          }
        });
      } else {
        // check against other workspaces
        if(otherWs.role === 'rx' && otherWs.ip === s.orig_ip && String(otherWs.port) === String(s.sip_port)) {
          conflict = true;
        }
        otherWs.scripts.forEach(os => {
          if(os.orig_ip === s.orig_ip && os.sip_port === s.sip_port) conflict = true;
        });
      }
    });
    conflictEl.style.display = conflict ? 'inline' : 'none';
  });
}
