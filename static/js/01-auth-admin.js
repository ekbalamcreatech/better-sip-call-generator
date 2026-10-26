// ═══════════════════════════════════════════════════════════════════════════════
// AUTH — global fetch wrapper. If the session expired server-side (inactivity
// timeout) or was never valid, every fetch() call in this file will start
// getting 401s back. Rather than adding a check to ~40 individual call sites,
// wrap fetch() once here so any 401 anywhere sends the user to /login.
// Placed before everything else so it's active before any real fetch fires.
// ═══════════════════════════════════════════════════════════════════════════════
(function(){
  const _origFetch = window.fetch;
  window.fetch = async function(...args){
    const res = await _origFetch(...args);
    if(res.status === 401 && !window.location.pathname.startsWith('/login')){
      window.location.href = '/login';
    }
    return res;
  };
})();

let currentUserRole = null;
let currentUsername = null;

async function loadAccountInfo(){
  try{
    const r=await fetch('/auth/status');
    const d=await r.json();
    const el=document.getElementById('account-username');
    if(el) el.textContent = d.username ? `${d.username} (${d.role})` : '—';
    if(d.username) currentUsername = d.username;
    currentUserRole = d.role;

    // Role-gated panels — hidden entirely for roles that can't use them,
    // rather than shown-but-disabled, since a 'user' account querying
    // /users or /workspaces (all) would just get a 403 anyway.
    const userMgmt = document.getElementById('user-mgmt-panel');
    if(userMgmt) userMgmt.style.display = (d.role === 'admin') ? '' : 'none';

    const adminWs = document.getElementById('admin-workspaces-panel');
    if(adminWs) adminWs.style.display = (d.role === 'admin') ? '' : 'none';

    // Same gating, now also applied to the Config sub-tab BUTTONS
    // themselves — a 'user' role shouldn't even see a "Users" tab to
    // click, not just find it empty once they get there.
    const usersTabBtn = document.getElementById('config-tab-btn-users');
    if(usersTabBtn) usersTabBtn.style.display = (d.role === 'admin') ? '' : 'none';

    const workspacesTabBtn = document.getElementById('config-tab-btn-workspaces');
    if(workspacesTabBtn) workspacesTabBtn.style.display = (d.role === 'admin') ? '' : 'none';

    if(d.role === 'admin') loadUserList();
    if(d.role === 'admin') loadAdminWorkspaces();
  }catch(e){}
}

