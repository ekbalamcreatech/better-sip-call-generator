// ═══════════════════════════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════════════════════════
async function loadConfig(){
  await Promise.all([loadSUTs(),loadAudioFileList(),loadInterfaceList(),loadStirInfo(),loadAccountInfo()]);
}

async function changeAccountPassword(){
  const oldPw = document.getElementById('acct-old-pw').value;
  const newPw = document.getElementById('acct-new-pw').value;
  const confirmPw = document.getElementById('acct-new-pw-confirm').value;
  const msgEl = document.getElementById('acct-pw-msg');
  msgEl.style.color = '#f87171';

  if(!oldPw || !newPw || !confirmPw){ msgEl.textContent = 'All fields are required.'; return; }
  if(newPw.length < 8){ msgEl.textContent = 'New password must be at least 8 characters.'; return; }
  if(newPw !== confirmPw){ msgEl.textContent = 'New password and confirmation do not match.'; return; }

  const fd = new FormData();
  fd.append('old_password', oldPw);
  fd.append('new_password', newPw);

  const r = await fetch('/auth/change-password', {method:'POST', body:fd});
  if(r.ok){
    msgEl.style.color = '#4ade80';
    msgEl.textContent = 'Password changed successfully.';
    ['acct-old-pw','acct-new-pw','acct-new-pw-confirm'].forEach(id=>document.getElementById(id).value='');
  } else {
    const err = await r.json().catch(()=>({detail:'Failed to change password'}));
    msgEl.textContent = err.detail || 'Failed to change password.';
  }
}

async function loadSUTs(){
  try{
    const r=await fetch('/suts');
    const d=await r.json();
    availableSUTs=d.suts||[];
    renderSUTTable();
    if(activeWsId) renderScripts();
  }catch(e){}
}

function renderSUTTable(){
  const tbody=document.getElementById('sut-table-body');
  if(!tbody) return;
  if(!availableSUTs.length){
    tbody.innerHTML='<tr><td colspan="4" style="color:#888;font-size:13px;padding:12px">No SUTs</td></tr>';return;
  }
  tbody.innerHTML=availableSUTs.map(s=>`
    <tr>
      <td style="font-weight:500;padding:8px 10px">${escapeHtml(s.name)}</td>
      <td style="font-family:monospace;padding:8px 10px">${escapeHtml(s.ip)}</td>
      <td style="padding:8px 10px">${escapeHtml(s.port)}</td>
      <td style="padding:8px 10px">
        <button data-name="${escapeHtml(s.name)}" onclick="deleteSUT(this.dataset.name)" style="padding:3px 8px;font-size:11px;color:#dc2626;border:1px solid #fca5a5;border-radius:4px;background:transparent;cursor:pointer">Delete</button>
      </td>
    </tr>`).join('');
}

