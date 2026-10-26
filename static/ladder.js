function renderLadder(containerId, calls, srcLabel, dstLabel, flipDirection=false, streamPresence=null) {
  const el = document.getElementById(containerId);
  if (!calls || Object.keys(calls).length === 0) {
    el.innerHTML = '<p style="color:#888;font-size:13px;padding:1rem">No messages found — run a test first</p>';
    return;
  }
  const callIds = Object.keys(calls);
  let html = `<div style="margin-bottom:12px;display:flex;align-items:center;gap:10px">
    <label style="font-size:12px;color:#888;font-weight:500">Select call</label>
    <select id="${escapeHtml(containerId)}_select" onchange="redrawLadder('${escapeHtml(containerId)}')"
      style="font-size:13px;padding:5px 10px;border:1px solid #e5e5e5;border-radius:6px;background:#fff">`;
  callIds.forEach((cid, i) => {
    const msgs = calls[cid] || [];
    const first = msgs[0] ? msgs[0].method : '';
    const tries = msgs.filter(m => m.direction === 'sent' && m.method === first).length;
    const answered = msgs.some(m => m.direction === 'received');
    const note = !answered && tries > 1 ? ` · no answer, ${tries} tries` : (tries > 1 ? ` · ${tries} tries` : '');
    html += `<option value="${escapeHtml(i)}">Call ${escapeHtml(i+1)} — ${escapeHtml(cid)}${escapeHtml(note)}</option>`;
  });
  html += `</select><span style="font-size:12px;color:#888">${callIds.length} call(s)</span></div>`;
  html += `<div id="${escapeHtml(containerId)}_svg"></div>`;
  html += `<div id="${escapeHtml(containerId)}_raw" style="display:none;margin-top:10px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
      <span style="font-size:12px;font-weight:500;color:#888" id="${escapeHtml(containerId)}_raw_title">Raw SIP</span>
      <button onclick="document.getElementById('${escapeHtml(containerId)}_raw').style.display='none'"
        style="font-size:11px;padding:3px 8px">Close</button>
    </div>
    <pre id="${escapeHtml(containerId)}_raw_content" style="font-size:11px;max-height:220px;overflow-y:auto"></pre>
  </div>`;
  el.innerHTML = html;
  el._calls = calls;
  el._callIds = callIds;
  el._srcLabel = srcLabel;
  el._dstLabel = dstLabel;
  el._flipDirection = flipDirection || false;
  el._streamPresence = streamPresence || {};
  redrawLadder(containerId);
}

function extractRTPInfo(msgs) {
  let origPort = null, termPort = null;
  let origCodec = 'PCMU', termCodec = 'PCMU';
  let origIp = null, termIp = null;

  msgs.forEach(msg => {
    const raw = msg.raw || '';
    const mAudio = raw.match(/m=audio\s+(\d+)/);
    const rtpmap = raw.match(/a=rtpmap:\d+\s+(\w+)/);
    const cLine  = raw.match(/c=IN IP4 (\d+\.\d+\.\d+\.\d+)/);
    const codec  = rtpmap ? rtpmap[1] : null;

    // INVITE sent — orig offering
    if(msg.method === 'INVITE' && msg.direction === 'sent' && mAudio) {
      origPort  = mAudio[1];
      if(codec) origCodec = codec;
      if(cLine) origIp = cLine[1];
    }
    // 200 OK received — term answering
    if(msg.method?.startsWith('200') && msg.direction === 'received' && mAudio) {
      termPort  = mAudio[1];
      if(codec) termCodec = codec;
      if(cLine) termIp = cLine[1];
    }
    // UAS perspective
    if(msg.method === 'INVITE' && msg.direction === 'received' && mAudio) {
      origPort  = mAudio[1];
      if(codec) origCodec = codec;
      if(cLine) origIp = cLine[1];
    }
    if(msg.method?.startsWith('200') && msg.direction === 'sent' && mAudio) {
      termPort  = mAudio[1];
      if(codec) termCodec = codec;
      if(cLine) termIp = cLine[1];
    }
  });

  return { origPort, termPort, origCodec, termCodec, origIp, termIp };
}

function findMessageY(msgs, method, direction, topPad, rowH) {
  const idx = msgs.findIndex(m => m.method === method && m.direction === direction);
  return idx >= 0 ? topPad + (idx * rowH) : null;
}