function showConfigTab(name){
  document.querySelectorAll('.config-tab-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.tab === name));
  document.querySelectorAll('.config-tab-content').forEach(panel =>
    panel.classList.toggle('active', panel.id === `config-tab-content-${name}`));

  // Refetch whichever tab was just switched to — same lesson learned the
  // hard way with Ladder/SIP Stats/Call Quality earlier: a tab that only
  // toggles visibility without refreshing its data will happily show
  // stale content from whenever it was last loaded, not what's true now.
  const loaders = {
    sut: loadSUTs,
    account: loadAccountInfo,
    users: loadUserList,
    workspaces: loadAdminWorkspaces,
    stir: loadStirInfo,
    audio: loadAudioFileList,
    interfaces: loadInterfaceList,
    llmprovider: loadLlmProviderInfo,
  };
  if(loaders[name]) loaders[name]();
}

// ─── User Management (admin only) ────────────────────────────────────
async function loadUserList(){
  try{
    const r = await fetch('/users');
    if(!r.ok) return;  // not admin, panel is hidden anyway
    const d = await r.json();
    renderUserList(d.users || []);
  }catch(e){}
}

function renderUserList(users){
  const tbody = document.getElementById('user-mgmt-tbody');
  if(!tbody) return;
  tbody.innerHTML = users.map(u => `
    <tr>
      <td style="padding:8px 10px;font-weight:500">${escapeHtml(u.username)}</td>
      <td style="padding:8px 10px">
        <select data-user="${escapeHtml(u.username)}" onchange="changeUserRole(this.dataset.user, this.value)" style="font-size:12px;padding:3px 6px">
          <option value="user" ${u.role==='user'?'selected':''}>user</option>
          <option value="admin" ${u.role==='admin'?'selected':''}>admin</option>
        </select>
      </td>
      <td style="padding:8px 10px">
        <input type="number" min="0" value="${escapeHtml(u.max_workspaces ?? '')}" placeholder="default"
          style="width:90px;font-size:12px;padding:3px 6px"
          data-user="${escapeHtml(u.username)}" onchange="changeUserMaxWorkspaces(this.dataset.user, this.value)"/>
      </td>
      <td style="padding:8px 10px">
        <button data-user="${escapeHtml(u.username)}" onclick="deleteUser(this.dataset.user)" style="padding:3px 8px;font-size:11px;color:#dc2626;border:1px solid #fca5a5;border-radius:4px;background:transparent;cursor:pointer">Delete</button>
      </td>
    </tr>`).join('');
}

async function changeUserMaxWorkspaces(username, value){
  const fd = new FormData();
  // Empty input -> clear the override, fall back to the default limit
  if(value !== '') fd.append('max_workspaces', value);
  const r = await fetch(`/users/${encodeURIComponent(username)}/max-workspaces`, {method:'POST', body:fd});
  if(!r.ok){
    const err = await r.json().catch(()=>({detail:'Failed to update'}));
    alert(err.detail);
  }
  loadUserList();
}

async function createUser(){
  const username = document.getElementById('new-user-username').value.trim();
  const password = document.getElementById('new-user-password').value;
  const role = document.getElementById('new-user-role').value;
  const maxWsInput = document.getElementById('new-user-max-workspaces').value.trim();
  const msgEl = document.getElementById('user-mgmt-msg');
  msgEl.style.color = '#f87171';

  if(!username || !password){ msgEl.textContent = 'Username and password required.'; return; }

  const fd = new FormData();
  fd.append('username', username);
  fd.append('password', password);
  fd.append('role', role);
  if(maxWsInput !== '') fd.append('max_workspaces', maxWsInput);
  const r = await fetch('/users', {method:'POST', body:fd});
  if(r.ok){
    msgEl.style.color = '#4ade80';
    msgEl.textContent = `User '${username}' created.`;
    document.getElementById('new-user-username').value = '';
    document.getElementById('new-user-password').value = '';
    document.getElementById('new-user-max-workspaces').value = '';
    loadUserList();
  } else {
    const err = await r.json().catch(()=>({detail:'Failed to create user'}));
    msgEl.textContent = err.detail;
  }
}

async function changeUserRole(username, role){
  const r = await fetch(`/users/${encodeURIComponent(username)}/role`, {method:'POST', body:new URLSearchParams({role})});
  if(!r.ok){
    const err = await r.json().catch(()=>({detail:'Failed to change role'}));
    alert(err.detail);
  }
  loadUserList();
}

async function deleteUser(username){
  if(!confirm(`Delete user '${username}'? This cannot be undone.`)) return;
  const r = await fetch(`/users/${encodeURIComponent(username)}`, {method:'DELETE'});
  if(!r.ok){
    const err = await r.json().catch(()=>({detail:'Failed to delete user'}));
    alert(err.detail);
  }
  loadUserList();
}

// ─── All Workspaces (admin oversight) ──────────────────────────
async function loadAdminWorkspaces(){
  try{
    const r = await fetch('/workspaces');
    if(!r.ok) return;  // not admin, panel is hidden anyway
    const d = await r.json();
    renderAdminWorkspaces(d);
  }catch(e){}
}

function renderAdminWorkspaces(allWs){
  const tbody = document.getElementById('admin-workspaces-tbody');
  if(!tbody) return;
  const entries = Object.values(allWs);
  if(!entries.length){
    tbody.innerHTML = '<tr><td colspan="6" style="color:#888;font-size:13px;padding:12px">No workspaces claimed right now</td></tr>';
    return;
  }
  tbody.innerHTML = entries.map(ws => `
    <tr>
      <td style="padding:8px 10px">${escapeHtml(ws.workspace_id)}</td>
      <td style="padding:8px 10px;font-weight:500">${escapeHtml(ws.owner || '—')}</td>
      <td style="padding:8px 10px">${escapeHtml(ws.label || '')}</td>
      <td style="padding:8px 10px;font-family:monospace;font-size:12px">${escapeHtml(ws.ip || '')}</td>
      <td style="padding:8px 10px;color:${ws.running?'#16a34a':'#888'}">${ws.running ? '▶ running' : 'idle'}</td>
      <td style="padding:8px 10px;display:flex;gap:6px">
        ${ws.running ? `<button onclick="adminForceStop(${escapeHtml(ws.workspace_id)})" style="padding:3px 8px;font-size:11px;color:#b45309;border:1px solid #fcd34d;border-radius:4px;background:transparent;cursor:pointer">Force Stop</button>` : ''}
        ${ws.owner ? `<button onclick="adminReleaseWorkspace(${escapeHtml(ws.workspace_id)})" style="padding:3px 8px;font-size:11px;color:#dc2626;border:1px solid #fca5a5;border-radius:4px;background:transparent;cursor:pointer">Release</button>` : `<span style="font-size:11px;color:#bbb">already free</span>`}
      </td>
    </tr>`).join('');
}

async function adminForceStop(workspaceId){
  if(!confirm(`Force-stop workspace ${workspaceId}? The owner's test will be interrupted.`)) return;
  const r = await fetch(`/workspaces/${workspaceId}/force-stop`, {method:'POST'});
  if(!r.ok){ const err = await r.json().catch(()=>({detail:'Failed'})); alert(err.detail); }
  loadAdminWorkspaces();
}

async function adminReleaseWorkspace(workspaceId){
  if(!confirm(`Release workspace ${workspaceId}? This frees the slot and IP for anyone to claim — the current owner will lose it.`)) return;
  const r = await fetch(`/workspaces/${workspaceId}/release`, {method:'POST'});
  if(!r.ok){ const err = await r.json().catch(()=>({detail:'Failed'})); alert(err.detail); }
  loadAdminWorkspaces();
}

async function doLogout(){
  // Cheap insurance: after today's fixes, virtually every edit saves
  // immediately as it happens — but a field you're actively typing in
  // (not yet blurred/committed) wouldn't have fired its onchange yet.
  // Force a save right before logging out so that narrow gap can't lose data.
  await saveWorkspaces();
  await fetch('/auth/logout', {method:'POST'});
  window.location.href = '/login';
}

async function loadAuthStatus(){
  try{
    const r = await fetch('/auth/status');
    const d = await r.json();
    const el = document.getElementById('logged-in-as');
    if(el && d.authenticated) el.textContent = `👤 ${d.username}`;
    if(d.authenticated) currentUsername = d.username;
  }catch(e){}
}
