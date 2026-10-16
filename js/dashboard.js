const SCANS = {
  m136: {
    t: "1M / 3M / 6M",
    d: "Common filter: ADX >= 20 and at least one of the 1M / 3M / 6M returns is >= 30%. Then breakout above the prior 31, 93 or 186 trading-day closing high with ADR and EMA60.",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["ret1m","1M %"],["ret3m","3M %"],["ret6m","6M %"],["breakout","Breakout","l"],["ema60","EMA60"],["tr_adr","ADR %"],["adx","ADX"],["spark","40 days"]]
  },
  m30: {
    t: "3M 30% Scan",
    d: "ADX >= 20 and at least one of the 1M / 3M / 6M returns is >= 30%. Then 3-month return above 30%, above EMA75, ADR at least 3%, and traded value above ₹1 Cr.",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["ret1m","1M %"],["ret3m","3M %"],["ret6m","6M %"],["ema75","EMA75"],["tr_adr","ADR %"],["adx","ADX"],["value_cr","Value (Cr)"],["spark","40 days"]]
  },
  htf: {
    t: "HTF Scan",
    d: "ADX >= 20 and at least one of the 1M / 3M / 6M returns is >= 30%. Then 60-day gain above 50%, within 15% of the prior 252-day high, controlled volume and price above ₹50.",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["ret1m","1M %"],["ret3m","3M %"],["ret6m","6M %"],["gain60","60D %"],["off_high","Off 252W high %"],["vol_ratio","Vol x"],["tr_adr","ADR %"],["adx","ADX"],["spark","40 days"]]
  },
  high52w: {
    t: "52Week High",
    d: "ADX >= 20 and at least one of the 1M / 3M / 6M returns is >= 30%. Then within 10% of the prior 252-day high, but not above it, with ADR and ₹1 Cr traded-value.",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["ret1m","1M %"],["ret3m","3M %"],["ret6m","6M %"],["off_high","Off 52W high %"],["tr_adr","ADR %"],["adx","ADX"],["value_cr","Value (Cr)"],["spark","40 days"]]
  },
  volume: {
    t: "Volume Scan",
    d: "NSE only · Price ≥ ₹30 · Change ≥ 3% · 20-day average volume ≥ 200,000 shares · RVOL > 3x.",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["volume","Volume"],["avg_volume","Avg Vol"],["rvol","RVOL"],["spark","40 days"]]
  },
  one_month: {
    t: "1 Month High",
    d: "NSE only · Price ≥ ₹30 · 20-day average volume ≥ 200,000 shares · New 1-month high.",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["avg_volume","Avg Vol"],["one_month_high","Prior 1M High"],["spark","40 days"]]
  },
  one_month_perf: {
    t: "1-Month Performance",
    d: "NSE only · Price ≥ ₹30 · 20-day average volume ≥ 200,000 shares · Minimum 30% gain over the last 1 month (21 trading sessions).",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["ret1m_perf","1M Gain %"],["avg_volume","Avg Vol"],["spark","40 days"]]
  },
  three_month: {
    t: "3-Month Performance",
    d: "NSE only · Price ≥ ₹30 · 20-day average volume ≥ 200,000 shares · Minimum 30% gain over the last 3 months (63 trading sessions).",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["ret3m_perf","3M Gain %"],["avg_volume","Avg Vol"],["spark","40 days"]]
  },
  ep: {
    t: "Episodic Pivot",
    d: "Common filters plus an EP event in the last 3 sessions.",
    sort: ["symbol", 1],
    cols: [["symbol","Symbol","l"],["exch","Exch","l"],["close","Close"],["chg","Chg %"],["state","EP Day","l"],["gap","Gap %"],["vol_ratio","Vol x"],["prior_3m","Prior 3M %"],["risk","Risk %"],["spark","40 days"]]
  },
}
const DEFAULT_STATE = { tab: "m136", ex: "ALL", q: "", key: "symbol", dir: 1 };
let S = {...DEFAULT_STATE};
try {
  const saved = JSON.parse(localStorage.getItem("scn") || "{}");
  S = {...DEFAULT_STATE, ...saved, lv:{...DEFAULT_STATE.lv, ...(saved.lv||{})}};
  if (!SCANS[S.tab]) { S.tab = DEFAULT_STATE.tab; S.key = DEFAULT_STATE.key; S.dir = DEFAULT_STATE.dir; }
} catch (_) {}

let D = null, SHOWN = [];

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




const WATCHLIST_COLORS=[["red","Red"],["orange","Orange"],["yellow","Yellow"],["green","Green"],["blue","Blue"],["purple","Purple"]];

