// ═══════════════════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════════════════
async function init() {
  loadAuthStatus();
  refreshLlmInfo();
  await Promise.all([loadSUTs(), loadAudioFileList(), loadInterfaceList()]);
  pingServer();

  // try to restore saved workspaces
  const restored = await loadSavedWorkspaces();
  if(!restored) {
    // no saved workspaces — add default one
    addWorkspace();
  }
}

init();
