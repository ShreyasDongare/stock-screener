const CELL = {
  symbol:r=>`<td class="sym l"><button class="chart-link" data-chart-key="${esc(r.key)}" title="Click for EOD chart · Double-click for Dhan TradingView">${esc(r.symbol)}</button>${r.note ? ` <span class="w" title="${esc(r.note)}">⚠</span>` : ""}</td>`,
  exch:r=>{const ex=String(r.exch||"").toUpperCase();return `<td class="l"><span class="ex ${ex==="BSE"?"bse":"nse"}">${esc(ex)}</span></td>`;},
  setup:r=>`<td class="l"><span class="tag">${esc(r.setup)}</span></td>`,
  state:r=>`<td class="l"><span class="tag ${r.state==="Triggered"?"t":""}">${esc(r.state)}</span></td>`,
  chg:r=>`<td class="${Number(r.chg)>=0?"up":"dn"}">${Number(r.chg)>=0?"+":""}${f2(r.chg)}</td>`,
  rs:r=>`<td><span class="rs"><i style="width:${Math.min(40,Number(r.rs||0)*.4)}px"></i><b>${f2(r.rs)}</b></span></td>`,
  adx:r=>`<td class="adx-cell">${f2(r.adx)}</td>`,
  ret1m:r=>heat(r.ret1m), ret3m:r=>heat(r.ret3m), ret6m:r=>heat(r.ret6m),
  dist:r=>`<td>${Number(r.dist)>=0?"+":""}${f2(r.dist)}</td>`,
  risk:r=>`<td class="${Number(r.risk)<=5?"rk-ok":Number(r.risk)<=10?"rk-mid":"rk-hi"}">${f2(r.risk)}</td>`,
  level:r=>`<td class="l">${esc(r.level)}</td>`,
  breakout:r=>`<td class="l"><span class="tag">${esc(r.breakout)}</span></td>`,
  market_cap_cr:r=>`<td>${f2(r.market_cap_cr)}</td>`,
  ema60:r=>`<td>${f2(r.ema60)}</td>`,
  ema75:r=>`<td>${f2(r.ema75)}</td>`,
  ret3m:r=>heat(r.ret3m),
  gain60:r=>heat(r.gain60),
  off_high:r=>`<td>${f2(r.off_high)}</td>`,
  vol_ratio:r=>`<td>${f2(r.vol_ratio)}x</td>`,
  tr_adr:r=>`<td>${f2(r.tr_adr ?? r.adr)}</td>`,
  value_cr:r=>`<td>${f2(r.value_cr)}</td>`,
  avg_volume:r=>`<td>${f2(r.avg_volume)}</td>`,
  rvol:r=>`<td>${f2(r.rvol)}x</td>`,
  one_month_high:r=>`<td>${f2(r.one_month_high)}</td>`,
  gap:r=>heat(r.gap),
  prior_3m:r=>heat(r.prior_3m),
  days_ago:r=>`<td>${f2(r.days_ago)}</td>`,
  ret3m_perf:r=>heat(r.ret3m_perf),
  ret1m_perf:r=>heat(r.ret1m_perf),
  spark:r=>`<td>${spark(r.spark,Number(r.chg)>=0)}</td>`
};

function render(){
  if(!D) return;
  const sc=SCANS[S.tab];
  Object.keys(SCANS).forEach(k=>{});
  $("tabs").innerHTML=Object.keys(SCANS).map(k=>{const count=sourceRows(k).length;return `<div class="tab" role="tab" tabindex="0" data-tab="${k}" aria-selected="${k===S.tab}"><b>${count}</b><span>${SCANS[k].t}</span><button type="button" class="tab-action tab-copy" data-copy-tab="${k}" aria-label="Copy ${count} stocks from ${SCANS[k].t}" title="Copy stocks"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"></path></svg></button><button type="button" class="tab-action tab-info" data-info-tab="${k}" aria-label="Show ${SCANS[k].t} formula" title="Show formula"><img src="assets/info.svg" alt="" aria-hidden="true"></button></div>`}).join("");
  document.querySelectorAll("[data-ex]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.ex===S.ex));
  const filterHTML = "";  $("filters").innerHTML=filterHTML;
  $("q").value=S.q||"";
  $("q").placeholder=`Search from ${sourceRows(S.tab).length} stocks`;
  $("desc").textContent=sc.d;
  $("thead").innerHTML="<tr>"+sc.cols.map(([k,t,cl])=>`<th class="${cl||""}"><button data-sort="${k}">${t}${S.key===k?(S.dir>0?" ▲":" ▼"):""}</button></th>`).join("")+"</tr>";
  SHOWN=rows(S.tab).sort((a,b)=>{
    const x=valueFor(a,S.key), y=valueFor(b,S.key);
    if(typeof x==="string" || typeof y==="string") return S.dir*String(x??"").localeCompare(String(y??""));
    return S.dir*((Number(x)||0)-(Number(y)||0));
  });
  $("tbody").innerHTML=SHOWN.length ? SHOWN.map(r=>"<tr>"+sc.cols.map(([k])=>CELL[k]?CELL[k](r):`<td>${f2(r[k])}</td>`).join("")+"</tr>").join("") : `<tr><td colspan="${sc.cols.length}" class="empty">No stocks match these filters.</td></tr>`;
  $("foot").textContent=`Showing ${SHOWN.length} of ${sourceRows(S.tab).length}. Click a symbol to open its chart.${""}`;
  try { localStorage.setItem("scn",JSON.stringify(S)); } catch (_) {}
}


