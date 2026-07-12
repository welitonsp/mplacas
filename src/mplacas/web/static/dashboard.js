const state={plantId:"",apiKey:""};
const $=(id)=>document.getElementById(id);
const fmt=(value,digits=1)=>new Intl.NumberFormat("pt-BR",{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(Number(value));
const money=(value)=>new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(Number(value));

function show(id,visible){$(id).classList.toggle("hidden",!visible)}
function setText(id,value){$(id).textContent=value}
function trendLabel(direction){return direction==="UP"?"Alta":direction==="DOWN"?"Queda":"Estável"}

function renderMetric(container,label,metric,unit){
  const item=document.createElement("div");
  item.className=`trend-item trend-${metric.direction}`;
  const title=document.createElement("strong");title.textContent=label;
  const direction=document.createElement("span");direction.textContent=trendLabel(metric.direction);
  const detail=document.createElement("small");
  const percent=metric.percent_delta===null?"base anterior igual a zero":`${fmt(metric.percent_delta)}%`;
  detail.textContent=`Variação: ${fmt(metric.absolute_delta,3)} ${unit} · ${percent}`;
  item.append(title,direction,detail);container.append(item);
}

function render(data){
  const current=data.current_cycle;
  const indicators=current.indicators;
  const quality=current.quality;
  setText("reference",`Ciclo ${current.reference_month}`);
  setText("headline",data.headline);
  const status=$("status");status.className=`status-pill status-${data.status}`;status.textContent=data.status;
  setText("production",fmt(indicators.cycle_production_kwh));
  setText("consumption",fmt(indicators.estimated_total_consumption_kwh));
  setText("self-sufficiency",`${fmt(indicators.self_sufficiency_rate_percent)}%`);
  setText("health",`${indicators.health_score}/100`);
  setText("imported",`${fmt(indicators.imported_kwh)} kWh`);
  setText("injected",`${fmt(indicators.injected_kwh)} kWh`);
  setText("self-consumption",`${fmt(indicators.estimated_self_consumption_kwh)} kWh`);
  setText("grid-dependency",`${fmt(indicators.grid_dependency_rate_percent)}%`);
  setText("credit-coverage",`${fmt(indicators.credit_coverage_rate_percent)}%`);
  setText("bill-energy",money(indicators.bill_energy_component_brl));
  setText("missing-days",quality.missing_days);
  setText("provisional-days",quality.provisional_days);
  setText("incomplete-days",quality.incomplete_days);
  setText("unavailable-days",quality.unavailable_days);

  const actions=$("actions");actions.replaceChildren();
  for(const action of data.priority_actions){const li=document.createElement("li");li.textContent=action;actions.append(li)}
  if(!data.priority_actions.length){const li=document.createElement("li");li.textContent="Nenhuma ação prioritária identificada.";actions.append(li)}

  const trends=$("trends");trends.replaceChildren();
  if(data.trend){
    show("trend-empty",false);show("trends",true);
    const metrics=data.trend.metrics;
    renderMetric(trends,"Produção",metrics.production,"kWh");
    renderMetric(trends,"Consumo",metrics.total_consumption,"kWh");
    renderMetric(trends,"Energia importada",metrics.imported_energy,"kWh");
  }else{show("trend-empty",true);show("trends",false)}
  show("dashboard",true);
}

async function loadDashboard(){
  if(!state.plantId||!state.apiKey)return;
  show("loading",true);show("error",false);show("dashboard",false);
  try{
    const response=await fetch(`/energy/executive/latest?plant_id=${encodeURIComponent(state.plantId)}`,{headers:{"X-API-Key":state.apiKey}});
    if(!response.ok){throw new Error(response.status===401?"Chave operacional inválida.":response.status===404?"Não há ciclo confirmado disponível para esta usina.":"Não foi possível carregar o painel.")}
    render(await response.json());
  }catch(error){setText("error",error.message||"Falha inesperada ao carregar o painel.");show("error",true)}
  finally{show("loading",false)}
}

$("setup-form").addEventListener("submit",(event)=>{event.preventDefault();state.plantId=$("plant-id").value.trim();state.apiKey=$("api-key").value;loadDashboard()});
$("refresh").addEventListener("click",loadDashboard);
