let LW = null;
let CHART = null, CHART_ROW = null;
let CHART_LOAD_PROMISE = null;
let CHART_RESIZE_OBSERVER = null;
let CHART_REQUEST_ID = 0;
let CHART_WATCH_RENDERED_MODE = "";

function showChartMessage(title, message, retry=true){
  const modal=$("chartModal"), body=$("chartBody");
  if(!modal || !body) return;
  modal.classList.add("open");
  if(CHART_RESIZE_OBSERVER){try{CHART_RESIZE_OBSERVER.disconnect();}catch(_){} CHART_RESIZE_OBSERVER=null;}
  if(LW){try{LW.remove();}catch(_){} LW=null;}
  CHART_SERIES={};
  body.innerHTML='<div class="chart-state" role="status"><div class="chart-state-icon">⌁</div><h3>'+esc(title)+'</h3><p>'+esc(message)+'</p>'+(retry?'<button type="button" class="btn" id="chartRetryBtn">Retry chart data</button>':'')+'</div>';
  const btn=$("chartRetryBtn");
  if(btn) btn.addEventListener("click",()=>{CHART=null;CHART_LOAD_PROMISE=null;openChart(CHART_ROW?.key||CHART_WATCH_ACTIVE_KEY,CHART_ROW);});
}
async function ensureChartData(force=false){
  if(!force && CHART && typeof CHART==="object") return CHART;
  if(!force && CHART_LOAD_PROMISE) return CHART_LOAD_PROMISE;
  CHART_LOAD_PROMISE=(async()=>{
    const url="data/chart_data.json"+(force?"?retry="+Date.now():"");
    const resp=await fetch(url,{cache:force?"no-store":"default"});
    if(!resp.ok) throw new Error("Chart history request failed (HTTP "+resp.status+").");
    const data=await resp.json();
    if(!data || typeof data!=="object" || Array.isArray(data)) throw new Error("Chart history file has an invalid format.");
    CHART=data;
    return CHART;
  })();
  try{return await CHART_LOAD_PROMISE;}catch(err){CHART_LOAD_PROMISE=null;throw err;}
}
let chartClickTimer = null;
let CHART_SERIES = {};
let CHART_TF = "D";

function weeklyChartData(src){
  const out={dates:[],open:[],high:[],low:[],close:[],volume:[]};
  let cur=null;
  for(let i=0;i<src.dates.length;i++){
    const date=String(src.dates[i]);
    const dt=new Date(date+"T00:00:00Z");
    const day=dt.getUTCDay();
    const monday=new Date(dt);
    const diff=day===0?-6:1-day;
    monday.setUTCDate(dt.getUTCDate()+diff);
    const week=monday.toISOString().slice(0,10);
    if(week!==cur){
      cur=week;
      out.dates.push(week);
      out.open.push(Number(src.open[i]));
      out.high.push(Number(src.high[i]));
      out.low.push(Number(src.low[i]));
      out.close.push(Number(src.close[i]));
      out.volume.push(Number(src.volume[i])||0);
    }else{
      const j=out.close.length-1;
      out.high[j]=Math.max(out.high[j],Number(src.high[i]));
      out.low[j]=Math.min(out.low[j],Number(src.low[i]));
      out.close[j]=Number(src.close[i]);
      out.volume[j]+=(Number(src.volume[i])||0);
    }
  }
  const close=out.close;
  const ema=(span)=>{
    const a=2/(span+1), z=[]; let prev=close[0];
    for(const x of close){prev=a*x+(1-a)*prev;z.push(Number(prev.toFixed(4)));}
    return z;
  };
  const sma=(n)=>close.map((_,i)=>i>=n-1?Number((close.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n).toFixed(4)):null);
  out.ema11=ema(11); out.ema21=ema(21); out.sma50=sma(50);
  return {...src,...out};
}

function chartDataForTimeframe(src){
  return CHART_TF==="W" ? weeklyChartData(src) : src;
}
function closeChart(){
  CHART_REQUEST_ID++;
  $("chartModal").classList.remove("open");
  if(CHART_RESIZE_OBSERVER){try{CHART_RESIZE_OBSERVER.disconnect();}catch(_){} CHART_RESIZE_OBSERVER=null;}
  if(LW){try{LW.remove();}catch(_){} LW=null;}
  CHART_SERIES={};
  CHART_ROW=null;
  CHART_WATCH_MODE="scan";
  $("chartBody").innerHTML="";
}
const CHART_TAGS_KEY="scn-chart-tags";
function getTags(){
  try{
    const v=JSON.parse(localStorage.getItem(CHART_TAGS_KEY)||"{}");
    return v && typeof v==="object" ? v : {};
  }catch(_){ return {}; }
}
function saveTags(tags){
  try{ localStorage.setItem(CHART_TAGS_KEY,JSON.stringify(tags||{})); }catch(_){}
}

