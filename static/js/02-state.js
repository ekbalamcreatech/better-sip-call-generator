// ═══════════════════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════════════════
let workspaces = {};  // {id: {id, label, role, ip, port, scripts:[], intervals:[], ...}}
let nextWsId = 1;
let nextScriptId = {};  // {wsId: nextId}
let nextIntervalId = {};
let activeWsId = null;
let pollTimer = null;
let pollStartTime = null;
let availableSUTs = [];
let availableIPs = [];
let audioFiles = [];
