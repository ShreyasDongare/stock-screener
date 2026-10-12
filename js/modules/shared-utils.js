const $ = id => document.getElementById(id);
const f2 = x => x == null || !Number.isFinite(Number(x)) ? "" : Number(x).toLocaleString("en-IN",{maximumFractionDigits:2});
const esc = x => String(x ?? "").replace(/[&<>"']/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[m]));
function sourceRows(tab){
  if (!D || !D.scans) return [];
  return D.scans[tab] || [];
}
function rows(tab){
  const q = S.q.trim().toUpperCase();
  return sourceRows(tab).filter(r => {
    if (S.ex !== "ALL" && r.exch !== S.ex) return false;
    if (q && !String(r.symbol || "").toUpperCase().includes(q)) return false;
    return true;
  });
}
function valueFor(r,key){
  const v = r?.[key];
  if(typeof v === "string") return v.toUpperCase();
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function spark(a, up){
  if(!Array.isArray(a) || a.length < 2) return "";
  const vals = a.map(Number).filter(Number.isFinite);
  if(vals.length < 2) return "";
  const mn=Math.min(...vals), mx=Math.max(...vals), den=mx-mn || 1;
  const pts=vals.map((v,i)=>[(i/(vals.length-1)*92+2).toFixed(1),(26-(v-mn)/den*22).toFixed(1)]);
  const col = `var(${up ? "--up" : "--dn"})`;
  const last=pts[pts.length-1];
  return `<svg width="82" height="22" viewBox="0 0 96 28" aria-hidden="true"><polyline points="${pts.map(p=>p.join(",")).join(" ")}" fill="none" stroke="${col}" stroke-width="1.6"/><circle cx="${last[0]}" cy="${last[1]}" r="2.3" fill="${col}"/></svg>`;
}

function heat(v){
  if(v == null || !Number.isFinite(Number(v))) return "<td></td>";
  const n=Number(v), cls=n>=0?"up":"dn";
  return `<td class="${cls}">${n>=0?"+":""}${f2(n)}</td>`;
}

function options(values,current,label){
  return values.map(v=>`<option value="${esc(v)}" ${String(v)===String(current)?"selected":""}>${label(v)}</option>`).join("");
}