function renderColourWatchlist(){
  // Legacy standalone colour modal is no longer used. The colour watchlist
  // is rendered inside the same popup as the stock chart.
  return;
}
function openColourWatchlist(){
  const tags=getTags();
  const rows=[];
  const seen=new Set();
  Object.keys(SCANS).forEach(tab=>{
    sourceRows(tab).forEach(r=>{
      if(!r||!r.symbol) return;
      const key=chartRowKey(r);
      if(seen.has(key)||!tags[key]) return;
      seen.add(key);
      rows.push({...r,__watchColor:tags[key]});
    });
  });
  rows.sort((a,b)=>{
    const order=Object.fromEntries(WATCHLIST_COLORS.map(([color],i)=>[color,i]));
    const ca=order[a.__watchColor]??99, cb=order[b.__watchColor]??99;
    return ca!==cb ? ca-cb : String(a.symbol||"").localeCompare(String(b.symbol||""));
  });
  if(!rows.length){
    alert("No coloured stocks in My Watchlist yet.");
    return;
  }
  CHART_WATCH_MODE="colours";
  CHART_WATCH_Q="";
  CHART_WATCH_SORT="symbol";
  CHART_WATCH_SORT_DIR=1;
  openChart(chartRowKey(rows[0]),rows[0]);
}
function closeColourWatchlist(){
  $("watchlistModal")?.classList.remove("open");
}

