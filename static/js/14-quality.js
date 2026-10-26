// ═══════════════════════════════════════════════════════════════════════════════
// CALL QUALITY
// ═══════════════════════════════════════════════════════════════════════════════
async function loadCallQuality() {
  if(!activeWsId) return;

  // populate and read script selector
  const qsel = document.getElementById('quality-script-select');
  if(qsel) {
    const ws = workspaces[activeWsId];
    if(!qsel.options.length || qsel.dataset.wsId !== String(activeWsId)) {
      qsel.innerHTML = ws.scripts.map(s =>
        `<option value="${escapeHtml(s.id)}">Script ${escapeHtml(s.id)} — ${escapeHtml(s.sut_name)}</option>`
      ).join('');
      qsel.dataset.wsId = String(activeWsId);
    }
  }
  const sid = parseInt(qsel?.value)||1;

  try {
    const r  = await fetch(`/quality/${activeWsId}?script_id=${sid}`);
    const d  = await r.json();
    const calls = d.calls||[];

    const tableEl = document.getElementById('quality-table');
    const summEl  = document.getElementById('quality-summary');

    const completed = calls.filter(c=>c.status==='completed').length;
    const failed    = calls.filter(c=>c.status==='failed').length;
    const avgDur    = calls.length>0
      ? (calls.reduce((s,c)=>s+(c.duration_s||0),0)/calls.length).toFixed(1) : 0;

    summEl.textContent = `Script ${sid} — ${calls.length} calls, ${completed} completed, ${failed} failed, avg ${avgDur}s`;

    if(!calls.length){
      tableEl.innerHTML='<p style="color:#888;font-size:13px;padding:8px">No call data — run a test first</p>';
      return;
    }
    tableEl.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead>
          <tr style="border-bottom:1px solid #e5e5e5;background:#fafafa">
            ${['Call ID','Status','Duration','Jitter','Loss','MOS','Codec','Error','Play'].map(h=>
              `<th style="text-align:left;padding:8px 10px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.04em">${escapeHtml(h)}</th>`
            ).join('')}
          </tr>
        </thead>
        <tbody>
          ${calls.map(c => {
            const outStream = (c.streams||[]).find(s => s.direction === 'out');
            const inStream  = (c.streams||[]).find(s => s.direction === 'in');
            const q = outStream?.quality || inStream?.quality || {};
            const mosColor = q.mos>=4.0?'#16a34a':q.mos>=3.5?'#f59e0b':q.mos?'#dc2626':'#888';
            return `
            <tr style="border-bottom:1px solid #f5f5f5;cursor:pointer"
                onmouseover="this.style.background='#fafafa'" onmouseout="this.style.background=''"
                data-call-id="${escapeHtml(c.call_id)}" onclick="jumpToCall(this.dataset.callId, ${escapeHtml(sid)})">
              <td style="padding:7px 10px;font-family:monospace;font-size:11px;color:#555">${escapeHtml(c.call_id.split('@')[0])}</td>
              <td style="padding:7px 10px">
                <span style="padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;background:${c.status==='completed'?'#dcfce7':'#fee2e2'};color:${c.status==='completed'?'#16a34a':'#dc2626'}">${escapeHtml(c.status.toUpperCase())}</span>
              </td>
              <td style="padding:7px 10px">${escapeHtml(c.duration_s?c.duration_s+'s':'—')}</td>
              <td style="padding:7px 10px">${escapeHtml(q.jitter_avg_ms!==undefined?q.jitter_avg_ms+'ms':'—')}</td>
              <td style="padding:7px 10px">${escapeHtml(q.packet_loss_pct!==undefined?q.packet_loss_pct+'%':'—')}</td>
              <td style="padding:7px 10px;font-weight:500;color:${escapeHtml(mosColor)}">${escapeHtml(q.mos||'—')}</td>
              <td style="padding:7px 10px;font-size:11px">${escapeHtml(q.codec||'—')}</td>
              <td style="padding:7px 10px;color:#dc2626;font-size:11px">${escapeHtml(c.error_code||'—')}</td>
              <td style="padding:7px 10px">
                ${outStream?`<button onclick="event.stopPropagation();playRTPStream('${escapeHtml(outStream.ssrc)}','out')" style="padding:3px 7px;font-size:11px">▶TX</button>`:''}
                ${inStream?`<button onclick="event.stopPropagation();playRTPStream('${escapeHtml(inStream.ssrc)}','in')" style="padding:3px 7px;font-size:11px;margin-left:3px">▶RX</button>`:''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  } catch(e) { console.error('Quality error:',e); }
}

function jumpToCall(callId, scriptId) {
  // switch to ladder tab
  showContentTab('ladder');

  // set correct script in dropdown
  const sel = document.getElementById('ladder-script-select');
  if(sel && scriptId) {
    sel.value = scriptId;
  }

  // load ladder then select the correct call
  loadLadder().then(() => {
    const callSel = document.getElementById('ladder-container-svg_select');
    if(callSel) {
      // find the option matching this call ID
      const opts = Array.from(callSel.options);
      const match = opts.find(o => o.text.includes(callId.split('@')[0]));
      if(match) {
        callSel.value = match.value;
        callSel.dispatchEvent(new Event('change'));
      }
    }
  });
}

async function playRTPStream(ssrc, direction) {
  if(!activeWsId) return;
  const playerEl = document.getElementById('ws-audio-player');
  const audioEl  = document.getElementById('ws-audio-elem');
  const labelEl  = document.getElementById('ws-player-label');
  labelEl.textContent = `Loading ${direction==='out'?'TX outbound':'RX inbound'} audio...`;
  playerEl.style.display = 'block';
  audioEl.src = `/rtp/play/${activeWsId}/${ssrc}`;
  audioEl.load();
  try { await audioEl.play(); } catch(e){}
  labelEl.textContent = `${direction==='out'?'▶ TX Outbound':'▶ RX Inbound'} — SSRC: ${ssrc}`;
}

function rtpBarClick(direction) {
  fetch(`/rtp/streams/${activeWsId}`)
    .then(r=>r.json())
    .then(d=>{
      const streams = d.streams||[];
      const wsIp = workspaces[activeWsId]?.ip||'127.0.0.1';
      const stream = direction==='tx'
        ? streams.find(s=>s.src.includes(wsIp))
        : streams.find(s=>s.dst.includes(wsIp));
      if(stream){
        showContentTab('quality');
        loadCallQuality().then(()=>playRTPStream(stream.ssrc, direction));
      } else {
        addLog('No RTP stream — run test with RTP enabled','err');
      }
    }).catch(e=>addLog('RTP error: '+e.message,'err'));
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXPORT — PCAP download + PDF test-run report
// Client-side only (jsPDF + jsPDF-AutoTable, loaded in <head>). The PDF is built
// from data the app already has: workspace totals, SIP stats and Call Quality.
// ═══════════════════════════════════════════════════════════════════════════════
function exportPCAP() {
  if(!activeWsId) return;
  const sid = parseInt(document.getElementById('pcap-script-select')?.value)||1;
  const a = document.createElement('a');
  a.href = `/pcap/${activeWsId}?script_id=${sid}&t=${Date.now()}`;
  a.download = `sipp_ws${activeWsId}_script${sid}_capture.pcap`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

function _pdfHeader(doc, title, subLines) {
  const margin = 14;
  let y = 18;
  doc.setFontSize(16); doc.setFont(undefined,'bold'); doc.setTextColor(20);
  doc.text(title, margin, y); y += 8;
  doc.setFontSize(10); doc.setFont(undefined,'normal'); doc.setTextColor(120);
  subLines.forEach(line => { doc.text(line, margin, y); y += 6; });
  doc.setDrawColor(230); doc.line(margin, y, 196, y); y += 8;
  return y;
}

function _pdfBreak(doc, y, needed) {
  if(y + needed > 280){ doc.addPage(); return 18; }
  return y;
}

function _pdfSection(doc, y, label) {
  y = _pdfBreak(doc, y, 24);
  doc.setFontSize(11); doc.setFont(undefined,'bold'); doc.setTextColor(20);
  doc.text(label, 14, y);
  doc.setFont(undefined,'normal');
  return y + 4;
}

async function exportReportPDF() {
  if(!activeWsId){ alert('Select a workspace first.'); return; }
  if(!window.jspdf){ alert('PDF library did not load.'); return; }
  const btn = document.getElementById('export-pdf-btn');
  if(btn) btn.disabled = true;
  try {
    const ws = workspaces[activeWsId] || {};
    const sid = parseInt(document.getElementById('pcap-script-select')?.value)||1;
    const script = (ws.scripts||[]).find(s => s.id === sid) || ws.scripts?.[0] || {};
    const stats = ws.stats || {};
    const note = (document.getElementById('export-notes')?.value || '').trim();

    const [qr, sr] = await Promise.all([
      fetch(`/quality/${activeWsId}?script_id=${sid}`).then(r=>r.json()).catch(()=>({})),
      fetch(`/sipstats/${activeWsId}?script_id=${sid}`).then(r=>r.json()).catch(()=>({}))
    ]);
    const calls = qr.calls || [];
    const avg = a => a.length ? a.reduce((x,y)=>x+y,0)/a.length : null;
    const fmt = (v,d=2) => (v===null||v===undefined) ? '—' : (+v).toFixed(d);
    const mosVals = calls.map(c=>c.mos).filter(v=>v!==null&&v!==undefined);
    const lossVals = calls.map(c=>c.packet_loss_pct).filter(v=>v!==null&&v!==undefined);
    const durVals = calls.map(c=>c.duration_s).filter(Boolean);

    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    let y = _pdfHeader(doc, 'SIP Test Run Report', [
      `Generated ${new Date().toLocaleString()}`,
      `Workspace ${activeWsId} (${(ws.role||'tx').toUpperCase()})   Script ${sid}   Target: ${script.sut_name || '—'} ${script.sut_ip ? '('+script.sut_ip+':'+(script.sut_port||'5060')+')' : ''}`
    ]);

    if(note){
      doc.setFontSize(10); doc.setTextColor(50);
      const lines = doc.splitTextToSize(note, 180);
      doc.text(lines, 14, y); y += lines.length*5 + 6;
    }

    const sent = stats.sent ?? 0, done = stats.completed ?? 0, failed = stats.failed ?? 0;
    y = _pdfSection(doc, y, 'Call results');
    doc.autoTable({ startY: y, margin:{left:14}, head:[['Metric','Value']], styles:{fontSize:9}, headStyles:{fillColor:[26,26,26]},
      body:[
        ['Calls sent', sent], ['Completed', done], ['Failed', failed],
        ['Completion rate', sent ? ((done/sent)*100).toFixed(1)+'%' : '—'],
        ['Average call duration (s)', fmt(avg(durVals),1)]
      ]});
    y = doc.lastAutoTable.finalY + 10;

    const sentM = sr.sent || {}, recvM = sr.received || {};
    if(Object.keys(sentM).length || Object.keys(recvM).length){
      y = _pdfSection(doc, y, 'SIP messages');
      const rows = [];
      Object.entries(sentM).forEach(([k,v]) => rows.push(['Sent', k, v]));
      Object.entries(recvM).forEach(([k,v]) => rows.push(['Received', k, v]));
      doc.autoTable({ startY: y, margin:{left:14}, head:[['Direction','Message','Count']], body: rows, styles:{fontSize:9}, headStyles:{fillColor:[26,26,26]} });
      y = doc.lastAutoTable.finalY + 10;
    }

    if(mosVals.length || lossVals.length){
      y = _pdfSection(doc, y, 'Media quality (from capture)');
      doc.autoTable({ startY: y, margin:{left:14}, head:[['Metric','Value']], styles:{fontSize:9}, headStyles:{fillColor:[26,26,26]},
        body:[
          ['Calls with RTP measured', mosVals.length],
          ['Average MOS', fmt(avg(mosVals))],
          ['Worst MOS', fmt(mosVals.length?Math.min(...mosVals):null)],
          ['Average packet loss (%)', fmt(avg(lossVals))]
        ]});
      y = doc.lastAutoTable.finalY + 10;
    }

    doc.save(`sipp_report_ws${activeWsId}_${Date.now()}.pdf`);
  } catch(e) {
    alert('Could not build the PDF: ' + e.message);
  } finally {
    if(btn) btn.disabled = false;
  }
}
