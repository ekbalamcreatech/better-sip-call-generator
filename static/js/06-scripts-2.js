function renderRXConfig() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  const container = document.getElementById('script-slots');
  if(!container) return;

  // ensure at least one script slot for RX config
  if(!ws.scripts.length) {
    ws.scripts.push({
      id:1, xml:'', ready:true,
      enable_rtp:false, audio_file:'reference.wav',
      sut_name:'UAS Listener', sut_ip:'', sut_port:'',
      orig_ip:ws.ip, sip_port:String(ws.port),
      cps:'1', pct:100, max_calls:'999999',
      called:'', calling:'',
      audio_mode:'plays', audio_value:2,
      codec:'PCMU', duration_ms:60000,
      dtmf_enabled:false, dtmf_digits:'',
      dtmf_gap_ms:100, stir_enabled:false, stir_attest:'A',
      desc:''
    });
  }

  const s = ws.scripts[0];
  // force % to 100 and ready for RX
  s.pct = 100; s.ready = true;

  container.innerHTML = `
    <div class="script-card">
      <div class="script-header" style="cursor:default">
        <div class="script-num" style="background:#15803d">●</div>
        <span style="font-size:13px;font-weight:500;flex:1">UAS Listener</span>
        <span style="font-size:12px;color:#15803d">Terminating</span>
      </div>
      <div class="script-body open">
        <div id="rx-listen-banner" style="padding:10px;background:#f0fdf4;border:1px solid #86efac;border-radius:8px;margin-bottom:12px;font-size:12px;color:#15803d">
          ● Listening on <strong id="rx-listen-addr">${escapeHtml(ws.ip)}:${escapeHtml(ws.port)}</strong> for incoming calls
        </div>

        <div class="field" style="margin-bottom:12px">
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
            <button onclick="generateRXScript()" style="padding:5px 12px;font-size:12px;background:#185FA5;color:#fff;border:none;border-radius:6px;cursor:pointer">✨ Generate RX scenario</button>
            <button onclick="viewRXXml()" id="rx-view-xml-btn" ${!s.xml?'disabled':''} style="padding:5px 12px;font-size:12px;border:1px solid #e5e5e5;border-radius:6px;background:#fff;cursor:pointer">View XML</button>
            <button onclick="saveRXScenario()" id="rx-save-btn" ${!s.xml?'disabled':''} style="padding:5px 12px;font-size:12px;border:1px solid #e5e5e5;border-radius:6px;background:#fff;cursor:pointer">💾 Save As...</button>
            <button onclick="loadRXScenario()" style="padding:5px 12px;font-size:12px;border:1px solid #e5e5e5;border-radius:6px;background:#fff;cursor:pointer">Load saved</button>
            <span id="rx-ready-indicator" style="font-size:12px">${s.xml ? '<span style="color:#16a34a">✓ Ready</span>' : '<span style="color:#aaa">needs scenario</span>'}</span>
          </div>
          <div id="rx-xml-panel" style="display:none;margin-bottom:8px">
            <pre id="rx-xml-content" style="background:#fafafa;border:1px solid #e5e5e5;border-radius:8px;padding:10px;font-size:11px;max-height:180px;overflow:auto;margin:0;white-space:pre-wrap">${escapeHtml(s.xml||'')}</pre>
          </div>
          <div class="field">
            <label>Describe RX behavior</label>
            <textarea id="rx-desc" rows="2"
              placeholder="e.g. Answer all calls, hold 30 seconds, then hang up"
              style="width:100%;border:1px solid #e5e5e5;border-radius:8px;padding:7px 10px;font-size:13px;outline:none;resize:vertical"></textarea>
          </div>
        </div>

        <div class="field" style="margin-bottom:12px">
          <label>MOS scoring</label>
          <div style="display:flex;align-items:center;gap:8px;margin-top:4px">
            <input type="checkbox" id="rx-enable-mos" ${s.enable_rtp?'checked':''}
              onchange="toggleRXMosScoring(this.checked)" style="width:15px;height:15px"/>
            <span style="font-size:12px;color:#888">Enable RTP capture and PESQ MOS scoring</span>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
          <div class="stat-card"><div class="label">Received</div><div class="value" id="s1-sent" style="font-size:16px">—</div></div>
          <div class="stat-card"><div class="label">Answered</div><div class="value ok" id="s1-ok" style="font-size:16px">—</div></div>
          <div class="stat-card"><div class="label">Failed</div><div class="value fail" id="s1-fail" style="font-size:16px">—</div></div>
        </div>
      </div>
    </div>`;

  updatePercentages();
}