function redrawLadder(containerId) {
  const el = document.getElementById(containerId);
  const idx = parseInt(document.getElementById(containerId + '_select').value);
  const callId = el._callIds[idx];
  const msgs = el._calls[callId];
  const srcLabel = el._srcLabel || 'UAC';
  const dstLabel = el._dstLabel || 'UAS';
  const rowH = 54, topPad = 60, leftCol = 160, rightCol = 520;
  const midX = (leftCol + rightCol) / 2;
  const totalH = topPad + (msgs.length * rowH) + 120;
  let svg = `<svg width="680" height="${totalH}" xmlns="http://www.w3.org/2000/svg" font-family="system-ui,sans-serif">`;
  svg += `<defs>
    <marker id="arr-r-${escapeHtml(containerId)}" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#555"/>
    </marker>
  </defs>`;
  svg += `<line x1="${leftCol}" y1="40" x2="${leftCol}" y2="${totalH-20}" stroke="#e5e5e5" stroke-width="1.5"/>`;
  svg += `<line x1="${rightCol}" y1="40" x2="${rightCol}" y2="${totalH-20}" stroke="#e5e5e5" stroke-width="1.5"/>`;
  svg += `<rect x="${leftCol-70}" y="8" width="140" height="28" rx="6" fill="#1a1a1a"/>`;
  svg += `<text x="${leftCol}" y="27" text-anchor="middle" fill="#fff" font-size="12" font-weight="500">${escapeHtml(srcLabel)}</text>`;
  svg += `<rect x="${rightCol-70}" y="8" width="140" height="28" rx="6" fill="#1a1a1a"/>`;
  svg += `<text x="${rightCol}" y="27" text-anchor="middle" fill="#fff" font-size="12" font-weight="500">${escapeHtml(dstLabel)}</text>`;
  msgs.forEach((msg, i) => {
    const y = topPad + (i * rowH);
    const flip = el._flipDirection || false;
    const sent = flip ? msg.direction === 'received' : msg.direction === 'sent';
    const x1 = sent ? leftCol : rightCol;
    const x2 = sent ? rightCol : leftCol;
    const marker = sent ? `arr-r-${containerId}` : `arr-l-${containerId}`;
    let color = '#555';
    const m = msg.method;
    if(m === 'INVITE' || m === 'ACK' || m === 'BYE' || m === 'CANCEL') color = '#185FA5';
    else if(m.startsWith('180') || m.startsWith('183')) color = '#854F0B';
    else if(m.startsWith('200')) color = '#166534';
    else if(m.startsWith('4') || m.startsWith('5') || m.startsWith('6')) color = '#dc2626';
    const rawEsc = escapeHtml(msg.raw);  // goes into a data- attribute; read back via dataset.raw
    const cid = containerId;
    const ax1 = sent ? leftCol : rightCol;
    const ax2 = sent ? rightCol : leftCol;
    svg += `<line x1="${ax1}" y1="${y}" x2="${ax2}" y2="${y}" stroke="${escapeHtml(color)}" stroke-width="1.5" marker-end="url(#arr-r-${escapeHtml(containerId)})" style="cursor:pointer" onclick="showRaw('${escapeHtml(cid)}',this.dataset.raw,this.dataset.method)" data-raw="${rawEsc}" data-method="${escapeHtml(m)}"/>`;
    svg += `<circle cx="${midX}" cy="${y}" r="5" fill="${escapeHtml(color)}" style="cursor:pointer" onclick="showRaw('${escapeHtml(cid)}',this.dataset.raw,this.dataset.method)" data-raw="${rawEsc}" data-method="${escapeHtml(m)}"/>`;
    svg += `<rect x="${midX-52}" y="${y-17}" width="104" height="19" rx="4" fill="#f5f5f5" style="cursor:pointer" onclick="showRaw('${escapeHtml(cid)}',this.dataset.raw,this.dataset.method)" data-raw="${rawEsc}" data-method="${escapeHtml(m)}"/>`;
    // check if STIR/SHAKEN Identity header present in raw message
    const hasStir = msg.raw && msg.raw.includes('Identity:') && msg.raw.includes('ppt=shaken');
    let stirLabel = '';
    if(hasStir) {
      try {
        // extract JWT token from Identity header
        const identityMatch = msg.raw.match(/Identity:\s*([\w\-\.]+)/);
        if(identityMatch) {
          // decode JWT payload (second part)
          const parts = identityMatch[1].split('.');
          if(parts.length >= 2) {
            const payload = JSON.parse(atob(parts[1].replace(/-/g,'+').replace(/_/g,'/')));
            const attest = payload.attest || 'A';
            stirLabel = ` ✍️${attest}`;
          }
        }
      } catch(e) {
        stirLabel = ' ✍️?';
      }
    }
    const label = m + stirLabel;
    svg += `<text x="${midX}" y="${y-3}" text-anchor="middle" fill="${escapeHtml(color)}" font-size="12" font-weight="500" style="cursor:pointer" onclick="showRaw('${escapeHtml(cid)}',this.dataset.raw,this.dataset.method)" data-raw="${rawEsc}" data-method="${escapeHtml(m)}">${escapeHtml(label)}</text>`;
    if(msg.timestamp){
      const tsX = sent ? leftCol - 8 : rightCol + 8;
      const anchor = sent ? 'end' : 'start';
      svg += `<text x="${tsX}" y="${escapeHtml(y+4)}" text-anchor="${escapeHtml(anchor)}" fill="#bbb" font-size="10">${escapeHtml(msg.timestamp)}</text>`;
    }
  });
  // find ACK and BYE regardless of direction
  const ackIdx = msgs.findIndex(m => m.method === 'ACK');
  const byeIdx = msgs.findIndex(m => m.method === 'BYE');
  const ackY = ackIdx >= 0 ? topPad + (ackIdx * rowH) : null;
  const byeY = byeIdx >= 0 ? topPad + (byeIdx * rowH) : null;

  // ── RTP media flows ───────────────────────────────────────────
  const rtpInfo = extractRTPInfo(msgs);
  const presenceMap = el._streamPresence || {};
  const presence = presenceMap[callId] || null;
  const verified = !!presence;
  if(!verified) {
    console.warn(`[ladder] No PCAP-based stream presence for call "${callId}" — drawing RTP flows as unverified. streamPresence had ${Object.keys(presenceMap).length} call(s): ${Object.keys(presenceMap).join(', ') || '(none)'}`);
  }
  const hasOut = verified ? !!presence.hasOut : null;  // null = unverified, not "true"
  const hasIn  = verified ? !!presence.hasIn  : null;

  if(ackY && byeY && rtpInfo.origPort) {
    const midY = (ackY + byeY) / 2;
    const barSpan = Math.min((byeY - ackY) * 0.6, 80);
    const barY1 = midY - barSpan / 2;
    const barY2 = midY + barSpan / 2;
    const barH  = barY2 - barY1;
    const barX1 = leftCol + 5;
    const barX2 = rightCol - 5;
    const midX2 = (barX1 + barX2) / 2;

    if(barH > 8) {
      const txY = barY1 + barH * 0.3;
      const rxY = barY1 + barH * 0.7;

      // TX flow — orig to term
      const mismatch = rtpInfo.origCodec !== rtpInfo.termCodec;
      // Three real states, not two: verified-real (packets actually
      // seen), verified-negotiated-only (SDP said so, but zero packets
      // ever captured for this direction), and unverified (we simply
      // don't have PCAP-based data to check against, e.g. Call Quality
      // hasn't loaded or a fetch failed). Collapsing "unverified" into
      // either of the other two was the actual bug reported after the
      // first pass of this fix — it silently looked identical to
      // "verified-real" whenever the lookup came up empty for any
      // reason, reproducing the exact false-positive under a new cause.
      const flowStyle = (state) => {
        if(state === true)  return { suffix: '', color: mismatch ? '#dc2626' : '#185FA5', fill: '#f0f7ff', stroke: '#bae6fd', text: '#0C447C' };
        if(state === false) return { suffix: ' (negotiated — no packets captured)', color: '#aaa', fill: '#f5f5f5', stroke: '#ddd', text: '#888' };
        return { suffix: ' (directionality unverified)', color: '#93a5c4', fill: '#f7f8fa', stroke: '#dde3ec', text: '#6b7a8f' };
      };
      const txStyle = flowStyle(hasOut);
      const txLabel = `RTP/${rtpInfo.origCodec}  ${rtpInfo.origIp||srcLabel}:${rtpInfo.origPort}${txStyle.suffix}`;
      const txColor = txStyle.color;
      svg += `<line x1="${barX1}" y1="${txY}" x2="${barX2-10}" y2="${txY}"
        stroke="${escapeHtml(txColor)}" stroke-width="2.5" stroke-dasharray="7,3"
        style="cursor:pointer" onclick="rtpBarClick('tx')"/>`;
      svg += `<polygon points="${barX2-2},${txY} ${barX2-12},${txY-5} ${barX2-12},${escapeHtml(txY+5)}"
        fill="${escapeHtml(txColor)}"/>`;
      // label box TX
      const txLabelW = txLabel.length * 6.2;
      const txLabelX = midX2 - txLabelW/2;
      svg += `<rect x="${txLabelX-4}" y="${txY-14}" width="${escapeHtml(txLabelW+8)}" height="16"
        rx="3" fill="${escapeHtml(txStyle.fill)}" stroke="${escapeHtml(txStyle.stroke)}" stroke-width="0.5"/>`;
      svg += `<text x="${midX2}" y="${txY-3}"
        text-anchor="middle" fill="${escapeHtml(txStyle.text)}" font-size="10" font-weight="500">${escapeHtml(txLabel)}</text>`;

      // RX flow — term to orig
      const rxStyle = flowStyle(hasIn);
      const rxLabel = `RTP/${rtpInfo.termCodec}  ${rtpInfo.termIp||dstLabel}:${rtpInfo.termPort||'?'}${rxStyle.suffix}`;
      const rxColor = rxStyle.color;
      svg += `<line x1="${barX2}" y1="${rxY}" x2="${escapeHtml(barX1+10)}" y2="${rxY}"
        stroke="${escapeHtml(rxColor)}" stroke-width="2.5" stroke-dasharray="7,3"
        style="cursor:pointer" onclick="rtpBarClick('rx')"/>`;
      svg += `<polygon points="${escapeHtml(barX1+2)},${rxY} ${escapeHtml(barX1+12)},${rxY-5} ${escapeHtml(barX1+12)},${escapeHtml(rxY+5)}"
        fill="${escapeHtml(rxColor)}"/>`;
      // label box RX
      const rxLabelW = rxLabel.length * 6.2;
      const rxLabelX = midX2 - rxLabelW/2;
      svg += `<rect x="${rxLabelX-4}" y="${rxY-14}" width="${escapeHtml(rxLabelW+8)}" height="16"
        rx="3" fill="${escapeHtml(rxStyle.fill)}" stroke="${escapeHtml(rxStyle.stroke)}" stroke-width="0.5"/>`;
      svg += `<text x="${midX2}" y="${rxY-3}"
        text-anchor="middle" fill="${escapeHtml(rxStyle.text)}" font-size="10" font-weight="500">${escapeHtml(rxLabel)}</text>`;

      // duration marker on left
      try {
        const ackIdx = msgs.findIndex(m=>m.method==='ACK' && m.direction==='sent');
        const byeIdx = msgs.findIndex(m=>m.method==='BYE' && m.direction==='sent');
        if(ackIdx >= 0 && byeIdx >= 0 && msgs[ackIdx].timestamp && msgs[byeIdx].timestamp) {
          const toMs = ts => {
            const p = ts.split(':');
            const [s,ms] = p[2].split('.');
            return (parseInt(p[0])*3600 + parseInt(p[1])*60 + parseInt(s))*1000 + parseInt((ms||'0').padEnd(3,'0'));
          };
          const dur = ((toMs(msgs[byeIdx].timestamp) - toMs(msgs[ackIdx].timestamp))/1000).toFixed(1);
          svg += `<line x1="${leftCol-12}" y1="${barY1}" x2="${leftCol-12}" y2="${barY2}"
            stroke="#bae6fd" stroke-width="1.5"/>`;
          svg += `<line x1="${leftCol-16}" y1="${barY1}" x2="${leftCol-8}" y2="${barY1}"
            stroke="#bae6fd" stroke-width="1"/>`;
          svg += `<line x1="${leftCol-16}" y1="${barY2}" x2="${leftCol-8}" y2="${barY2}"
            stroke="#bae6fd" stroke-width="1"/>`;
          svg += `<text x="${leftCol-22}" y="${escapeHtml(barY1 + barH/2 + 4)}"
            text-anchor="middle" fill="#185FA5" font-size="9"
            transform="rotate(-90,${leftCol-22},${escapeHtml(barY1 + barH/2)})">${escapeHtml(dur)}s</text>`;
        }
      } catch(e){}

      if(mismatch) {
        svg += `<rect x="${barX1}" y="${escapeHtml(barY2+4)}" width="${barX2-barX1}" height="16"
          rx="3" fill="#fef2f2" stroke="#fca5a5" stroke-width="0.5"/>`;
        svg += `<text x="${midX2}" y="${escapeHtml(barY2+15)}"
          text-anchor="middle" fill="#dc2626" font-size="10" font-weight="500">&#9888; Codec mismatch: ${escapeHtml(rtpInfo.origCodec)} offered / ${escapeHtml(rtpInfo.termCodec)} answered</text>`;
      }
    }
  }
  svg += '</svg>';
  document.getElementById(containerId + '_svg').innerHTML = svg;
}

function showRaw(containerId, raw, method) {
  // support both new UI (hardcoded IDs) and legacy
  const titleEl   = document.getElementById('ladder-raw-title') ||
                    document.getElementById(containerId + '_raw_title');
  const contentEl = document.getElementById('ladder-raw-content') ||
                    document.getElementById(containerId + '_raw_content');
  const panelEl   = document.getElementById('ladder-raw-panel') ||
                    document.getElementById(containerId + '_raw');

  if(titleEl)   titleEl.textContent   = 'Raw SIP — ' + method;
  if(contentEl) contentEl.textContent = raw;
  if(panelEl)   panelEl.style.display = 'block';
}
