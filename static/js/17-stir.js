// ═══════════════════════════════════════════════════════════════════════════════
// STIR/SHAKEN
// ═══════════════════════════════════════════════════════════════════════════════
async function loadStirInfo(){
  try{
    const r=await fetch('/stir/info');
    const d=await r.json();
    const el=document.getElementById('stir-info');
    if(!el) return;
    if(!d.exists){el.innerHTML='<span style="color:#888">No certificate — auto-generated on first use</span>';return;}
    const expired=new Date(d.not_after)<new Date();
    el.innerHTML=`
      <div style="display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:12px">
        <span style="color:#888">Subject:</span><span style="font-weight:500">${escapeHtml(d.subject)} ${d.self_signed?'(self-signed)':'(BYOC)'}</span>
        <span style="color:#888">Expires:</span><span style="${expired?'color:#dc2626':'color:#16a34a'}">${escapeHtml(new Date(d.not_after).toLocaleDateString())}${expired?' (EXPIRED)':''}</span>
        <span style="color:#888">Cert URL:</span><span style="font-family:monospace;font-size:11px">${escapeHtml(d.cert_url)}</span>
      </div>`;
  }catch(e){}
}

async function stirRegenCert(){
  const r=await fetch('/stir/regenerate-cert',{method:'POST'});
  const d=await r.json();
  if(d.ok){alert('Certificate regenerated');loadStirInfo();}
  else alert('Failed to regenerate certificate: '+(d.error||'unknown error'));
}

function stirShowByoc(){
  const p=document.getElementById('stir-byoc-panel');
  if(p) p.style.display=p.style.display==='none'?'block':'none';
}

async function stirUploadByoc(){
  const cert=document.getElementById('byoc-cert')?.value.trim();
  const key =document.getElementById('byoc-key')?.value.trim();
  if(!cert||!key){alert('Both cert and key required');return;}
  const r=await fetch('/stir/upload-cert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cert_pem:cert,key_pem:key})});
  const d=await r.json();
  if(d.ok){alert('BYOC cert uploaded');loadStirInfo();}
  else alert('Upload failed: '+(d.error||'unknown'));
}

async function stirGenerate(){
  const orig=document.getElementById('stir-orig-tn')?.value.trim();
  const dest=document.getElementById('stir-dest-tn')?.value.trim();
  const attest=document.getElementById('stir-attest')?.value||'A';
  if(!orig||!dest){alert('Enter orig and dest TNs');return;}
  const r=await fetch('/stir/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({orig_tn:orig,dest_tn:dest,attestation:attest})});
  const d=await r.json();
  if(d.error){alert('Error: '+d.error);return;}
  document.getElementById('stir-result').style.display='block';
  document.getElementById('stir-identity').value=d.identity_header;
  document.getElementById('stir-decoded').textContent=JSON.stringify(d.payload,null,2);
  const colors={A:'#dcfce7;color:#16a34a',B:'#fef3c7;color:#92400e',C:'#fee2e2;color:#dc2626'};
  const labels={A:'A — Full Attestation',B:'B — Partial Attestation',C:'C — Gateway Attestation'};
  const badge=document.getElementById('stir-attest-badge');
  const c=colors[attest];
  badge.style.cssText=`padding:3px 10px;border-radius:10px;font-size:12px;font-weight:500;background:${c.split(';')[0]};${c.split(';')[1]}`;
  badge.textContent=labels[attest];
  document.getElementById('stir-tn-display').textContent=`${escapeHtml(d.orig_tn)} → ${escapeHtml(d.dest_tn)}  |  IAT: ${new Date(d.iat*1000).toLocaleTimeString()}`;
}

async function stirVerify(){
  const identity=document.getElementById('stir-verify-input')?.value.trim();
  if(!identity){alert('Paste an Identity header first');return;}
  const r=await fetch('/stir/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identity_header:identity})});
  const d=await r.json();
  const el=document.getElementById('stir-verify-result');
  el.style.display='block';
  if(d.error){
    el.style.cssText='display:block;padding:12px;border-radius:8px;background:#fee2e2;border:1px solid #fca5a5;font-size:13px';
    el.innerHTML=`<strong>Error:</strong> ${escapeHtml(d.error)}`;return;
  }
  const colors={A:'#dcfce7',B:'#fef3c7',C:'#fee2e2'};
  const bg=d.verified?(colors[d.attestation]||'#f0f9ff'):'#fee2e2';
  const border=d.verified?'#86efac':'#fca5a5';
  el.style.cssText=`display:block;padding:12px;border-radius:8px;background:${bg};border:1px solid ${border};font-size:13px`;
  el.innerHTML=`
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <span style="font-size:16px">${d.verified?'✅':'❌'}</span>
      <strong>${d.verified?'VERIFIED':'VERIFICATION FAILED'}</strong>
      <span style="padding:2px 8px;border-radius:10px;background:rgba(0,0,0,.08);font-size:12px">Attestation ${escapeHtml(d.attestation)}</span>
    </div>
    <div style="display:grid;grid-template-columns:auto 1fr;gap:3px 12px;font-size:12px">
      <span style="color:#555">Orig TN:</span><span style="font-weight:500">${escapeHtml(d.orig_tn)}</span>
      <span style="color:#555">Dest TN:</span><span style="font-weight:500">${escapeHtml(d.dest_tn)}</span>
      <span style="color:#555">Token age:</span><span>${escapeHtml(d.age_seconds)}s ${d.age_seconds>60?'⚠️ EXPIRED':'✓ fresh'}</span>
      <span style="color:#555">Orig ID:</span><span style="font-family:monospace;font-size:11px">${escapeHtml(d.origid)}</span>
      ${d.verification_error?`<span style="color:#dc2626">Error:</span><span style="color:#dc2626">${escapeHtml(d.verification_error)}</span>`:''}
    </div>`;
}