function viewRXXml() {
  const panel = document.getElementById('rx-xml-panel');
  if(panel) panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

function updateRXXml() {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  if(ws.scripts[0]) ws.scripts[0].xml = document.getElementById('rx-xml')?.value||'';
  saveWorkspaces();
}

async function generateRXScript() {
  const rdEl = document.getElementById('rx-ready-indicator');
  if(rdEl) rdEl.innerHTML = '<span style="color:#f59e0b">⟳ Generating...</span>';
  const btn = document.querySelector('button[onclick="generateRXScript()"]');
  if(btn) { btn.disabled=true; btn.textContent='Generating...'; }

  if(!activeWsId) return;
  const ws = workspaces[activeWsId];

  const descEl = document.getElementById('rx-desc');
  const desc = descEl?.value.trim() || 'Answer all calls, send 200 OK, hold for 30 seconds then BYE';

  const prompt_text = `You are a SIPp expert. Generate a complete valid SIPp UAS (terminating/server side) scenario file.

Terminating behavior: "${desc}"
Listen IP: ${escapeHtml(ws.ip)}
Listen Port: ${escapeHtml(ws.port)}

Output ONLY raw XML. No markdown, no backticks, no explanation.
Start with: <?xml version="1.0" encoding="ISO-8859-1" ?>
Use <scenario name="..."> structure for UAS (server/terminating side).

CRITICAL: This is a UAS (server) scenario — it RECEIVES calls, not sends them.
CRITICAL: First element must be <recv request="INVITE"> (or <recv request="REGISTER"> if the description is about registration).
CRITICAL: Use [last_Via:] [last_From:] [last_Call-ID:] [last_CSeq:] to build response headers.
CRITICAL: This is UAS — NEVER use [field0], [field1], [field2] in any message.
CRITICAL: [last_Via:], [last_From:], [last_To:], [last_Call-ID:], [last_CSeq:], [last_Contact:] etc. EACH ALREADY EXPAND TO THE FULL HEADER LINE, including the header name and colon (e.g. [last_Via:] expands to the complete line "Via: SIP/2.0/UDP 1.2.3.4:5060;branch=..."). NEVER write the header name yourself in front of one of these keywords — "Via: [last_Via:]" is WRONG and produces a broken, doubled header ("Via: Via: ..."). Each of these keywords goes on its own line, by itself, with nothing in front of it. The ONLY exception: [last_To:] may have a literal ";tag=..." appended directly after it on the same line with no space (e.g. "[last_To:];tag=[call_number]") when the response needs to add this UAS's own tag — that is the one case where something follows the keyword on its line.
CRITICAL: Contact header is context-dependent — pick ONE of these two, never mix them:
  - REGISTER 200 OK only: the response should echo the registrant's OWN Contact back, so use the bare keyword alone on its own line: [last_Contact:] (no "Contact:" prefix — it already includes it, same rule as above).
  - Any INVITE-flow response (100/180/183/200 OK to a call, or any other response that is not to a REGISTER): build a FRESH Contact header yourself instead — write "Contact: <sip:[local_ip]:[local_port];transport=[transport]>" — this is YOUR OWN address as the answering UAS. Do NOT use [last_Contact:] here; that would incorrectly echo the caller's own address back to them.
For BYE use: BYE sip:[remote_ip]:[remote_port] SIP/2.0
Always use [last_Via:] [last_From:] [last_To:] [last_Call-ID:] [last_CSeq:] for all responses.

Common UAS patterns based on description:
- Answer call: recv INVITE → send 100 → send 180 → send 200 OK with SDP → recv ACK → pause → send BYE → recv 200
- Reject call: recv INVITE → send 486 or 503 or 404
- Early media: recv INVITE → send 100 → send 183 with SDP → pause → send 200 OK → recv ACK → pause → send BYE
- No answer/timeout: recv INVITE → send 100 → send 180 → pause long → send 486
- CANCEL handling: recv INVITE → send 100 → send 180 → recv CANCEL → send 200 for CANCEL → send 487 → recv ACK
- Register challenge (401/407): recv REGISTER → send 401 (or 407) with a WWW-Authenticate (or Proxy-Authenticate) header containing realm/nonce/algorithm → recv REGISTER (this is the UAC's authenticated retry — just receive it again, do NOT verify the Authorization header contents) → send 200 OK with Expires header matching whatever the retried REGISTER requested. Do not add Content-Type/SDP to any of these — REGISTER has no body.

SDP for 200 OK must include (choose the codec based on the terminating behavior description below — default to PCMU only if it doesn't specify one):
  o=user1 53655765 2353687637 IN IP4 [local_ip]
  c=IN IP4 [local_ip]
  m=audio [media_port] RTP/AVP [payload type — see table below]
  a=rtpmap:[payload type] [codec name/clock rate — see table below]

Codec table (use whichever the description names; default to PCMU if none named):
  - G.711 μ-law (PCMU) [default]: payload type 0, a=rtpmap:0 PCMU/8000
  - G.711 A-law (PCMA): payload type 8, a=rtpmap:8 PCMA/8000
  - G.722: payload type 9, a=rtpmap:9 G722/8000 — NOTE the well-known RFC 3551 quirk: G.722 actually operates at a 16kHz sample rate, but its SDP rtpmap clock rate is still written as 8000, not 16000. This is correct and intentional, not a typo.
  - G.729: payload type 18, a=rtpmap:18 G729/8000
  - Opus: dynamic payload type (typically 111), a=rtpmap:111 opus/48000/2 (48000 clock rate, 2 = stereo-capable per spec even for a mono call)

Use [last_Via:] [last_From:] [last_To:] [last_Call-ID:] [last_CSeq:] in response headers.
Only use <send>, <recv>, <pause>. NEVER <exec>, <action>, <nop>.
NEVER use optional="true" on consecutive recvs before a pause.`;

  try {
    let xml = (await llmGenerate(prompt_text, 1500)).trim();
    xml = xml.replace(/^```xml\s*/i,'').replace(/^```\s*/,'').replace(/```\s*$/,'').trim();
    if(ws.scripts[0]) ws.scripts[0].xml = xml;
    ws.scripts[0].ready = true;
    saveWorkspaces();  // Was: unlike the TX generation path, this never persisted the freshly-generated XML — lost on reload/timeout unless some unrelated later action happened to trigger a save.

    // update XML panel
    const rxXmlContent = document.getElementById('rx-xml-content');
    if(rxXmlContent) rxXmlContent.textContent = xml;
    const viewBtn = document.getElementById('rx-view-xml-btn');
    if(viewBtn) viewBtn.disabled = false;
    const saveBtn = document.getElementById('rx-save-btn');
    if(saveBtn) saveBtn.disabled = false;

    // update ready indicator
    const rdEl = document.getElementById('rx-ready-indicator');
    if(rdEl) rdEl.innerHTML = '<span style="color:#16a34a">✓ Ready</span>';

    addLog('RX scenario generated', 'ok');
  } catch(e) {
    addLog('RX generation failed: '+e.message, 'err');
  } finally {
    // reset button regardless of success/failure
    const btn = document.querySelector('button[onclick="generateRXScript()"]');
    if(btn) { btn.disabled=false; btn.textContent='✨ Generate RX scenario'; }
  }
}

function toggleRXMosScoring(checked) {
  if(!activeWsId) return;
  const ws = workspaces[activeWsId];
  if(!ws || !ws.scripts[0]) return;
  ws.scripts[0].enable_rtp = checked;
  saveWorkspaces();
}

async function loadRXScenario() {
  try{
    const r=await fetch('/scenarios/list/rx');
    const d=await r.json();
    if(!d.scenarios?.length){alert('No saved RX scenarios');return;}
    const name=prompt('Enter scenario name:\n'+d.scenarios.map(s=>s.name).join('\n'));
    if(!name) return;
    const found=d.scenarios.find(s=>s.name===name);
    if(!found){alert('Not found');return;}
    const lr=await fetch(`/scenarios/load/${found.filename}`);
    const ld=await lr.json();
    if(ld.xml && activeWsId && workspaces[activeWsId].scripts[0]){
      const s = workspaces[activeWsId].scripts[0];
      s.xml = ld.xml;
      s.ready = true;
      saveWorkspaces();
      const rxXmlContent = document.getElementById('rx-xml-content');
      if(rxXmlContent) rxXmlContent.textContent = ld.xml;
      const viewBtn = document.getElementById('rx-view-xml-btn');
      if(viewBtn) viewBtn.disabled = false;
      const saveBtn = document.getElementById('rx-save-btn');
      if(saveBtn) saveBtn.disabled = false;
      const rdEl = document.getElementById('rx-ready-indicator');
      if(rdEl) rdEl.innerHTML = '<span style="color:#16a34a">✓ Ready</span>';
      addLog('RX scenario loaded: '+ld.name,'ok');
    }
  }catch(e){addLog('Load error: '+e.message,'err');}
}

function toggleScript(id) {
  const body = document.getElementById(`s${id}-body`);
  if(body) body.classList.toggle('open');
}

// After a script gets its XML from somewhere other than Generate (a saved
// scenario or a script template): enable the XML buttons and show the XML.
function revealScriptXml(id) {
  const body = document.getElementById(`s${id}-body`);
  if(body) body.classList.add('open');
  const panel = document.getElementById(`s${id}-xml-panel`);
  if(panel) panel.style.display = 'block';
  const pre = document.getElementById(`s${id}-xml`);
  const s = getScript(id);
  if(pre && s) pre.textContent = s.xml || '';
  ['view','save'].forEach(k => {
    const b = document.getElementById(`s${id}-${k}-btn`);
    if(b) b.disabled = !(s && s.xml);
  });
}

function viewScriptXml(id) {
  const panel = document.getElementById(`s${id}-xml-panel`);
  if(panel) panel.style.display = panel.style.display==='none' ? 'block' : 'none';
}
