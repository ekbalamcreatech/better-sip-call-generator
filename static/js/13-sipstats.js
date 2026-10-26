// ═══════════════════════════════════════════════════════════════════════════════
// SIP STATS
// ═══════════════════════════════════════════════════════════════════════════════
async function loadSipStats() {
  if(!activeWsId) return;

  // populate script dropdown
  const qsel = document.getElementById('sipstats-script-select');
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
    const r = await fetch(`/sipstats/${activeWsId}?script_id=${sid}`);
    const d = await r.json();

    const el = document.getElementById('sipstats-content');
    const sumEl = document.getElementById('sipstats-summary');

    const rt = Object.values(d.retransmissions||{}).reduce((a,b)=>a+b,0);
    sumEl.textContent = `${d.total_calls} calls` + (rt ? ` · ${rt} retransmissions` : '');

    if(!Object.keys(d.sent||{}).length && !Object.keys(d.received||{}).length) {
      el.innerHTML = '<p style="color:#888;font-size:13px;padding:8px">No data — run a test first</p>';
      return;
    }

    const sum = d.summary || {};
    const total4xx5xx = (sum['4xx']||0) + (sum['5xx']||0) + (sum['6xx']||0);
    const total2xx = sum['2xx']||0;
    const totalResp = Object.values(sum).reduce((a,b)=>a+b,0);

    el.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">

        <!-- Sent -->
        <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden">
          <div style="padding:10px 14px;background:#fafafa;border-bottom:1px solid #f0f0f0;font-size:12px;font-weight:500;color:#1a1a1a">
            ▶ Sent (TX)
          </div>
          <table style="width:100%;border-collapse:collapse;font-size:13px">
            ${Object.entries(d.sent||{}).map(([method, count]) => `
              <tr style="border-bottom:1px solid #f5f5f5">
                <td style="padding:7px 14px;font-weight:500;color:#185FA5;font-family:monospace">${escapeHtml(method)}</td>
                <td style="padding:7px 14px;text-align:right;font-weight:500">${escapeHtml(count)}</td>
                <td style="padding:7px 14px;width:40%">
                  <div style="background:#e5e5e5;border-radius:2px;height:4px">
                    <div style="background:#185FA5;border-radius:2px;height:4px;width:${escapeHtml(Math.min(100,count/Math.max(...Object.values(d.sent))*100))}%"></div>
                  </div>
                </td>
              </tr>`).join('')}
          </table>
        </div>

        <!-- Received -->
        <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden">
          <div style="padding:10px 14px;background:#fafafa;border-bottom:1px solid #f0f0f0;font-size:12px;font-weight:500;color:#1a1a1a">
            ← Received (RX)
          </div>
          <table style="width:100%;border-collapse:collapse;font-size:13px">
            ${Object.entries(d.received||{}).map(([code, count]) => {
              const c = parseInt(code);
              const color = c>=200&&c<300 ? '#16a34a' : c>=400&&c<700 ? '#dc2626' : '#185FA5';
              const maxVal = Math.max(...Object.values(d.received));
              return `
              <tr style="border-bottom:1px solid #f5f5f5">
                <td style="padding:7px 14px;font-weight:500;color:${escapeHtml(color)};font-family:monospace">${escapeHtml(code)}</td>
                <td style="padding:7px 14px;text-align:right;font-weight:500">${escapeHtml(count)}</td>
                <td style="padding:7px 14px;width:40%">
                  <div style="background:#e5e5e5;border-radius:2px;height:4px">
                    <div style="background:${escapeHtml(color)};border-radius:2px;height:4px;width:${escapeHtml(Math.min(100,count/maxVal*100))}%"></div>
                  </div>
                </td>
              </tr>`;
            }).join('')}
          </table>
        </div>
      </div>

      ${Object.keys(d.retransmissions||{}).length ? `
      <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:12px 14px;margin-bottom:16px;font-size:13px;color:#9a3412">
        <b>Retransmissions</b> (repeats of a message already counted above, usually because the far end did not answer):
        ${Object.entries(d.retransmissions).map(([m,n]) => `<span style="font-family:monospace;margin-left:10px">${escapeHtml(m)} ×${escapeHtml(n)}</span>`).join('')}
      </div>` : ''}

      <!-- Response code summary -->
      <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:14px">
        <div style="font-size:12px;font-weight:500;margin-bottom:10px;color:#1a1a1a">Response Code Summary</div>
        <div style="display:flex;gap:12px;flex-wrap:wrap">
          ${[
            {label:'2xx Success', key:'2xx', color:'#16a34a', bg:'#dcfce7'},
            {label:'3xx Redirect', key:'3xx', color:'#185FA5', bg:'#dbeafe'},
            {label:'4xx Client Error', key:'4xx', color:'#dc2626', bg:'#fee2e2'},
            {label:'5xx Server Error', key:'5xx', color:'#dc2626', bg:'#fee2e2'},
            {label:'6xx Global Error', key:'6xx', color:'#7c3aed', bg:'#ede9fe'},
          ].map(({label, key, color, bg}) => {
            const count = sum[key]||0;
            const pct = totalResp > 0 ? Math.round(count/totalResp*100) : 0;
            return `
            <div style="background:${escapeHtml(bg)};border-radius:8px;padding:10px 16px;min-width:120px">
              <div style="font-size:11px;color:${escapeHtml(color)};font-weight:500;margin-bottom:2px">${escapeHtml(label)}</div>
              <div style="font-size:20px;font-weight:500;color:${escapeHtml(color)}">${escapeHtml(count)}</div>
              <div style="font-size:11px;color:${escapeHtml(color)};opacity:.7">${escapeHtml(pct)}%</div>
            </div>`;
          }).join('')}
        </div>
      </div>`;

  } catch(e) {
    console.error('SIP stats error:', e);
  }
}
