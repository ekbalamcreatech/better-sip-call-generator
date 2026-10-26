// ═══════════════════════════════════════════════════════════════════════════════
// AI GENERATION
// ═══════════════════════════════════════════════════════════════════════════════
async function generateScript(id) {
  const s = getScript(id);
  if(!s) return;

  // Fetched fresh here rather than relying on a cached global from the
  // separate STIR/SHAKEN Config tab — that tab's loadStirInfo() only runs
  // if the user has actually opened it, which isn't guaranteed before
  // generating a script that needs this value.
  let stirCertUrl = '';
  if(s.stir_enabled){
    try{
      const cr = await fetch('/stir/info');
      const cd = await cr.json();
      stirCertUrl = cd.cert_url || '';
    }catch(e){}
  }

  const desc = document.getElementById(`s${id}-desc`)?.value.trim() ||
    `Basic SIP call at ${s.cps} CPS, UAC hangs up`;

  const btn = document.getElementById(`s${id}-gen-btn`);
  if(btn){ btn.disabled=true; btn.textContent='Generating...'; }

  const codec = s.codec || 'PCMU';
  const codecPayload = codec==='PCMU'?'0':codec==='PCMA'?'8':'18';
  const codecName    = codec==='PCMU'?'PCMU/8000':codec==='PCMA'?'PCMA/8000':'G729/8000';
  const dtmfNote = s.dtmf_enabled && s.dtmf_digits
    ? `After ACK, send DTMF digits "${s.dtmf_digits}" using RFC 2833 telephone-event payload type 101, ${s.dtmf_gap_ms}ms inter-digit gap.`
    : '';

  const prompt = `You are a SIPp expert. Generate a complete valid SIPp UAC scenario file.

Test description: "${desc}"
Originating IP: ${s.orig_ip}
SUT IP: ${s.sut_ip}:${s.sut_port}
SIP source port: ${s.sip_port}
CPS: ${s.cps}
Duration: ${s.duration_ms}ms
Codec default: ${codec} (payload type ${codecPayload}) — this is the workspace's configured Audio-tab default, used ONLY if the description below doesn't request a specific codec. If the description explicitly names a codec (e.g. "use G.722", "use Opus", "G.729 call"), use THAT instead, with its correct standard payload type and clock rate, not the default above:
  - G.711 μ-law (PCMU): payload type 0, a=rtpmap:0 PCMU/8000
  - G.711 A-law (PCMA): payload type 8, a=rtpmap:8 PCMA/8000
  - G.722: payload type 9, a=rtpmap:9 G722/8000 — NOTE the well-known RFC 3551 quirk: G.722 actually operates at a 16kHz sample rate, but its SDP rtpmap clock rate is still written as 8000, not 16000. This is correct and intentional, not a typo.
  - G.729: payload type 18, a=rtpmap:18 G729/8000
  - Opus: dynamic payload type (typically 111), a=rtpmap:111 opus/48000/2 (48000 clock rate, 2 = stereo-capable per spec even for a mono call)
${dtmfNote}

Output ONLY raw XML. No markdown, no backticks, no explanation.
Start with: <?xml version="1.0" encoding="ISO-8859-1" ?>
Use <scenario name="..."> structure.
Include INVITE, 100/180 (optional recv), 200 OK, ACK, pause, BYE.
Use <pause milliseconds="${s.duration_ms}"/> for call duration before BYE.
${s.called.includes('@') ?
`INVITE URI: INVITE sip:[field1] SIP/2.0
To: <sip:[field1]>
From: <sip:[field0]@[local_ip]:[local_port]>;tag=[call_number]
Contact: <sip:[field0]@[local_ip]:[local_port]>
The Request-URI and To header use [field1] directly with NO additional @host since the number already contains a domain.` :
`INVITE URI: INVITE sip:[field1]@[remote_ip]:[remote_port] SIP/2.0
To: <sip:[field1]@[remote_ip]:[remote_port]>
From: <sip:[field0]@[local_ip]:[local_port]>;tag=[call_number]
Contact: <sip:[field0]@[local_ip]:[local_port]>`}
SDP must include (using the codec actually selected above — default or description-requested):
  o=user1 53655765 2353687637 IN IP4 [local_ip]
  c=IN IP4 [local_ip]
  m=audio [media_port] RTP/AVP [payload type from the codec you selected]
  a=rtpmap:[payload type] [codec name/clock rate from the table above, e.g. "PCMU/8000" or "G722/8000" or "opus/48000/2"]
${s.enable_rtp ?
  `Use <pause milliseconds="${s.duration_ms}"/> as the default call duration (this reflects the configured Audio settings — plays × duration each). However, if the description EXPLICITLY states a call duration or hold time before hang-up (e.g. "10 seconds", "hang up after 30 seconds", "hold for 2 minutes"), use that value instead — convert to milliseconds and use it in place of ${s.duration_ms}. An explicitly-stated duration in the description always takes priority over the Audio-settings-derived value, even with RTP/MOS scoring enabled. (Operator note: the RTP sender itself still runs for the Audio-settings duration independent of this XML — if the explicit description duration is shorter, the call will hang up before the configured audio finishes playing, which cuts the RTP stream off mid-stream rather than lengthening the call to match it.)` :
  `Use <pause milliseconds="${s.duration_ms}"/> as the default call duration, but if the description specifies a different duration (e.g. "10 seconds", "30 second call"), use that instead.`
}
Only use <send>, <recv>, <pause>. NEVER <exec>, <action>, <nop>, <ResponseTime>. EXCEPTION: if and only if the description involves REFER / call transfer, you MAY also use <label>, <nop>, and <action> containing <ereg> and <test> — but ONLY for the specific REFER NOTIFY-handling pattern described below. Do not use these constructs for any other scenario type, and do not invent other uses for them even within a REFER scenario.
CRITICAL: [field0]=calling number, [field1]=called number${s.auth_enabled ? ', [field2]=a pre-built [authentication...] keyword string (see Authentication rule below)' : ''}${s.stir_enabled ? ', [field3]=a pre-built per-call PASSporT JWT token (see STIR/SHAKEN rule below)' : ''}. NEVER hardcode numbers.${s.stir_enabled ? `
CRITICAL: STIR/SHAKEN is ENABLED for this script. [field3] (from the CSV injection file) already contains a complete, correctly-computed PASSporT JWT for THIS SPECIFIC call — a fresh token per call, not one reused value, since each call in a range/volume test has its own calling/called number and needs its own correctly-scoped attestation. You never compute or write the JWT yourself. Add exactly ONE header line, immediately after the Max-Forwards line in the INVITE:
  Identity: [field3];info=<${stirCertUrl}>;alg=ES256;ppt=shaken
  Everything after [field3] in that line (the ;info=<...>;alg=ES256;ppt=shaken part) is fixed, identical boilerplate for every call — write it exactly as shown, literally, do not template or vary it. Only [field3] itself varies per call, and that variation is handled for you by the CSV substitution — you don't need to do anything else.` : ''}
CRITICAL: [peer_tag_param] ALREADY includes its own leading semicolon and "tag=" (it expands to something like ";tag=abc123"). NEVER prepend an additional semicolon before it. Correct: ">[peer_tag_param]". WRONG: ">;[peer_tag_param]" (this produces a double-semicolon and a malformed header). This applies to [peer_tag_param] anywhere it appears — in ACK, BYE, REFER, re-INVITE, or any other message that needs to reference the remote party's dialog tag, not just one specific message type.
CRITICAL: NEVER concatenate literal text directly onto the [call_id] keyword (e.g. "reg-[call_id]", "call-[call_id]"). Always write [call_id] by itself, completely unmodified, as the entire Call-ID header value. This has caused a real, reproduced bug: prefixing literal text onto [call_id] makes SIPp unable to correlate the response back to its request, so the original send's retransmission timer keeps firing on exponential backoff (500ms, 1s, 2s, 4s...) even though a valid response clearly arrives every time — the scenario never advances. If a scenario has both a REGISTER and a later INVITE and you want them to feel logically distinct, that's fine — but do it by NOT giving them a shared variable name or anything else; simply use plain [call_id] for both. REGISTER does not create a dialog (per RFC 3261), so there is no protocol requirement for it to have a separate Call-ID from a later INVITE in the same scenario file — sharing the same [call_id] across both is correct, not a bug.
CRITICAL: NEVER use optional="true" on two consecutive recv before a pause or send.
CRITICAL: For CANCEL — recv 100 optional, recv 180 MANDATORY, then pause, then CANCEL.
CRITICAL: A pause must be preceded by at least one mandatory recv or send.
CRITICAL: If the description asks for HOLD, RESUME, or a RE-INVITE (mid-call SDP change), follow these exact dialog rules:
  - Re-INVITE uses the SAME [call_id] as the original INVITE — never generate a new Call-ID.
  - Re-INVITE's To header MUST include [peer_tag_param] (same as the ACK after the original 200 OK) — the remote tag never changes for the life of the dialog.
  - CSeq numbering is a single incrementing counter for ALL requests this UAC sends in the dialog (INVITE, re-INVITE, BYE) — NOT per-method. Example: INVITE=1, ACK=1 (matches INVITE), re-INVITE(hold)=2, ACK=2 (matches), re-INVITE(resume)=3, ACK=3 (matches), BYE=4. Each ACK shares its corresponding INVITE/re-INVITE's CSeq number, never its own.
  - HOLD re-INVITE's SDP body must include "a=sendonly" (instead of a=sendrecv) on the audio line.
  - RESUME re-INVITE's SDP body must include "a=sendrecv" to restore normal two-way audio.
  - Each re-INVITE must <recv response="200" retrans="500"> before sending its matching ACK.
  - Use <pause milliseconds="..."/> between hold and resume as specified in the description (default 3000ms if unspecified).
CRITICAL: If the description involves REFER / call transfer, follow this exact structure (uses the <label>/<nop>/<action> exception above):
  - Send REFER with the SAME [call_id] and [peer_tag_param] as the established dialog, CSeq continuing the same single incrementing counter (see the CSeq rule above — REFER and any later BYE are just more requests in that same counter). Include Refer-To and Referred-By headers. Expect <recv response="202"> as a MANDATORY recv (REFER is acknowledged with 202 Accepted, not 200 OK).
  - The FIRST NOTIFY is MANDATORY — it normally carries an early-progress sipfrag (e.g. "SIP/2.0 100 Trying" or "SIP/2.0 180 Ringing"). Extract its sipfrag status code, then respond 200 OK to it:
      <recv request="NOTIFY">
        <action>
          <ereg regexp="SIP/2\\.0 ([0-9]{3})" search_in="body" assign_to="dummy,refer_status"/>
        </action>
      </recv>
      <send>
        <![CDATA[
          SIP/2.0 200 OK
          [last_Via:]
          [last_From:]
          [last_To:]
          [last_Call-ID:]
          [last_CSeq:]
          Content-Length: 0
        ]]>
      </send>
  - A SECOND NOTIFY (the final-outcome one) is OPTIONAL and may arrive at any point shortly after the first — give it an explicit timeout and branch cleanly on whether it actually showed up, rather than assuming it will and rather than letting an unconditional <send> fire if it never does (an optional <recv> that doesn't match does NOT block the next element from running, so a careless "optional recv, then unconditional send" pair would send a stray response with no real NOTIFY behind it):
      <recv request="NOTIFY" optional="true" timeout="5000" ontimeout="refer_notify_done" next="refer_notify2_got">
        <action>
          <ereg regexp="SIP/2\\.0 ([0-9]{3})" search_in="body" assign_to="dummy,refer_status"/>
        </action>
      </recv>
      <label id="refer_notify2_got"/>
      <send>
        <![CDATA[
          SIP/2.0 200 OK
          [last_Via:]
          [last_From:]
          [last_To:]
          [last_Call-ID:]
          [last_CSeq:]
          Content-Length: 0
        ]]>
      </send>
      <label id="refer_notify_done"/>
    Each ereg above re-assigns the SAME "refer_status" variable, so by the time both NOTIFYs (or just the mandatory one, if the second never arrives) have been processed, "refer_status" holds whichever sipfrag code arrived LAST — which is the actual final outcome of the transfer.
  - Only send BYE if the transfer actually succeeded — never send it unconditionally. Check refer_status first:
      <nop>
        <action>
          <test assign_to="refer_ok" variable="refer_status" compare="equal" value="200"/>
        </action>
      </nop>
      <nop next="refer_succeeded" test="refer_ok"/>
      <!-- falls through to here only if refer_status was NOT "200" -->
      <nop next="refer_end"/>
      <label id="refer_succeeded"/>
      <send retrans="500">
        <![CDATA[
          BYE sip:[remote_ip]:[remote_port] SIP/2.0
          Via: SIP/2.0/[transport] [local_ip]:[local_port];branch=[branch]
          From: <sip:[field0]@[local_ip]:[local_port]>;tag=[call_number]
          To: <sip:[field1]@[remote_ip]:[remote_port]>[peer_tag_param]
          Call-ID: [call_id]
          CSeq: [cseq] BYE
          Max-Forwards: 70
          Content-Length: 0
        ]]>
      </send>
      <recv response="200"/>
      <label id="refer_end"/>
    Do NOT send BYE in the failed/unknown-outcome branch — per RFC behavior and real PBX implementations (Asterisk, FreeSWITCH), a failed transfer means the original call is still up; ending the scenario there without a BYE is the protocol-correct choice, not an oversight.
  - This checks for exactly status "200" specifically (not a general 2xx range) — real implementations overwhelmingly use exactly 200 for a successfully connected transferred call, and this keeps the check simple rather than building a full 2xx-range match.
  - IMPORTANT: this REFER pattern is built from documented SIPp constructs but has not been validated against a live test as of this writing. Generate it carefully and exactly as structured above — do not improvise variations on the branching mechanics (label names, next/test/ontimeout wiring, or the order of elements).${s.auth_enabled ? `
CRITICAL: Authentication is ENABLED for this script. [field2] (from the CSV injection file) already contains a complete, pre-built "[authentication username=... password=...]" keyword string — you never see or write the actual username/password, and you never write out "[authentication username=..." yourself. Follow this exact challenge/response flow:
  - Send the scenario's primary request first (REGISTER, or the initial INVITE if this is a call scenario) with NO Authorization or Proxy-Authorization header. Add start_txn="auth_initial" to this <send> — e.g. <send retrans="500" start_txn="auth_initial">. This is REQUIRED, not optional decoration: without it, SIPp falls back to matching responses by CSeq+method alone, which the SIPp docs themselves call "imprecise" — in practice this can cause the retrans timer on this send to keep firing every "retrans" milliseconds even after the 401/407 has clearly arrived, because the engine never registers that this specific transaction was satisfied. This is a real, reproduced failure mode, not a theoretical one.
  - Immediately after that <send>, add exactly these two recv elements, then a label, in this order:
      <recv response="401" optional="true" auth="true" response_txn="auth_initial" next="auth_retry"/>
      <recv response="407" auth="true" response_txn="auth_initial" next="auth_retry"/>
      <label id="auth_retry"/>
    auth="true" on BOTH is REQUIRED — without it SIPp cannot capture the realm/nonce needed to compute the retry's credentials. response_txn="auth_initial" on BOTH is ALSO REQUIRED — it ties these two recv elements to the exact transaction started above, which is what actually lets SIPp recognize the challenge as resolving that send and stop retransmitting it. This satisfies the "one mandatory recv" rule above (the 401 is optional, the 407 is mandatory).
  - This scenario assumes the SUT WILL challenge the request (Authentication is explicitly enabled for this test) — do NOT add a separate "accepted without a challenge" branch before the label.
  - After the label, re-send the EXACT SAME request type, with the SAME Call-ID, To, and From as the first attempt, but CSeq incremented by exactly 1 from the first attempt (e.g. first attempt CSeq=1, retry CSeq=2 — this is the same single-incrementing-counter rule as the re-INVITE rule above; auth retries are not an exception). Add exactly one new header line containing only [field2] (on its own line, nothing else on that line) — this expands into the full Authorization or Proxy-Authorization header automatically.
  - Add a MANDATORY <recv response="200"> immediately after the retried request to confirm success.
  - If the retried request is an INVITE rather than REGISTER, continue the rest of the call flow (ACK, pause, BYE, etc.) normally after this point exactly as an unauthenticated call would — the challenge/retry only ever applies to the FIRST request of the dialog, never to subsequent requests like BYE.` : ''}`;

  try {
    let xml = (await llmGenerate(prompt, 3500)).trim();
    xml = xml.replace(/^```xml\s*/i,'').replace(/^```\s*/,'').replace(/```\s*$/,'').trim();
    // REFER scenarios legitimately need <nop>/<action> (sipfrag-status branching) — only
    // strip these as a safety net for every other scenario type, where they're never wanted.
    const isReferScenario = /\bREFER\b/.test(xml);
    if (!isReferScenario) {
      xml = xml.replace(/<nop>[\s\S]*?<\/nop>/gi,'').replace(/<action>[\s\S]*?<\/action>/gi,'');
    }
    xml = xml.replace(/<ResponseTime[^>]*\/>/gi,'');

    s.xml = xml; s.ready = true;
    const xmlEl = document.getElementById(`s${id}-xml`);
    if(xmlEl) xmlEl.textContent = xml;
    const viewBtn = document.querySelector(`button[onclick="viewScriptXml(${id})"]`);
    if(viewBtn) viewBtn.disabled = false;
    const rdEl = document.getElementById(`s${id}-ready`);
    if(rdEl) rdEl.innerHTML = '<span style="color:#16a34a">✓ Ready</span>';
    const dot = document.getElementById(`s${id}-dot`);
    if(dot) dot.style.background = '#4ade80';
    addLog(`Script ${id} scenario generated`, 'ok');
    updateStartBtn();
    saveWorkspaces();
  } catch(e) {
    addLog(`Script ${id} generation failed: ${e.message}`, 'err');
  }

  if(btn){ btn.disabled=false; btn.textContent='✨ Generate'; }
}
