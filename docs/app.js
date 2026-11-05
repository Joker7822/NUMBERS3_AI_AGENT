const el=id=>document.getElementById(id);
const set=(id,value)=>{const node=el(id);if(node)node.textContent=value==null?"—":String(value)};
const mk=(tag,text)=>{const node=document.createElement(tag);node.textContent=String(text);return node};
const digits=n=>typeof n==="string"&&/^\d{3}$/.test(n);
const integer=n=>Number.isInteger(n)&&n>=0;
const japTime=s=>{if(!s)return"—";const d=new Date(s);return Number.isNaN(d.getTime())?"—":new Intl.DateTimeFormat("ja-JP",{timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(d)+" JST"};
const jaNum=n=>integer(n)?n.toLocaleString("ja-JP"):"—";

function validate(data){
  if(!data||data.version!=="numbers3-dashboard-v1"||data.product!=="Numbers3"||
      !integer(data.verified_draws)||!integer(data.secondary_research_draws)||
      !integer(data.issued_forecasts)||data.formally_graded_forecasts!==0||
      data.prediction_skill_confirmed!==false||
      data.automatic_production_promotion!==false||
      data.actual_purchase_profit_yen!==null||
      !Array.isArray(data.warnings)||data.warnings.some(x=>typeof x!=="string"))
    throw new Error("Numbers3監査データの安全性を確認できません");
  for(const [name,row] of [["verified",data.latest_verified_draw],["secondary",data.latest_secondary_draw]]){
    if(row&&( !integer(row.round)||!digits(row.winning_number)||
       !/^\d{4}-\d{2}-\d{2}$/.test(row.draw_date)||
       (name==="verified"&&(row.verification!=="bank_primary_rakuten_publication_match"||
         !/^[a-f0-9]{64}$/.test(row.bank_sha256)||!/^[a-f0-9]{64}$/.test(row.rakuten_sha256)))))
      throw new Error("未検証の抽せん結果を確認済みと表示できません");
  }
  const research=data.research||{};
  if(research.prediction_skill_confirmed===true||research.production_model_changed===true||
      research.officially_verified===true)
    throw new Error("研究結果の正式実績への転用は禁止です");
  const forecast=research.next_research_candidate;
  if(forecast&&(forecast.status!=="research_only_not_issued_not_purchased"||
      !digits(forecast.number)||forecast.officially_verified!==false||
      forecast.actual_purchase!==false||forecast.draw_date!==null||
      forecast.round!==forecast.training_last_round+1))
    throw new Error("最新の研究予測の証拠が不足しています");
  const week=data.recent_week;
  if(!week||!Array.isArray(week.retrospective_rows)||!Array.isArray(week.issued_rows)||
      !/^\d{4}-\d{2}-\d{2}$/.test(week.start_date)||!/^\d{4}-\d{2}-\d{2}$/.test(week.end_date)||
      week.retrospective_rows.length>7||!integer(week.research_straight_hits)||
      week.research_straight_hits!==week.retrospective_rows.filter(x=>x.research_hit===1).length||
      week.retrospective_rows.some(r=>!digits(r.research_number)||!digits(r.actual)||
        !["single_rakuten_publisher_not_officially_verified",
          "two_secondary_publishers_overlap_checked_not_bank_verified"].includes(r.source_status)||
        r.research_hit!==Number(r.research_number===r.actual)||
        !(r.draw_date>=week.start_date&&r.draw_date<=week.end_date))||
      week.issued_rows.some(r=>r.status!=="unwitnessed_not_formally_graded"||
        !(r.draw_date>=week.start_date&&r.draw_date<=week.end_date)))
    throw new Error("7日間の参考照合または予測発行の権限が不正です");
  return data;
}
function addRow(target,parts){
  const tr=document.createElement("tr");
  parts.forEach((part,index)=>tr.appendChild(mk(index===0?"th":"td",part)));
  target.appendChild(tr);
}
function render(data){
  set("generated-time","データ生成 "+japTime(data.generated_at_jst));
  set("verified-count",jaNum(data.verified_draws));
  set("secondary-count",jaNum(data.secondary_research_draws));
  set("evaluated-count",jaNum(data.research?.evaluated_draws));
  set("graded-count",data.formally_graded_forecasts);
  const bank=data.latest_verified_draw,secondary=data.latest_secondary_draw;
  set("source-badge",bank?"銀行＋楽天の照合記録あり":secondary?"研究用データあり・銀行照合待ち":"取得待ち・公式照合なし");
  el("source-badge").className="state-pill"+(bank?"":" warn");
  set("verified-number",bank?bank.winning_number.split("").join(" "):"— — —");
  set("verified-meta",bank?"第"+bank.round+"回 / "+bank.draw_date:"一次・二次の一致データ未取得");
  set("secondary-number",secondary?secondary.winning_number.split("").join(" "):"— — —");
  set("secondary-meta",secondary?"第"+secondary.round+"回 / "+secondary.draw_date+" / 未照合参考":"楽天公開元の取得待ち");
  const cand=data.research?.next_research_candidate;
  set("candidate-number",cand?cand.number.split("").join(" "):"— — —");
  set("candidate-round",cand?"第"+cand.round+"回":"研究生成待ち");
  set("candidate-model",cand?cand.model:"—");
  set("candidate-cutoff",cand?"第"+cand.training_last_round+"回":"—");
  set("candidate-note",cand?"研究候補・未発行・未購入。対象の公式抽せん日は確認できません。":"履歴不足のため予測候補を生成していません。");
  const week=data.recent_week;
  set("week-range",week.start_date+" 〜 "+week.end_date+" / 日本時間（当日を含む7暦日）");
  const table=el("week-rows");table.replaceChildren();
  for(const row of week.retrospective_rows) addRow(table,[
    "第"+row.round+"回 / "+row.draw_date,
    row.research_number+"（"+row.research_model+"）",
    row.actual+"（楽天参考）",
    row.research_hit===1?"参考一致・正式実績外":"参考不一致"
  ]);
  if(!week.retrospective_rows.length)addRow(table,["対象期間の研究結果なし","—","—","研究再計算待ち"]);
  set("week-hits",week.research_straight_hits+"件 / "+week.retrospective_rows.length+"回（研究参考）");
  set("issue-count",data.issued_forecasts+"件（独立公開証拠は未確認）");
  const published=el("issued-rows");published.replaceChildren();
  for(const row of week.issued_rows)addRow(published,[
    "第"+row.round+"回 / "+row.draw_date,
    row.number+"（"+row.mode+"）",
    row.winning_number||"未照合",
    "公開証拠未確認・正式採点不可"
  ]);
  if(!week.issued_rows.length)addRow(published,["事前発行記録なし","—","—","正式採点0件"]);
  set("research-hits",jaNum(data.research?.research_straight_hits)+"回");
  set("uniform-hits",jaNum(data.research?.reference_straight_hits)+"回");
  set("expected-hits",data.research?.theoretical_uniform_expected_straight_hits==null?"—":data.research.theoretical_uniform_expected_straight_hits+"回");
  set("replay-at",japTime(data.research?.generated_at_jst));
  const source=data.source_audit||{};
  set("source-at",japTime(source.checked_at_jst));
  set("source-rows",integer(source.bank_rows)?source.bank_rows+"行 / "+source.rakuten_rows+"行":"取得待ち");
  set("source-errors",Array.isArray(source.errors)?source.errors.length+"件":"未確認");
  const warnings=el("warnings");warnings.replaceChildren();
  for(const warning of data.warnings)warnings.appendChild(mk("p",warning));
  if(!data.warnings.length)warnings.appendChild(mk("p","取得データに重大な不一致はありません。ただし予測力は未実証です。"));
}
async function refresh(){
  const btn=el("refresh");btn.disabled=true;el("error").hidden=true;
  try{
    const response=await fetch("./data/status.json?no-cache="+Date.now(),{cache:"no-store",headers:{Accept:"application/json"}});
    if(!response.ok)throw new Error("HTTP "+response.status);
    render(validate(await response.json()));
  }catch(exc){
    const error=el("error");error.hidden=false;
    error.textContent="公開データを読み込み・検証できません: "+String(exc.message||exc);
    set("source-badge","データ検証不可");el("source-badge").className="state-pill warn";
  }finally{btn.disabled=false}
}
el("refresh").addEventListener("click",refresh);
refresh();
setInterval(()=>{if(!document.hidden&&!el("refresh").disabled)refresh()},120000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh()});