const CHART_WATCH_ROW_HEIGHT=44;
const CHART_WATCH_BUFFER=12;
let CHART_WATCH_Q="";
let CHART_WATCH_SCROLL_TOP=null;
let CHART_WATCH_SORT="symbol";
let CHART_WATCH_SORT_DIR=1;
let CHART_WATCH_ITEMS=[];
let CHART_WATCH_ACTIVE_KEY="";
let CHART_WATCH_TAGS={};
let CHART_WATCH_VIRTUAL={start:0,end:0,raf:0};
let CHART_WATCH_MODE="scan";

function navigateChartStock(direction){
  const items=CHART_WATCH_MODE==="colours" ? chartRows() : chartRows();
  if(!items.length) return;
  const currentKey=CHART_ROW ? chartRowKey(CHART_ROW) : CHART_WATCH_ACTIVE_KEY;
  let index=items.findIndex(r=>chartRowKey(r)===currentKey);
  if(index<0 && CHART_ROW){
    index=items.findIndex(r=>String(r.symbol||"").toUpperCase()===String(CHART_ROW.symbol||"").toUpperCase()
      && String(r.exch||"NSE").toUpperCase()===String(CHART_ROW.exch||"NSE").toUpperCase());
  }
  if(index<0) index=0;
  const nextIndex=index+direction;
  if(nextIndex<0 || nextIndex>=items.length) return;
  const next=items[nextIndex];
  CHART_WATCH_ACTIVE_KEY=chartRowKey(next);
  openChart(chartRowKey(next),next);
}
function bindMobileChartSwipe(host){
  if(!host || host.dataset.swipeBound==="1") return;
  host.dataset.swipeBound="1";
  let startX=0,startY=0,startAt=0;
  host.addEventListener("touchstart",e=>{
    if(e.touches.length!==1) return;
    startX=e.touches[0].clientX;
    startY=e.touches[0].clientY;
    startAt=Date.now();
  },{passive:true});
  host.addEventListener("touchend",e=>{
    if(!startAt || !e.changedTouches.length) return;
    const dx=e.changedTouches[0].clientX-startX;
    const dy=e.changedTouches[0].clientY-startY;
    const elapsed=Date.now()-startAt;
    startAt=0;
    if(Math.abs(dx)<70 || Math.abs(dx)<Math.abs(dy)*1.25 || elapsed>800) return;
    navigateChartStock(dx<0?1:-1);
  },{passive:true});
}

