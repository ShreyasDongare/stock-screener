(() => {
  const $r = id => document.getElementById(id);
  const state = { data: null, selected: "today", dates: [] };
  const escR = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const isoDate = date => {
    const parts = new Intl.DateTimeFormat("en-CA", {timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(date);
    const v = Object.fromEntries(parts.map(p=>[p.type,p.value]));
    return v.year+"-"+v.month+"-"+v.day;
  };
  const parseISO = value => {
    const [y,m,d] = String(value).split("-").map(Number);
    return new Date(Date.UTC(y,m-1,d,12));
  };
  const addDays = (date, count) => { const d=new Date(date); d.setUTCDate(d.getUTCDate()+count); return d; };
  const formatDate = value => {
    const d=parseISO(value);
    return new Intl.DateTimeFormat("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",year:"numeric"}).format(d);
  };
  const isTradingDay = (date, holidays) => {
    const weekday=date.getUTCDay();
    return weekday!==0 && weekday!==6 && !holidays.has(isoDate(date));
  };
  const dateSet = () => {
    const now = new Date();
    const today = isoDate(now);
    const holidays = new Set((state.data?.holidays || []).map(String));
    let last = addDays(parseISO(today),-1);
    for(let i=0;i<15 && !isTradingDay(last,holidays);i++) last=addDays(last,-1);
    return [
      {id:"last",label:"Last Trading Day",date:isoDate(last)},
      {id:"today",label:"Today",date:today},
      {id:"tomorrow",label:"Tomorrow",date:isoDate(addDays(parseISO(today),1))}
    ];
  };
  const resultRows = date => (state.data?.results || []).filter(r => String(r.date || r.meeting_date || "")===date)
    .sort((a,b)=>String(a.symbol||"").localeCompare(String(b.symbol||"")));
  const screenerUrl = symbol => "https://www.screener.in/company/"+encodeURIComponent(String(symbol||"").trim())+"/";
  const tvUrl = symbol => "https://www.tradingview.com/chart/?symbol="+encodeURIComponent("NSE:"+String(symbol||"").trim());
  function renderTabs(){
    const tabs=$r("resultsTabs"); if(!tabs) return;
    tabs.innerHTML=state.dates.map(tab=>'<button type="button" class="results-date-tab" role="tab" data-result-date="'+tab.id+'" aria-selected="'+(state.selected===tab.id)+'"><b>'+escR(tab.label)+'</b><span>'+escR(formatDate(tab.date))+'</span></button>').join("");
  }
  function renderRows(){
    const content=$r("resultsContent"), tab=state.dates.find(x=>x.id===state.selected);
    if(!content || !tab) return;
    const rows=resultRows(tab.date);
    if(!state.data){
      content.innerHTML='<div class="results-empty">Could not load the results calendar. Check the data file and try refreshing the page.</div>';
      return;
    }
    if(!rows.length){
      content.innerHTML='<div class="results-empty">No result meetings/filings found for '+escR(formatDate(tab.date))+'.<br><br><a href="https://www.nseindia.com/companies-listing/corporate-filings-board-meetings" target="_blank" rel="noopener noreferrer">Check NSE Board Meetings ↗</a></div>';
      return;
    }
    content.innerHTML='<table class="results-table"><thead><tr><th>Stock / Company</th><th>Result / Meeting</th><th>Status</th><th>Announcement</th></tr></thead><tbody>'+rows.map(r=>{
      const symbol=String(r.symbol||"").trim();
      const status=String(r.status||"Scheduled");
      const official=r.official_url||"https://www.nseindia.com/companies-listing/corporate-filings-board-meetings";
      return '<tr><td><a class="results-stock" href="'+screenerUrl(symbol)+'" target="_blank" rel="noopener noreferrer">'+escR(symbol||r.company_name||"Unknown")+'</a><span class="results-links"><a class="results-link" href="'+screenerUrl(symbol)+'" target="_blank" rel="noopener noreferrer" title="Open '+escR(symbol)+' on Screener.in" aria-label="Open '+escR(symbol)+' on Screener.in"><img src="https://www.screener.in/favicon.ico" alt=""></a><a class="results-link" href="'+tvUrl(symbol)+'" target="_blank" rel="noopener noreferrer" title="Open '+escR(symbol)+' on TradingView" aria-label="Open '+escR(symbol)+' on TradingView"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M2 6h12l-2.1 3H8.7L4.5 15H1l3.1-5.3H1.2L2 6zm10.2 0H23l-5.1 9h-3.6l3.4-6h-3.9l-1.6 3H8.8l3.4-6zm-1.5 10h3.4l-2.1 3.7H8.6l2.1-3.7z"/></svg></a></span><div style="font-size:10px;color:var(--mute);margin-top:3px">'+escR(r.company_name||"")+'</div></td><td>'+escR(r.purpose||r.period||"Financial Results")+'</td><td><span class="results-status">'+escR(status)+'</span></td><td><a href="'+escR(official)+'" target="_blank" rel="noopener noreferrer">NSE ↗</a></td></tr>';
    }).join("")+'</tbody></table>';
  }
  async function loadData(){
    try{
      const response=await fetch("data/results_calendar.json?"+Date.now(),{cache:"no-store"});
      if(!response.ok) throw new Error("HTTP "+response.status);
      state.data=await response.json();
      $r("resultsSub").textContent="Exchange calendar · Updated "+(state.data.generated_at ? new Date(state.data.generated_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"})+" IST" : "timestamp unavailable");
    }catch(error){
      console.error("Results calendar load failed",error);
      state.data=null;
      $r("resultsSub").textContent="Results data unavailable";
    }
    state.dates=dateSet();
    renderTabs();
    renderRows();
  }
  function open(){ $r("resultsModal")?.classList.add("open"); if(!state.data) loadData(); }
  function close(){ $r("resultsModal")?.classList.remove("open"); }
  $r("resultsOpen")?.addEventListener("click",open);
  $r("resultsClose")?.addEventListener("click",close);
  $r("resultsModal")?.addEventListener("click",e=>{if(e.target.id==="resultsModal")close();});
  $r("resultsTabs")?.addEventListener("click",e=>{
    const button=e.target.closest("[data-result-date]");
    if(!button) return;
    state.selected=button.dataset.resultDate;
    renderTabs(); renderRows();
  });
  document.addEventListener("keydown",e=>{if(e.key==="Escape")close();});
  state.dates=dateSet();
  renderTabs();
})();