function closeFormulaPopover(){ $("formulaPopover")?.classList.remove("open"); }
function showFormulaPopover(tab,anchor){
  const pop=$("formulaPopover");
  if(!pop) return;
  const title=SCANS[tab]?.t || tab;
  const def=D?.config?.definitions?.[tab] || SCANS[tab]?.d || "Formula not available.";
  $("formulaTitle").textContent=title;
  const parts=String(def).split(/\s+AND\s+/i).map(x=>x.trim()).filter(Boolean);
  $("formulaBody").innerHTML=parts.map(x=>'<div class="formula-line">'+esc(x)+'</div>').join("");
  const commonTabs=new Set(["m136","m30","htf","high52w"]);
  $("formulaNote").textContent=commonTabs.has(tab)
    ? "This scan also uses the common filters shown in the dashboard description."
    : "Independent scan: common momentum/ADX filters are not applied.";
  pop.classList.add("open");
  const r=anchor?.getBoundingClientRect?.();
  const w=pop.offsetWidth, h=pop.offsetHeight, pad=10;
  let left=(r?.right ?? window.innerWidth-pad)+10;
  let top=(r?.top ?? pad);
  if(left+w>window.innerWidth-pad) left=Math.max(pad,(r?.left ?? 0)-w-10);
  if(top+h>window.innerHeight-pad) top=Math.max(pad,window.innerHeight-h-pad);
  pop.style.left=left+"px";
  pop.style.top=top+"px";
}
function wire(){
  $("marketBreadthOpen")?.addEventListener("click",openMarketBreadth);
  $("breadthClose")?.addEventListener("click",closeMarketBreadth);
  $("breadthModal")?.addEventListener("click",e=>{if(e.target.id==="breadthModal") closeMarketBreadth();});
  const openTradingView=(r)=>{
    if(!r || !r.symbol) return;
    const exchange=r.exch==="BSE"?"BSE":"NSE";
    const tvSymbol=exchange+":"+String(r.symbol);
    const url="https://www.tradingview.com/chart/?symbol="+encodeURIComponent(tvSymbol);
    window.open(url,"_blank","noopener,noreferrer");
  };
  document.addEventListener("click",e=>{
    const tfBtn=e.target.closest("[data-chart-tf]");
    if(tfBtn){ CHART_TF=tfBtn.dataset.chartTf==="W"?"W":"D"; if(CHART_ROW) openChart(CHART_ROW.key,CHART_ROW); return; }
    const chartBtn=e.target.closest("[data-chart-key]");
    const watchSort=e.target.closest("[data-watch-sort]");
    if(watchSort){ const key=watchSort.dataset.watchSort; if(CHART_WATCH_SORT===key) CHART_WATCH_SORT_DIR*=-1; else { CHART_WATCH_SORT=key; CHART_WATCH_SORT_DIR=(key==="symbol"?1:-1); } renderChartWatchlist(CHART_ROW?chartRowKey(CHART_ROW):""); return; }
    const colourWatchBtn=e.target.closest("[data-colour-watch-key]");
    if(colourWatchBtn){
      const key=colourWatchBtn.dataset.colourWatchKey;
      let row=null;
      for(const tab of Object.keys(SCANS)){
        row=sourceRows(tab).find(x=>chartRowKey(x)===key);
        if(row) break;
      }
      if(row){
        closeColourWatchlist();
        clearTimeout(chartClickTimer);
        openChart(key,row);
      }
      return;
    }
    const watchBtn=e.target.closest("[data-watch-key]");
    const tagBtn=e.target.closest("[data-tag-key]");
    if(tagBtn){ e.stopPropagation(); return; }
    if(watchBtn){
      const key=watchBtn.dataset.watchKey;
      const r=chartRows().find(x=>chartRowKey(x)===key);
      clearTimeout(chartClickTimer);
      chartClickTimer=setTimeout(()=>openChart(key,r),220);
      return;
    }
    if(chartBtn){
      const r=Object.values(D.scans||{}).flat().find(x=>x.key===chartBtn.dataset.chartKey);
      clearTimeout(chartClickTimer);
      chartClickTimer=setTimeout(()=>openChart(chartBtn.dataset.chartKey,r),220);
      return;
    }
    const copyTab=e.target.closest("[data-copy-tab]");
    if(copyTab){
      e.stopPropagation();
      const tab=copyTab.dataset.copyTab;
      const symbols=[...new Set(sourceRows(tab).map(r=>r?.symbol).filter(Boolean).map(String))];
      navigator.clipboard?.writeText(symbols.join("\n")).then(()=>{
        copyTab.classList.add("copied");
        const oldTitle=copyTab.getAttribute("title");
        copyTab.setAttribute("title","Copied "+symbols.length+" stocks");
        setTimeout(()=>{copyTab.classList.remove("copied");copyTab.setAttribute("title",oldTitle||"Copy stocks");},1200);
      }).catch(()=>{});
      return;
    }
    const info=e.target.closest("[data-info-tab]");
    if(info){
      e.stopPropagation();
      showFormulaPopover(info.dataset.infoTab,info);
      return;
    }
    const t=e.target.closest("[data-tab]"), x=e.target.closest("[data-ex]"), s=e.target.closest("[data-sort]"), l=e.target.closest("[data-lv]");
    if(t){S.tab=t.dataset.tab;S.st="";[S.key,S.dir]=SCANS[S.tab].sort;CHART_WATCH_Q="";CHART_WATCH_SORT="symbol";CHART_WATCH_SORT_DIR=1;render();return}
    if(x){S.ex=x.dataset.ex;render();return}
    if(l){S.lv[l.dataset.lv]=!S.lv[l.dataset.lv];render();return}
    if(s){const k=s.dataset.sort;S.dir=S.key===k?-S.dir:1;S.key=k;render();return}
    if(["copyAll","copyNSE","copyBSE"].includes(e.target.id)){
      const exchange=e.target.id==="copyNSE"?"NSE":e.target.id==="copyBSE"?"BSE":null;
      const all=[];
      Object.keys(SCANS).forEach(tab=>sourceRows(tab).forEach(r=>{
        if(r?.symbol && (!exchange || String(r.exch||"").toUpperCase()===exchange)) all.push(r.symbol);
      }));
      const sy=[...new Set(all.map(String))];
      navigator.clipboard?.writeText(sy.join("\n")).then(()=>{
        const b=e.target, old=b.textContent;
        b.textContent="Copied "+sy.length;
        setTimeout(()=>b.textContent=old,1400);
      }).catch(()=>{});
      return;
    }
    if(e.target.id==="theme"){
      const root=document.documentElement, current=root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");
      root.dataset.theme=current==="dark"?"light":"dark";
      try{localStorage.setItem("scn-theme",root.dataset.theme)}catch(_){}
      if(LW && CHART_ROW && CHART[CHART_ROW.key]) openChart(CHART_ROW.key,CHART_ROW);
      return;
    }
  });
  document.addEventListener("keydown",e=>{
    const info=e.target.closest?.("[data-info-tab]");
    if(info && (e.key==="Enter" || e.key===" ")){
      e.preventDefault();
      e.stopPropagation();
      showFormulaPopover(info.dataset.infoTab,info);
      return;
    }
    const copyTab=e.target.closest?.("[data-copy-tab]");
    if(copyTab && (e.key==="Enter" || e.key===" ")){
      e.preventDefault();
      copyTab.click();
      return;
    }
    const tab=e.target.closest?.(".tab[data-tab]");
    if(tab && !copyTab && (e.key==="Enter" || e.key===" ")){
      e.preventDefault();
      tab.click();
    }
  });
  document.addEventListener("dblclick",e=>{
    const chartBtn=e.target.closest("[data-chart-key]");
    const watchBtn=e.target.closest("[data-watch-key]");
    if(!D) return;
    // Desktop only: double-click opens TradingView. Mobile long-press is reserved for colour tagging.
    if(!window.matchMedia("(hover:hover) and (pointer:fine)").matches) return;
    e.preventDefault();
    clearTimeout(chartClickTimer);
    if(chartBtn){
      const r=Object.values(D.scans||{}).flat().find(x=>x.key===chartBtn.dataset.chartKey);
      openTradingView(r);
      return;
    }
    if(watchBtn){
      const r=chartRows().find(x=>chartRowKey(x)===watchBtn.dataset.watchKey);
      openTradingView(r);
    }
  });
  document.addEventListener("change",e=>{
    const id=e.target.id;
    if(id==="rs")S.rs=Number(e.target.value);
    else if(id==="off")S.off=e.target.value;
    else if(id==="risk")S.risk=e.target.value;
    else if(id==="st")S.st=e.target.value;
    else if(id==="fmt")S.fmt=e.target.value;
    else return;
    render();
  });
  $("q").addEventListener("input",e=>{S.q=e.target.value;render()});
  document.addEventListener("keydown",e=>{if(e.key==="/" && document.activeElement.tagName!=="INPUT"){e.preventDefault();$("q").focus()}});
}