function chartRowKey(r){
  return r?.key||((String(r?.exch||"NSE").toUpperCase())+":"+String(r?.symbol||""));
}
function chartRows(){
  if(CHART_WATCH_MODE==="colours"){
    const tags=getTags(), seen=new Set(), out=[];
    Object.keys(SCANS).forEach(tab=>{
      sourceRows(tab).forEach(r=>{
        if(!r||!r.symbol) return;
        const key=chartRowKey(r);
        if(seen.has(key) || !tags[key]) return;
        seen.add(key);
        out.push({...r,__watchColor:tags[key]});
      });
    });
    const order=Object.fromEntries(WATCHLIST_COLORS.map(([color],i)=>[color,i]));
    out.sort((a,b)=>{
      const ca=order[a.__watchColor]??99, cb=order[b.__watchColor]??99;
      if(ca!==cb) return ca-cb;
      return String(a.symbol||"").localeCompare(String(b.symbol||""));
    });
    return out;
  }
  const all=sourceRows(S.tab).filter(r=>r&&r.symbol);
  const seen=new Set();
  return all.filter(r=>{
    const k=chartRowKey(r);
    if(seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}
function chartWatchItems(){
  const all=chartRows(), q=CHART_WATCH_Q.trim().toUpperCase();
  const items=all.filter(r=>!q||String(r.symbol||"").toUpperCase().includes(q));

  const sortValue=(r,key)=>{
    if(key==="symbol") return String(r.symbol||"").toUpperCase();
    if(key==="price") return Number(r.close);
    return Number(r.chg);
  };
  const dir=CHART_WATCH_SORT_DIR;
  const colourOrder=Object.fromEntries(WATCHLIST_COLORS.map(([color],i)=>[color,i]));
  items.sort((a,b)=>{
    // My Watchlist is always grouped by colour first.
    if(CHART_WATCH_MODE==="colours"){
      const ca=colourOrder[a.__watchColor]??99, cb=colourOrder[b.__watchColor]??99;
      if(ca!==cb) return ca-cb;
    }
    const av=sortValue(a,CHART_WATCH_SORT), bv=sortValue(b,CHART_WATCH_SORT);
    if(typeof av==="string" || typeof bv==="string") return dir*String(av).localeCompare(String(bv));
    const an=Number(av), bn=Number(bv);
    if(!Number.isFinite(an) && !Number.isFinite(bn)) return String(a.symbol).localeCompare(String(b.symbol));
    if(!Number.isFinite(an)) return 1;
    if(!Number.isFinite(bn)) return -1;
    const diff=dir*(an-bn);
    return diff!==0 ? diff : String(a.symbol||"").localeCompare(String(b.symbol||""));
  });
  return items;
}

function chartWatchRowHTML(r,activeKey){
  const key=chartRowKey(r);
  const price=Number(r.close), chg=Number(r.chg);
  const priceText=Number.isFinite(price)?f2(price):"—";
  const chgText=Number.isFinite(chg)?((chg>=0?"+":"")+f2(chg)+"%"):"—";
  const chgCls=Number.isFinite(chg)?(chg>=0?"up":"dn"):"";
  const tag=(CHART_WATCH_TAGS||{})[key]||r.__watchColor||"";
  const tagLabel=WATCHLIST_COLORS.find(([color])=>color===tag)?.[1]||"";
  return '<button class="chart-watch-item '+(key===activeKey?"active ":"")+(tag?"tag-"+esc(tag):"")+'" data-watch-key="'+esc(key)+'">'+
    '<span class="wsymbol"><b>'+esc(r.symbol)+'</b><span class="wexch '+(String(r.exch||"").toUpperCase()==="BSE"?"bse":"nse")+'">'+esc(String(r.exch||"NSE").toUpperCase())+'</span></span>'+
    '<span class="wprice">'+priceText+'</span>'+
    '<span class="wchg '+chgCls+'">'+chgText+'</span>'+
  '</button>';
}

function updateChartWatchVirtual(force=false){
  const scroll=$("chartWatchScroll"), spacer=$("chartWatchSpacer"), itemsEl=$("chartWatchItems");
  if(!scroll||!spacer||!itemsEl) return;

  const items=CHART_WATCH_ITEMS;
  const total=items.length;
  spacer.style.height=(total*CHART_WATCH_ROW_HEIGHT)+"px";

  const top=scroll.scrollTop;
  const viewport=Math.max(1,scroll.clientHeight);
  let start=Math.floor(top/CHART_WATCH_ROW_HEIGHT)-CHART_WATCH_BUFFER;
  start=Math.max(0,Math.min(start,total));
  let end=Math.ceil((top+viewport)/CHART_WATCH_ROW_HEIGHT)+CHART_WATCH_BUFFER;
  end=Math.max(start,Math.min(end,total));

  if(!force && start===CHART_WATCH_VIRTUAL.start && end===CHART_WATCH_VIRTUAL.end) return;
  CHART_WATCH_VIRTUAL.start=start;
  CHART_WATCH_VIRTUAL.end=end;
  itemsEl.style.transform="translateY("+(start*CHART_WATCH_ROW_HEIGHT)+"px)";
  itemsEl.innerHTML=items.slice(start,end).map(r=>chartWatchRowHTML(r,CHART_WATCH_ACTIVE_KEY)).join("");
}

function scheduleChartWatchVirtual(){
  if(CHART_WATCH_VIRTUAL.raf) return;
  CHART_WATCH_VIRTUAL.raf=requestAnimationFrame(()=>{
    CHART_WATCH_VIRTUAL.raf=0;
    updateChartWatchVirtual(false);
  });
}

function ensureChartWatchActiveVisible(){
  const scroll=$("chartWatchScroll");
  if(!scroll||!CHART_WATCH_ITEMS.length||!CHART_WATCH_ACTIVE_KEY) return;
  const index=CHART_WATCH_ITEMS.findIndex(r=>chartRowKey(r)===CHART_WATCH_ACTIVE_KEY);
  if(index<0) return;

  const top=index*CHART_WATCH_ROW_HEIGHT;
  const bottom=top+CHART_WATCH_ROW_HEIGHT;
  const viewTop=scroll.scrollTop;
  const viewBottom=viewTop+scroll.clientHeight;

  if(top < viewTop) scroll.scrollTop=Math.max(0,top-8);
  else if(bottom > viewBottom) scroll.scrollTop=Math.max(0,bottom-scroll.clientHeight+8);
}

function renderChartWatchlist(activeKey){
  const el=$("chartWatchlist"); if(!el) return;
  CHART_WATCH_ACTIVE_KEY=activeKey||"";
  CHART_WATCH_TAGS=getTags();

  if(CHART_WATCH_MODE==="colours"){
    // Keep colour-group state outside the DOM. openChart() rebuilds the
    // chart body, so DOM-only state is lost when another stock is selected.
    const oldScroll=$("chartWatchScroll");
    if(oldScroll) CHART_WATCH_COLOUR_SCROLL_TOP=oldScroll.scrollTop;
    el.querySelectorAll("wa-details[data-colour-group]").forEach(d=>{
      CHART_WATCH_COLOUR_OPEN[d.dataset.colourGroup]=!!d.open;
    });

    const q=CHART_WATCH_Q.trim().toUpperCase();
    const groups={};
    WATCHLIST_COLORS.forEach(([color,label])=>groups[color]={label,items:[]});

    const seen=new Set();
    Object.keys(SCANS).forEach(tab=>{
      sourceRows(tab).forEach(r=>{
        if(!r||!r.symbol) return;
        const key=chartRowKey(r), color=CHART_WATCH_TAGS[key];
        if(!color || seen.has(key) || !groups[color]) return;
        seen.add(key);
        if(!q || String(r.symbol).toUpperCase().includes(q)){
          groups[color].items.push({...r,__watchColor:color});
        }
      });
    });

    el.innerHTML=
      '<div class="chart-watch-head">'+
        '<div class="chart-watch-title">My Colour Watchlist</div>'+
        '<input id="chartWatchSearch" class="chart-watch-search" placeholder="Search symbol..." value="'+esc(CHART_WATCH_Q)+'">'+
        '<div class="chart-watch-columns"><span>Stock</span><span style="text-align:right">Price (₹)</span><span style="text-align:right">Change %</span></div>'+
      '</div>'+
      '<div class="chart-watch-scroll colour-scroll" id="chartWatchScroll">'+
        '<div class="colour-watch-groups">'+
          WATCHLIST_COLORS.filter(([color])=>groups[color].items.length).map(([color,label])=>{
            const items=groups[color].items.sort((a,b)=>String(a.symbol).localeCompare(String(b.symbol)));
            const isOpen=CHART_WATCH_COLOUR_OPEN[color]===undefined ? true : CHART_WATCH_COLOUR_OPEN[color];
            const openAttr=isOpen ? ' open' : '';
            const summary='<span class="colour-watch-summary '+color+'" slot="summary"><span class="cw-dot"></span><span class="cw-name">'+label+' Tag</span><span class="cw-count">'+items.length+'</span></span>';
            return '<wa-details class="colour-watch-details '+color+'" data-colour-group="'+color+'"'+openAttr+'>'+summary+
              items.map(r=>chartWatchRowHTML(r,CHART_WATCH_ACTIVE_KEY)).join("")+
              '</wa-details>';
          }).join("")+
        '</div>'+
      '</div>'+
      '<div class="chart-watch-help">Click = EOD chart · Double-click = TradingView</div>';

    const search=$("chartWatchSearch");
    search?.addEventListener("input",e=>{
      CHART_WATCH_Q=e.target.value;
      renderChartWatchlist(CHART_ROW?chartRowKey(CHART_ROW):"");
      requestAnimationFrame(()=>{const s=$("chartWatchSearch");s?.focus();s?.setSelectionRange(CHART_WATCH_Q.length,CHART_WATCH_Q.length);});
    });

    const scroll=$("chartWatchScroll");
    if(scroll){
      scroll.scrollTop=Math.max(0,Number(CHART_WATCH_COLOUR_SCROLL_TOP)||0);
      scroll.addEventListener("scroll",()=>{
        CHART_WATCH_COLOUR_SCROLL_TOP=scroll.scrollTop;
      },{passive:true});
      // Web Components can finish applying <wa-details open> one frame later.
      requestAnimationFrame(()=>{
        scroll.scrollTop=Math.max(0,Number(CHART_WATCH_COLOUR_SCROLL_TOP)||0);
        requestAnimationFrame(()=>{
          scroll.scrollTop=Math.max(0,Number(CHART_WATCH_COLOUR_SCROLL_TOP)||0);
        });
      });
    }
    el.querySelectorAll("wa-details[data-colour-group]").forEach(d=>{
      d.addEventListener("toggle",()=>{
        CHART_WATCH_COLOUR_OPEN[d.dataset.colourGroup]=!!d.open;
      });
    });
    return;
  }
  // Normal scan watchlist keeps the existing virtual-scroller behaviour.
  CHART_WATCH_ITEMS=chartWatchItems();
  CHART_WATCH_VIRTUAL={start:0,end:0,raf:0};
  const previousScrollTop=CHART_WATCH_SCROLL_TOP;
  CHART_WATCH_SCROLL_TOP=null;
  const sortMark=(key)=>CHART_WATCH_SORT===key?(CHART_WATCH_SORT_DIR>0?" ▲":" ▼"):"";

  el.innerHTML=
    '<div class="chart-watch-head">'+
      '<div class="chart-watch-title">Scanned Stocks</div>'+
      '<input id="chartWatchSearch" class="chart-watch-search" placeholder="Search symbol..." value="'+esc(CHART_WATCH_Q)+'">'+
      '<div class="chart-watch-columns">'+
        '<button type="button" data-watch-sort="symbol" class="'+(CHART_WATCH_SORT==="symbol"?"active":"")+'">Stock'+sortMark("symbol")+'</button>'+
        '<button type="button" data-watch-sort="price" class="'+(CHART_WATCH_SORT==="price"?"active":"")+'">Price (₹)'+sortMark("price")+'</button>'+
        '<button type="button" data-watch-sort="chg" class="'+(CHART_WATCH_SORT==="chg"?"active":"")+'">Change %'+sortMark("chg")+'</button>'+
      '</div>'+
    '</div>'+
    '<div class="chart-watch-scroll" id="chartWatchScroll">'+
      '<div class="chart-watch-spacer" id="chartWatchSpacer"><div class="chart-watch-items" id="chartWatchItems"></div></div>'+
    '</div>'+
    '<div class="chart-watch-help">Click = EOD chart · Double-click = TradingView</div>';

  updateChartWatchVirtual(true);
  requestAnimationFrame(()=>updateChartWatchVirtual(true));
  const scroll=$("chartWatchScroll");
  if(scroll){
    scroll.scrollTop=Math.max(0,Number(previousScrollTop)||0);
    updateChartWatchVirtual(true);
    requestAnimationFrame(()=>{
      updateChartWatchVirtual(true);
      requestAnimationFrame(()=>{
        if(scroll && previousScrollTop !== null){
          scroll.scrollTop=Math.max(0,Number(previousScrollTop)||0);
          updateChartWatchVirtual(true);
        }
      });
    });
    scroll.addEventListener("scroll",scheduleChartWatchVirtual,{passive:true});
  }
  const search=$("chartWatchSearch");
  search?.addEventListener("input",e=>{
    CHART_WATCH_Q=e.target.value;
    renderChartWatchlist(CHART_ROW?chartRowKey(CHART_ROW):"");
  });
}
function bindChartTooltip(chart,d,candle,ema11,ema21,sma50,volume){
  const host=$("chartHost");
  const stats=$("chartStats");
  const fmt=v=>Number.isFinite(Number(v))?Number(v).toLocaleString("en-IN",{maximumFractionDigits:2}):"—";
  const pctForIndex=i=>{
    if(i<=0) return NaN;
    const cur=Number(d.close[i]), prev=Number(d.close[i-1]);
    return Number.isFinite(cur)&&Number.isFinite(prev)&&prev!==0 ? (cur/prev-1)*100 : NaN;
  };
  const pctHTML=(label,pct)=>{
    const cls=Number.isFinite(pct) ? (pct>=0 ? "positive" : "negative") : "";
    const value=Number.isFinite(pct) ? ((pct>=0?"+":"")+fmt(pct)+"%") : "—";
    return '<span class="chart-stat-pill '+cls+'">'+label+' <b>('+value+')</b></span>';
  };
  const render=({cd,index,crosshair=false}={})=>{
    if(!stats) return;
    if(!cd || index<0){
      stats.innerHTML="";
      return;
    }
    const crossPct=pctForIndex(index);
    const candleClass=Number(cd.close)>=Number(cd.open) ? "positive" : "negative";
    stats.innerHTML=
      '<span class="chart-stat-pill '+candleClass+'">O <b>'+fmt(cd.open)+'</b></span>'+
      '<span class="chart-stat-pill '+candleClass+'">H <b>'+fmt(cd.high)+'</b></span>'+
      '<span class="chart-stat-pill '+candleClass+'">L <b>'+fmt(cd.low)+'</b></span>'+
      '<span class="chart-stat-pill '+candleClass+'">C <b>'+fmt(cd.close)+'</b></span>'+
      '<span class="chart-stat-gap"></span>'+
      pctHTML("Last",pctForIndex(d.close.length-1))+
      pctHTML("Current",crossPct);
  };

  // Start with the latest candle.
  const lastIndex=d.close.length-1;
  render({
    cd:{open:d.open[lastIndex],high:d.high[lastIndex],low:d.low[lastIndex],close:d.close[lastIndex]},
    index:lastIndex
  });

  chart.subscribeCrosshairMove(p=>{
    if(!p || !p.point || p.point.x<0 || p.point.y<0 ||
       p.point.x>host.clientWidth || p.point.y>host.clientHeight || !p.time){
      return;
    }
    const cd=p.seriesData.get(candle);
    if(!cd) return;
    const time=String(p.time).slice(0,10);
    const index=d.dates.findIndex(x=>String(x).slice(0,10)===time);
    render({cd,index,crosshair:true});
  });
}

async function openChart(key,row){
  CHART_TF="D";
  if(CHART_WATCH_MODE!=="colours") CHART_WATCH_MODE="scan";
  const requestId=++CHART_REQUEST_ID;
  CHART_ROW=row||CHART_ROW||{key,symbol:String(key||"").split(":").slice(1).join(":"),exch:String(key||"NSE:").split(":")[0]};
  if(typeof LightweightCharts==="undefined"){
    showChartMessage("Chart library unavailable","The chart library did not load. Check your internet connection and reload the dashboard.",false);
    return;
  }
  $("chartModal").classList.add("open");
  if(!CHART) showChartMessage("Loading chart history","Fetching daily candles for "+key+"…",false);
  try{
    await ensureChartData();
  }catch(err){
    if(requestId!==CHART_REQUEST_ID) return;
    showChartMessage("Could not load chart history",String(err?.message||"Network error while loading chart_data.json."),true);
    const retry=$("chartRetryBtn");
    if(retry) retry.onclick=async()=>{
      const current=CHART_ROW;
      showChartMessage("Retrying…","Fetching chart history again.",false);
      try{await ensureChartData(true);if(current) openChart(current.key||chartRowKey(current),current);}
      catch(e){showChartMessage("Chart history still unavailable",String(e?.message||"Please check your connection and try again."),true);}
    };
    return;
  }
  if(requestId!==CHART_REQUEST_ID) return;
  if(!CHART || !CHART[key]){
    CHART_ROW=Object.assign(CHART_ROW||{},row||{},{key});
    showChartMessage("Historical data unavailable",key+" is not present in chart_data.json. Scanner results are still available; retry after the next data refresh.",true);
    const retry=$("chartRetryBtn");
    if(retry) retry.onclick=async()=>{
      const current=CHART_ROW;
      showChartMessage("Retrying…","Checking chart history again.",false);
      try{await ensureChartData(true);if(current) openChart(current.key||key,current);}
      catch(e){showChartMessage("Chart history still unavailable",String(e?.message||"Please check your connection and try again."),true);}
    };
    return;
  }
  const baseD=CHART[key];
  if(!baseD.dates?.length || !baseD.close?.length){
    showChartMessage("No usable historical candles","History exists for "+key+" but contains no usable daily candles.",true);
    return;
  }
  const d=chartDataForTimeframe(baseD), n=d.dates.length;
  if(!n){showChartMessage("No candles for this timeframe","Try switching to Daily or retry the chart.",true);return;}
  const dark=document.documentElement.dataset.theme==="dark";
  const ct=dark ? {
    bg:"#0D131A", text:"#91A2B3", grid:"rgba(125,145,165,.075)", border:"#293542",
    cross:"#71869B", crossLabel:"#33485B", up:"#20A46B", down:"#D95353",
    ema11:"rgba(88,166,230,.62)", ema21:"rgba(231,184,75,.62)", sma50:"rgba(177,125,230,.52)", volume:"#3E5368"
  } : {
    bg:"#FFFFFF", text:"#526273", grid:"rgba(82,98,115,.10)", border:"#DCE2E8",
    cross:"#7A8C9D", crossLabel:"#526273", up:"#17794F", down:"#B83232",
    ema11:"rgba(42,120,184,.62)", ema21:"rgba(176,122,0,.62)", sma50:"rgba(123,79,163,.52)", volume:"#8A9AAA"
  };
  CHART_ROW=row||null;
  const last=n-1, close=Number(d.close[last]), prev=n>1?Number(d.close[last-1]):NaN;
  const dayPct=Number.isFinite(prev)&&prev!==0?(close/prev-1)*100:NaN;
  const fmt=x=>Number.isFinite(x)?x.toLocaleString("en-IN",{maximumFractionDigits:2}):"—";

  $("chartTitle").textContent=d.exch+":"+d.symbol;
  $("chartMeta").textContent=d.dates[0]+" → "+d.dates[last]+" · "+n+" "+(CHART_TF==="W"?"weeks":"sessions")+" · "+(CHART_TF==="W"?"Weekly":"EOD");
  document.querySelectorAll("[data-chart-tf]").forEach(b=>b.classList.toggle("active",b.dataset.chartTf===CHART_TF));
  const statsEl=$("chartStats");
  if(statsEl){
    const adrValues=[];
    const adrLookback=Math.min(20,n);
    for(let i=n-adrLookback;i<n;i++){
      const hi=Number(d.high[i]),lo=Number(d.low[i]),cl=Number(d.close[i]);
      if(Number.isFinite(hi)&&Number.isFinite(lo)&&Number.isFinite(cl)&&cl>0) adrValues.push((hi-lo)/cl*100);
    }
    const adr=adrValues.length?adrValues.reduce((a,b)=>a+b,0)/adrValues.length:NaN;
    statsEl.innerHTML=
      '<span class="chart-stat-pill '+(dayPct>=0?"positive":"negative")+'">₹'+fmt(close)+' ('+(dayPct>=0?'+':'')+fmt(dayPct)+'%)</span>'+
      '<span class="chart-stat-pill adr">ADR(20) '+fmt(adr)+'%</span>';
  }

  if(CHART_RESIZE_OBSERVER){try{CHART_RESIZE_OBSERVER.disconnect();}catch(_){} CHART_RESIZE_OBSERVER=null;}
  if(LW){try{LW.remove();}catch(_){} LW=null;}
  CHART_SERIES={};
  const body=$("chartBody");
  CHART_WATCH_ITEMS=CHART_WATCH_MODE==="colours" ? chartRows() : chartWatchItems();
  body.innerHTML='<div class="chart-host" id="chartHost"></div><div class="chart-statsbar chart-stats-overlay" id="chartStats" aria-live="polite"></div>';
  $("chartModal").classList.add("open");
  const host=$("chartHost");
  bindMobileChartSwipe(host);

  // The modal starts hidden (display:none). Create the chart only after the
  // modal is open and let Lightweight Charts observe the host size. This avoids
  // the zero-size canvas that can occur when a flex child is measured too early.
  let chart;
  try{ chart=LightweightCharts.createChart(host,{
    width:Math.max(1,host.clientWidth),
    height:Math.max(1,host.clientHeight),
    layout:{background:{type:LightweightCharts.ColorType.Solid,color:ct.bg},textColor:ct.text,fontFamily:"IBM Plex Mono, monospace",fontSize:11},
    grid:{vertLines:{color:ct.grid},horzLines:{color:ct.grid}},
    rightPriceScale:{borderColor:ct.border,scaleMargins:{top:.06,bottom:.24},minimumWidth:74},
    timeScale:{borderColor:ct.border,timeVisible:false,secondsVisible:false,rightOffset:6,barSpacing:8,minBarSpacing:2},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal,vertLine:{color:ct.cross,width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:ct.crossLabel},horzLine:{color:ct.cross,width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:ct.crossLabel}},
    handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},
    handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:{time:true,price:true},axisDoubleClickReset:true},
    localization:{priceFormatter:p=>Number(p).toLocaleString("en-IN",{maximumFractionDigits:2})}
  }); }catch(err){
    console.error("Chart creation failed",err);
    showChartMessage("Chart could not be created",String(err?.message||"Unexpected chart rendering error."),true);
    return;
  }
  LW=chart;

  // Mobile: dragging directly on the right price axis scales the visible price range.
  let axisTouchY=null;
  host.addEventListener("touchstart",e=>{
    if(e.touches.length!==1) return;
    const t=e.touches[0];
    axisTouchY=(t.clientX-host.getBoundingClientRect().left)>=host.clientWidth-92?t.clientY:null;
  },{passive:true});
  host.addEventListener("touchmove",e=>{
    if(axisTouchY===null||e.touches.length!==1||!LW||LW!==chart) return;
    const t=e.touches[0], y=t.clientY, delta=y-axisTouchY;
    axisTouchY=y;
    try{
      const ps=chart.priceScale("right"), range=ps.getVisibleRange();
      if(!range||!Number.isFinite(range.from)||!Number.isFinite(range.to)||range.to<=range.from) return;
      ps.setAutoScale(false);
      const center=(range.from+range.to)/2;
      const factor=Math.exp(delta*0.012);
      const half=(range.to-range.from)*factor/2;
      ps.setVisibleRange({from:center-half,to:center+half});
    }catch(_){}
  },{passive:true});
  host.addEventListener("touchend",()=>{axisTouchY=null;},{passive:true});
  host.addEventListener("touchcancel",()=>{axisTouchY=null;},{passive:true});

  try{
  // Use Lightweight Charts' native business-day format. The chart data is EOD
  // YYYY-MM-DD, which is the most reliable representation for NSE sessions.
  const chartDate=(value)=>{
    const s=String(value||"").slice(0,10);
    return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null;
  };
  const candles=d.dates.map((time,i)=>({
    time:chartDate(time),open:+d.open[i],high:+d.high[i],low:+d.low[i],close:+d.close[i]
  })).filter(x=>x.time&&[x.open,x.high,x.low,x.close].every(Number.isFinite));
  const candle=chart.addSeries(LightweightCharts.CandlestickSeries,{
    upColor:ct.up,downColor:ct.down,borderUpColor:ct.up,borderDownColor:ct.down,wickUpColor:ct.up,wickDownColor:ct.down,
    priceLineVisible:false,lastValueVisible:true
  });
  if(!candles.length){showChartMessage("No valid candles found","Historical data could not be converted into chart candles for "+key+".",true);return;}
  candle.setData(candles);

  const ema11=chart.addSeries(LightweightCharts.LineSeries,{color:ct.ema11,lineWidth:1,lastValueVisible:false,priceLineVisible:false});
  const ema21=chart.addSeries(LightweightCharts.LineSeries,{color:ct.ema21,lineWidth:1,lastValueVisible:false,priceLineVisible:false});
  const sma50=chart.addSeries(LightweightCharts.LineSeries,{color:ct.sma50,lineWidth:1,lastValueVisible:false,priceLineVisible:false});
  ema11.setData(d.dates.map((time,i)=>({time:chartDate(time),value:+d.ema11[i]})).filter(x=>x.time&&Number.isFinite(x.value)));
  ema21.setData(d.dates.map((time,i)=>({time:chartDate(time),value:+d.ema21[i]})).filter(x=>x.time&&Number.isFinite(x.value)));
  sma50.setData(d.dates.map((time,i)=>({time:chartDate(time),value:+d.sma50[i]})).filter(x=>x.time&&Number.isFinite(x.value)&&x.value>0));

  // Put volume in a separate lower pane. Lightweight Charts v5 takes pane index
  // as the third addSeries argument; "pane" inside options is ignored.
  let volumePaneIndex=1;
  try{chart.addPane();}catch(_){volumePaneIndex=0;}
  const volume=chart.addSeries(LightweightCharts.HistogramSeries,{
    priceFormat:{type:"volume"},priceScaleId:"volume",
    lastValueVisible:false,priceLineVisible:false,color:ct.volume
  },volumePaneIndex);
  if(volumePaneIndex===0){
    volume.priceScale().applyOptions({scaleMargins:{top:.83,bottom:0},borderVisible:false});
  }else{
    try{
      const panes=chart.panes();
      if(panes[1]) panes[1].setHeight(Math.max(90,Math.min(130,Math.round(host.clientHeight*.19))));
    }catch(_){}
  }
  volume.setData(d.dates.map((time,i)=>({
    time:chartDate(time),value:+d.volume[i],color:+d.close[i]>=+d.open[i]?ct.up:ct.down
  })).filter(x=>x.time&&Number.isFinite(x.value)));

  CHART_SERIES={candle,ema11,ema21,sma50,volume};
  bindChartTooltip(chart,d,candle,ema11,ema21,sma50,volume);
  }catch(err){
    console.error("Chart data/render failed",err);
    showChartMessage("Chart rendering failed",String(err?.message||"The history could not be drawn. Retry to try again."),true);
    return;
  }

  // EMA11, EMA21 and SMA50 are shown; other setup labels remain hidden.


  const resize=()=>{
    if(!LW || LW!==chart) return;
    const w=Math.max(1,host.clientWidth);
    const h=Math.max(1,host.clientHeight);
    try{LW.resize(w,h,true);}catch(_){try{LW.applyOptions({width:w,height:h});}catch(__){}}
  };
  CHART_RESIZE_OBSERVER=new ResizeObserver(()=>{resize();});
  CHART_RESIZE_OBSERVER.observe(host);
  // Default view: latest 120 trading days, with 12-candle right breathing room.
  chart.applyOptions({rightPriceScale:{scaleMargins:{top:.18,bottom:.12}}});
  requestAnimationFrame(()=>{
    resize();
    try{
      const from=Math.max(0,n-120);
      chart.timeScale().setVisibleLogicalRange({from,to:n+12});
    }catch(_){
      try{chart.timeScale().fitContent();}catch(__){}
    }
    requestAnimationFrame(resize);
  });
}
