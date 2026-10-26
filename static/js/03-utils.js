// ═══════════════════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════
function copyEl(id) {
  const el = document.getElementById(id);
  if(!el) return;
  const text = el.value !== undefined ? el.value : el.textContent;
  if(navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}
function fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
}

function addLog(msg, level='info') {
  const el = document.getElementById('ws-log');
  if(!el) return;
  const d = document.createElement('div');
  d.className = level;
  d.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  el.appendChild(d);
  el.scrollTop = el.scrollHeight;
}

async function pingServer() {
  const dot = document.getElementById('dot');
  const lbl = document.getElementById('server-status');
  try {
    const r = await fetch('/health');
    const d = await r.json();
    if(d.ok){ dot.className='dot online'; lbl.textContent='online'; }
  } catch(e) { dot.className='dot offline'; lbl.textContent='offline'; }
}

function showTab(name) {
  document.getElementById('no-ws-panel').style.display = 'none';
  document.getElementById('ws-content').style.display = 'none';
  document.getElementById('config-panel').style.display = 'none';
  document.getElementById('history-panel').style.display = 'none';

  if(name === 'config') {
    document.getElementById('config-panel').style.display = 'block';
    loadConfig();
  } else if(name === 'history') {
    document.getElementById('history-panel').style.display = 'block';
    loadHistory();
  } else if(name === 'workspace') {
    if(activeWsId) {
      document.getElementById('ws-content').style.display = 'flex';
    } else {
      document.getElementById('no-ws-panel').style.display = 'flex';
    }
  } else {
    document.getElementById('no-ws-panel').style.display = 'flex';
  }
}


let activeContentTab = 'scripts';
const MAX_WORKSPACES_UI = 8;  // matches the server default; the server enforces the real limit

function showContentTab(name) {
  const tabs = ['scripts','intervals','audio','log','ladder','sipstats','quality','export','scenarios'];
  document.querySelectorAll('.content-tab').forEach((t,i) => t.classList.toggle('active', tabs[i]===name));
  tabs.forEach(t => {
    const p = document.getElementById(`panel-${t}`);
    if(p) p.classList.toggle('active', t===name);
  });
  activeContentTab = name;
  if(name === 'scenarios') loadScenarios();
  else if(name === 'ladder') loadLadder();
  else if(name === 'sipstats') loadSipStats();
  else if(name === 'quality') loadCallQuality();
}
