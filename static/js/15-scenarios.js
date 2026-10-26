// ═══════════════════════════════════════════════════════════════════════════════
// SCENARIOS
// ═══════════════════════════════════════════════════════════════════════════════
async function saveScriptScenario(id) {
  if(!activeWsId) return;
  const s = getScript(id);
  if(!s || !s.xml){ alert('Generate a scenario for this script first.'); return; }
  const name = prompt('Save this scenario as:', '');
  if(!name) return;
  const desc = prompt('Description (optional):', '') || '';

  const ws = workspaces[activeWsId];
  try {
    const r = await fetch('/scenarios/save', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ name, description: desc, xml: s.xml, mode: ws.role })
    });
    const d = await r.json().catch(()=>({ok:false}));
    if(!r.ok || !d.ok){
      const why = d.detail || 'server could not save this scenario';
      addLog('Save failed — ' + why, 'err');
      alert(typeof why === 'string' ? why : 'Failed to save scenario.');
      return;
    }
    addLog(`Saved "${name}" (Script ${id})`, 'ok');
    loadScenarios();
  } catch(e) {
    alert('Could not reach the server to save this scenario.');
  }
}

async function saveRXScenario() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const s = ws.scripts[0];
  if(!s || !s.xml){ alert('Generate an RX scenario first.'); return; }
  const name = prompt('Save this RX scenario as:', '');
  if(!name) return;
  const desc = prompt('Description (optional):', '') || '';

  try {
    const r = await fetch('/scenarios/save', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ name, description: desc, xml: s.xml, mode: 'rx' })
    });
    const d = await r.json().catch(()=>({ok:false}));
    if(!r.ok || !d.ok){
      const why = d.detail || 'server could not save this RX scenario';
      addLog('Save failed — ' + why, 'err');
      alert(typeof why === 'string' ? why : 'Failed to save scenario.');
      return;
    }
    addLog(`Saved "${name}" (RX)`, 'ok');
  } catch(e) {
    alert('Could not reach the server to save this RX scenario.');
  }
}

async function loadScenarios() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  try{
    const r=await fetch(`/scenarios/list/${ws.role}`);
    const d=await r.json();
    const el=document.getElementById('scenario-list');
    if(!el) return;
    if(!d.scenarios?.length){
      el.innerHTML='<p style="color:#888;font-size:13px">No saved scenarios</p>';return;
    }
    el.innerHTML=d.scenarios.map(s=>`
      <div class="scenario-item">
        <span class="scenario-name">${escapeHtml(s.name)}</span>
        <span class="scenario-desc">${escapeHtml(s.description||'')}</span>
        <span style="font-size:11px;color:#aaa">${escapeHtml(s.saved_by ? 'by '+escapeHtml(s.saved_by)+' · ' : '')}${escapeHtml(s.saved_at?.substring(0,16)||'')}</span>
        <button data-file="${escapeHtml(s.filename)}" onclick="deleteScenario(this.dataset.file)" style="padding:3px 8px;font-size:11px;color:#dc2626;border:1px solid #fca5a5;border-radius:4px;background:transparent;cursor:pointer">Del</button>
      </div>`).join('');
  }catch(e){}
}

async function loadScriptScenario(id) {
  try{
    const r=await fetch(`/scenarios/list/tx`);
    const d=await r.json();
    if(!d.scenarios?.length){alert('No saved scenarios');return;}
    const name=prompt('Enter scenario name:\n'+d.scenarios.map(s=>s.name).join('\n'));
    if(!name) return;
    const found=d.scenarios.find(s=>s.name===name);
    if(!found){alert('Not found');return;}
    const lr=await fetch(`/scenarios/load/${found.filename}`);
    const ld=await lr.json();
    if(ld.xml){
      const s=getScript(id);
      if(s){
        s.xml=ld.xml;s.ready=true;
        revealScriptXml(id);
        saveWorkspaces();
        const rdEl=document.getElementById(`s${id}-ready`);
        if(rdEl) rdEl.innerHTML='<span style="color:#16a34a">✓ Ready</span>';
        addLog(`Script ${id}: loaded "${ld.name}"`, 'ok');
        updateStartBtn();
      }
    }
  }catch(e){addLog('Load error: '+e.message,'err');}
}

async function deleteScenario(filename){
  const r = await fetch(`/scenarios/${filename}`,{method:'DELETE'});
  if(!r.ok){ const d = await r.json().catch(()=>({})); alert(d.detail || 'Could not delete scenario.'); }
  loadScenarios();
}