async function addSUT(){
  const name=document.getElementById('new-sut-name')?.value.trim();
  const ip  =document.getElementById('new-sut-ip')?.value.trim();
  const port=document.getElementById('new-sut-port')?.value.trim()||'5060';
  if(!name||!ip){alert('Name and IP required');return;}
  const r=await fetch('/suts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,ip,port})});
  const d=await r.json();
  if(d.ok){document.getElementById('new-sut-name').value='';document.getElementById('new-sut-ip').value='';await loadSUTs();}
  else alert(d.error||'Failed');
}

async function deleteSUT(name){
  if(!confirm(`Delete SUT "${name}"?`)) return;
  const r = await fetch(`/suts/${encodeURIComponent(name)}`,{method:'DELETE'});
  if(!r.ok){ const d = await r.json().catch(()=>({})); alert(d.detail || 'Could not delete SUT.'); }
  await loadSUTs();
}

async function loadAudioFileList(){
  try{
    const r=await fetch('/audio/files');
    const d=await r.json();
    audioFiles=d.files||[];
    const el=document.getElementById('audio-file-list');
    if(el) el.innerHTML=audioFiles.map(f=>
      `<div style="padding:5px 0;border-bottom:1px solid #f5f5f5;display:flex;gap:16px;font-size:13px">
        <span style="font-weight:500">${escapeHtml(f.filename)}</span>
        <span style="color:#888">${escapeHtml(f.duration_s)}s</span>
        <span style="color:#aaa;font-size:11px">${escapeHtml(f.path)}</span>
      </div>`).join('');
    // also update audio tab dropdowns
    const fileSel=document.getElementById('audio-file-select');
    if(fileSel) fileSel.innerHTML=audioFiles.map(f=>
      `<option value="${escapeHtml(f.filename)}">${escapeHtml(f.filename)} (${escapeHtml(f.duration_s)}s)</option>`).join('');
  }catch(e){}
}

async function loadInterfaceList(){
  try{
    const r=await fetch('/interfaces');
    const d=await r.json();
    availableIPs=d.ips||[];
    const portsByIp = {};
    (d.interfaces||[]).forEach(i => { portsByIp[i.ip] = i.ports_in_use || []; });

    const el=document.getElementById('interface-list');
    if(el) el.innerHTML=availableIPs.map(ip=>{
      const inUse = portsByIp[ip] || [];
      const status = inUse.length
        ? `<span style="color:#888;font-size:11px"> — ports in use: ${inUse.map(p=>`${p.port} (${escapeHtml(p.owner)})`).join(', ')}</span>`
        : '';
      return `<div style="padding:3px 0;font-family:monospace;font-size:13px">${escapeHtml(ip)}${status}</div>`;
    }).join('');

    // An IP is never exclusive — many workspaces can share one IP on
    // different ports, same as this app's own nextAvailablePort()/
    // checkAllPortConflicts() logic has always assumed for a single
    // operator. Never disable an IP option here; just show what ports
    // are already claimed on it as a heads-up. The actual conflict check
    // happens server-side on submit, keyed on the specific ip:port pair.
    const ipSel=document.getElementById('ws-ip-select');
    if(ipSel&&activeWsId){
      const ws=workspaces[activeWsId];
      ipSel.innerHTML=availableIPs.map(ip=>{
        const inUse = portsByIp[ip] || [];
        const hint = inUse.length ? ` (ports in use: ${inUse.map(p=>p.port).join(',')})` : '';
        return `<option value="${escapeHtml(ip)}" ${ip===ws?.ip?'selected':''}>${escapeHtml(ip)}${escapeHtml(hint)}</option>`;
      }).join('');
    }
  }catch(e){}
}



// ─── AI provider (admin-configured; the server makes the call) ──────────────
let llmInfo = {provider:'anthropic', model:'', key_required:true};

async function refreshLlmInfo(){
  try{ const r = await fetch('/llm/info'); if(r.ok) llmInfo = await r.json(); }catch(e){}
  const key = document.getElementById('api-key');
  if(key){
    key.style.display = llmInfo.key_required ? '' : 'none';
    key.placeholder = 'API key (not stored)';
  }
  return llmInfo;
}

async function llmGenerate(prompt, maxTokens){
  await refreshLlmInfo();
  const apiKey = document.getElementById('api-key').value.trim();
  if(llmInfo.key_required && !apiKey) throw new Error('Enter your API key first (' + llmInfo.provider + ')');
  const r = await fetch('/llm/generate', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({prompt, max_tokens:maxTokens, api_key:apiKey})});
  const d = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'AI request failed');
  return d.text || '';
}

function llmFormHints(){
  const p = document.getElementById('llm-provider-select').value;
  const base = document.getElementById('llm-baseurl-input');
  base.style.display = (p === 'openai_compatible') ? '' : 'none';
  document.getElementById('llm-authmode-select').style.display = (p === 'openai_compatible') ? '' : 'none';
}

async function loadLlmProviderInfo(){
  const el = document.getElementById('llm-provider-info');
  if(!el) return;
  try{
    const d = await refreshLlmInfo();
    el.innerHTML = `
      <div style="display:grid;grid-template-columns:auto 1fr;gap:6px 14px">
        <span style="color:#888">Provider:</span><span style="font-weight:500">${escapeHtml(d.provider)}</span>
        <span style="color:#888">Model:</span><span style="font-family:monospace;font-size:12px">${escapeHtml(d.model)}</span>
        ${d.base_url ? `<span style="color:#888">Base URL:</span><span style="font-family:monospace;font-size:12px">${escapeHtml(d.base_url)}</span>` : ''}
        ${d.provider === 'openai_compatible' ? `<span style="color:#888">Auth:</span><span>${escapeHtml(d.auth_mode)}</span>` : ''}
      </div>`;
    const edit = document.getElementById('llm-provider-edit');
    const isAdmin = (currentUserRole === 'admin');
    if(edit){
      edit.style.display = isAdmin ? '' : 'none';
      if(isAdmin){
        document.getElementById('llm-provider-select').value = d.provider;
        document.getElementById('llm-model-input').value = d.model;
        document.getElementById('llm-baseurl-input').value = d.base_url || '';
        document.getElementById('llm-authmode-select').value = d.auth_mode;
        llmFormHints();
      }
    }
  }catch(e){
    el.textContent = 'Could not load the AI provider settings.';
  }
}

async function saveLlmProviderConfig(){
  const msg = document.getElementById('llm-provider-msg');
  const body = {
    provider: document.getElementById('llm-provider-select').value,
    model: document.getElementById('llm-model-input').value.trim(),
    base_url: document.getElementById('llm-baseurl-input').value.trim(),
    auth_mode: document.getElementById('llm-authmode-select').value
  };
  msg.style.color = '#f87171';
  if(!body.model){ msg.textContent = 'Model is required.'; return; }
  if(body.provider === 'openai_compatible' && !body.base_url){ msg.textContent = 'Base URL is required for a self-hosted model.'; return; }
  const r = await fetch('/llm/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const d = await r.json().catch(()=>({}));
  if(r.ok){ msg.style.color = '#4ade80'; msg.textContent = 'AI provider updated.'; loadLlmProviderInfo(); }
  else { msg.textContent = typeof d.detail === 'string' ? d.detail : 'Could not update the AI provider.'; }
}