$("chartClose").addEventListener("click",closeChart);
$("chartPrev")?.addEventListener("click",()=>navigateChartStock(-1));
$("chartNext")?.addEventListener("click",()=>navigateChartStock(1));
$("chartPrevBottom")?.addEventListener("click",()=>navigateChartStock(-1));
$("chartNextBottom")?.addEventListener("click",()=>navigateChartStock(1));
$("watchlistOpen")?.addEventListener("click",()=>openColourWatchlist());

$("formulaClose")?.addEventListener("click",closeFormulaPopover);
document.addEventListener("click",e=>{if(!e.target.closest(".formula-popover") && !e.target.closest("[data-info-tab]")) closeFormulaPopover();});
window.addEventListener("resize",closeFormulaPopover);
$("chartModal").addEventListener("click",e=>{if(e.target.id==="chartModal") closeChart()});
function closeTagPalette(){document.querySelector(".chart-tag-palette")?.remove();}
function openTagPalette(key,x,y){
  closeTagPalette();
  const palette=document.createElement("div");
  palette.className="chart-tag-palette";
  palette.dataset.tagKey=key;
  const colors=[
    ["","No colour"],["red","Red"],["orange","Orange"],["yellow","Yellow"],
    ["green","Green"],["blue","Blue"],["purple","Purple"]
  ];
  palette.innerHTML=colors.map(([color,label])=>'<button type="button" class="chart-tag-choice '+(color||"none")+'" data-palette-color="'+color+'" aria-label="'+label+'" title="'+label+'"></button>').join("");
  document.body.appendChild(palette);
  const pad=8, w=palette.offsetWidth, h=palette.offsetHeight;
  palette.style.left=Math.min(x,window.innerWidth-w-pad)+"px";
  palette.style.top=Math.min(y,window.innerHeight-h-pad)+"px";
  palette.addEventListener("click",e=>{
    const b=e.target.closest("[data-palette-color]"); if(!b) return;
    const tags=getTags(), color=b.dataset.paletteColor;
    if(color) tags[key]=color; else delete tags[key];
    saveTags(tags); CHART_WATCH_TAGS=tags; closeTagPalette(); renderChartWatchlist(CHART_ROW?chartRowKey(CHART_ROW):key); if($("watchlistModal")?.classList.contains("open")) renderColourWatchlist();
  });
}
let chartWatchLongPressTimer=null;
let chartWatchLongPressMoved=false;
document.addEventListener("contextmenu",e=>{
  const item=e.target.closest("[data-watch-key]");
  if(!item || !$("chartModal").classList.contains("open")) return;
  // Desktop: right-click opens the colour palette.
  if(window.matchMedia("(hover:hover) and (pointer:fine)").matches){
    e.preventDefault();
    openTagPalette(item.dataset.watchKey,e.clientX,e.clientY);
  }
});
document.addEventListener("pointerdown",e=>{
  const item=e.target.closest("[data-watch-key]");
  if(!item || !$("chartModal").classList.contains("open")) return;
  if(!window.matchMedia("(hover:none) and (pointer:coarse)").matches) return;
  chartWatchLongPressMoved=false;
  const key=item.dataset.watchKey, x=e.clientX, y=e.clientY;
  clearTimeout(chartWatchLongPressTimer);
  chartWatchLongPressTimer=setTimeout(()=>{
    if(!chartWatchLongPressMoved) openTagPalette(key,x,y);
  },550);
});
document.addEventListener("pointermove",e=>{
  if(chartWatchLongPressTimer && (Math.abs(e.movementX)>4 || Math.abs(e.movementY)>4)){
    chartWatchLongPressMoved=true;
    clearTimeout(chartWatchLongPressTimer);
    chartWatchLongPressTimer=null;
  }
});
document.addEventListener("pointerup",()=>{
  clearTimeout(chartWatchLongPressTimer);
  chartWatchLongPressTimer=null;
});
document.addEventListener("click",e=>{
  if(!e.target.closest(".chart-tag-palette")) closeTagPalette();
});
document.addEventListener("keydown",e=>{
  if(!$("chartModal").classList.contains("open")) return;
  if(["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName) && e.key!=="Escape") return;
  if(e.key==="Escape"){
    const p=document.querySelector(".chart-tag-palette");
    if(p){e.preventDefault();closeTagPalette();return;}
    e.preventDefault();closeChart();return;
  }
  // Navigate in exactly the same order as the visible watchlist.
  // This keeps keyboard arrows aligned with the current search and sort.
  const items=chartWatchItems();
  const active=CHART_ROW?.key;
  let idx=items.findIndex(x=>chartRowKey(x)===active);
  if(!items.length) return;
  if((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==="c"){
    if(["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName)) return;
    const current=CHART_ROW;
    if(!current?.symbol) return;
    e.preventDefault();
    navigator.clipboard?.writeText(String(current.symbol)).then(()=>{
      const meta=$("chartMeta");
      if(!meta) return;
      const old=meta.textContent;
      meta.textContent=String(current.symbol)+" · copied";
      setTimeout(()=>{if($("chartMeta")?.textContent===String(current.symbol)+" · copied") $("chartMeta").textContent=old;},900);
    }).catch(()=>{});
    return;
  }
  if(e.key==="ArrowDown" || e.key==="ArrowRight"){
    e.preventDefault();
    clearTimeout(chartClickTimer);
    if(idx < items.length-1){
      idx++;
      const r=items[idx]; openChart(chartRowKey(r),r);
    }
    return;
  }
  if(e.key==="ArrowUp" || e.key==="ArrowLeft"){
    e.preventDefault();
    clearTimeout(chartClickTimer);
    if(idx > 0){
      idx--;
      const r=items[idx]; openChart(chartRowKey(r),r);
    }
    return;
  }
  if(e.key==="Home"){e.preventDefault(); const r=items[0]; openChart(chartRowKey(r),r);return;}
  if(e.key==="End"){e.preventDefault(); const r=items[items.length-1]; openChart(chartRowKey(r),r);return;}

});


async function load(){
  try{
    const resp=await fetch("data/results.json?"+Date.now(),{cache:"no-store"});
    if(!resp.ok) throw new Error("HTTP "+resp.status);
    D=await resp.json();
    const lastRefresh=D.generated?new Date(D.generated):null;
    const now=new Date();
    const nextRefresh=new Date(now);
    nextRefresh.setHours(18,0,0,0);
    if(nextRefresh<=now) nextRefresh.setDate(nextRefresh.getDate()+1);
    const fmtIST=d=>d.toLocaleString("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:true});
    $("meta").textContent=`${D.asof||"—"} · ${Number(D.stats?.traded_last_day||0).toLocaleString("en-IN")} stocks traded · Last refresh: ${lastRefresh?fmtIST(lastRefresh):"—"} IST · Next refresh: ${fmtIST(nextRefresh)} IST`;
    const age=(Date.now()-new Date(D.asof))/864e5;
    if(Number.isFinite(age)&&age>4){$("stale").style.display="block";$("stale").textContent=`Data is ${Math.floor(age)} days old.`;}
    render();
    document.body.classList.add("ready");
  }catch(err){
    console.error(err);
    $("meta").textContent="Could not load data/results.json";
    $("foot").textContent="Make sure the local server is running from ~/stock-screener.";
    document.body.classList.add("ready");
  }
}

try{
  const th=localStorage.getItem("scn-theme");
  if(th) document.documentElement.dataset.theme=th;
}catch(_){}
wire();
load();
