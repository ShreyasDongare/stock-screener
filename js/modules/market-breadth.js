function renderMarketBreadth(){
  const body=$("breadthBody"), sub=$("breadthSub"); if(!body) return;
  const data=Array.isArray(D?.market_breadth)?D.market_breadth:[];
  const stockCount=Number(D?.config?.breadth?.stock_list_count)||0;
  sub.textContent=data.length?(stockCount.toLocaleString("en-IN")+" stocks in universe • "+data.length+" NSE trading days"):"No breadth data available";

  // Match the conditional-format thresholds and screenshot-sampled colours from the user sheet.
  const cell=(v,cls)=>'<td class="breadth-'+cls+'">'+(v==null?"—":f2(v))+'</td>';
  const dailyUp=v=>{const n=Number(v);return cell(v,!Number.isFinite(n)?"neutral":n<=35?"negative":n>=200?"positive-strong":n>=75?"mid":"neutral");};
  const dailyDown=v=>{const n=Number(v);return cell(v,!Number.isFinite(n)?"neutral":n<=35?"positive":n>=200?"negative-strong":n>=50?"negative":"neutral");};
  const ratioCell=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<=0.75?"negative":n>2?"positive":"neutral");};
  const qUp=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<=50?"negative":n>=200?"positive":"neutral");};
  const qDown=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<=18?"positive":n>=35?"negative":"neutral");};
  const monthUp25=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<=18?"negative":n>=35?"positive":"neutral");};
  const monthDown25=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n>10?"positive":n<=18?"negative":"neutral");};
  const monthUp13=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<=50?"positive":n>=100?"negative":"neutral");};
  const monthDown13=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<=35?"positive":n>=75?"negative":"neutral");};
  const dma21=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<20?"negative":"neutral");};
  const dma50=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<30?"negative":"neutral");};
  const dma200=v=>{const n=Number(v);return cell(v,v==null||!Number.isFinite(n)?"neutral":n<50?"negative":n>=100?"positive-strong":"neutral");};
  const plainCell=v=>cell(v,"neutral");
  body.innerHTML=data.slice().reverse().map(r=>{
    return '<tr><td class="l">'+esc(r.date)+'</td>'+
      dailyUp(r.up3)+dailyDown(r.down3)+
      ratioCell(r.ratio5)+ratioCell(r.ratio10)+
      qUp(r.up25_q)+qDown(r.down25_q)+
      monthUp25(r.up25_m)+monthDown25(r.down25_m)+
      monthUp13(r.up13_m)+monthDown13(r.down13_m)+
      dma21(r.above21)+dma50(r.above50)+dma200(r.above200)+
      plainCell(r.nifty50)+plainCell(r.daily_return_pct)+
      '</tr>';
  }).join("") || '<tr><td colspan="16" class="empty">No market breadth data available.</td></tr>';
}
function openMarketBreadth(){ renderMarketBreadth(); $("breadthModal")?.classList.add("open"); }
function closeMarketBreadth(){ $("breadthModal")?.classList.remove("open"); }
