/* ── Credential store (localStorage) ─────────────────── */
const CREDS_KEY = 'mplacas_creds_v1';

function credsSave(plantId, apiKey) {
  try { localStorage.setItem(CREDS_KEY, JSON.stringify({plantId, apiKey})); } catch(_) {}
}
function credsLoad() {
  try { return JSON.parse(localStorage.getItem(CREDS_KEY)); } catch(_) { return null; }
}
function credsClear() {
  try { localStorage.removeItem(CREDS_KEY); } catch(_) {}
}

/* ── State ───────────────────────────────────────────── */
const state = {plantId: '', apiKey: ''};

/* ── DOM helpers ─────────────────────────────────────── */
const $ = (id) => document.getElementById(id);
const fmt = (v, d=1) => new Intl.NumberFormat('pt-BR', {minimumFractionDigits:d, maximumFractionDigits:d}).format(Number(v));
const money = (v) => new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}).format(Number(v));

function show(id, visible) { $(id).classList.toggle('hidden', !visible); }
function setText(id, value) { $(id).textContent = value; }
function trendLabel(d) { return d==='UP'?'Alta':d==='DOWN'?'Queda':'Estável'; }

/* ── Render ──────────────────────────────────────────── */
function renderMetric(container, label, metric, unit) {
  const item = document.createElement('div');
  item.className = `trend-item trend-${metric.direction}`;
  const title = document.createElement('strong'); title.textContent = label;
  const direction = document.createElement('span'); direction.textContent = trendLabel(metric.direction);
  const detail = document.createElement('small');
  const pct = metric.percent_delta === null ? 'base anterior igual a zero' : `${fmt(metric.percent_delta)}%`;
  detail.textContent = `Variação: ${fmt(metric.absolute_delta, 3)} ${unit} · ${pct}`;
  item.append(title, direction, detail);
  container.append(item);
}

function render(data) {
  const indicators = data.current_cycle.indicators;
  const quality = data.current_cycle.quality;
  const STATUS_LABEL = {HEALTHY:'Saudável', ATTENTION:'Atenção', CRITICAL:'Crítico'};

  setText('reference', `Ciclo ${data.current_cycle.reference_month}`);
  setText('headline', data.headline);

  const pill = $('status');
  pill.className = `status-pill status-${data.status}`;
  pill.textContent = STATUS_LABEL[data.status] || data.status;

  setText('production',       fmt(indicators.cycle_production_kwh));
  setText('consumption',      fmt(indicators.estimated_total_consumption_kwh));
  setText('self-sufficiency', `${fmt(indicators.self_sufficiency_rate_percent)}%`);
  setText('health',           `${indicators.health_score}/100`);
  setText('imported',         `${fmt(indicators.imported_kwh)} kWh`);
  setText('injected',         `${fmt(indicators.injected_kwh)} kWh`);
  setText('self-consumption', `${fmt(indicators.estimated_self_consumption_kwh)} kWh`);
  setText('grid-dependency',  `${fmt(indicators.grid_dependency_rate_percent)}%`);
  setText('credit-coverage',  `${fmt(indicators.credit_coverage_rate_percent)}%`);
  setText('bill-energy',      money(indicators.bill_energy_component_brl));
  setText('missing-days',     quality.missing_days);
  setText('provisional-days', quality.provisional_days);
  setText('incomplete-days',  quality.incomplete_days);
  setText('unavailable-days', quality.unavailable_days);

  const actions = $('actions');
  actions.replaceChildren();
  const items = data.priority_actions.length
    ? data.priority_actions
    : ['Nenhuma ação prioritária identificada.'];
  for (const a of items) {
    const li = document.createElement('li'); li.textContent = a; actions.append(li);
  }

  const trends = $('trends');
  trends.replaceChildren();
  if (data.trend) {
    show('trend-empty', false); show('trends', true);
    const m = data.trend.metrics;
    renderMetric(trends, 'Produção',        m.production,       'kWh');
    renderMetric(trends, 'Consumo',         m.total_consumption,'kWh');
    renderMetric(trends, 'Energia importada',m.imported_energy, 'kWh');
  } else {
    show('trend-empty', true); show('trends', false);
  }

  show('dashboard', true);
}

/* ── Data fetch ──────────────────────────────────────── */
async function loadDashboard() {
  if (!state.plantId || !state.apiKey) return;
  show('loading', true); show('error', false); show('dashboard', false);
  try {
    const res = await fetch(
      `/energy/executive/latest?plant_id=${encodeURIComponent(state.plantId)}`,
      {headers: {'X-API-Key': state.apiKey}}
    );
    if (!res.ok) {
      const msg =
        res.status === 401 ? 'Chave operacional inválida.' :
        res.status === 404 ? 'Não há ciclo confirmado disponível para esta usina.' :
                             'Não foi possível carregar o painel.';
      throw new Error(msg);
    }
    render(await res.json());
  } catch(err) {
    setText('error', err.message || 'Falha inesperada ao carregar o painel.');
    show('error', true);
  } finally {
    show('loading', false);
  }
}

/* ── Connected / disconnected states ─────────────────── */
function enterConnected(plantId, apiKey) {
  state.plantId = plantId;
  state.apiKey  = apiKey;
  credsSave(plantId, apiKey);
  show('setup',      false);
  show('disconnect', true);
  show('refresh',    true);
  loadDashboard();
}

function enterDisconnected() {
  credsClear();
  state.plantId = ''; state.apiKey = '';
  $('plant-id').value = ''; $('api-key').value = '';
  show('setup',      true);
  show('disconnect', false);
  show('refresh',    false);
  show('dashboard',  false);
  show('loading',    false);
  show('error',      false);
}

/* ── Events ──────────────────────────────────────────── */
$('setup-form').addEventListener('submit', (e) => {
  e.preventDefault();
  enterConnected($('plant-id').value.trim(), $('api-key').value);
});

$('refresh').addEventListener('click', loadDashboard);

$('disconnect').addEventListener('click', () => {
  if (confirm('Remover credenciais salvas e voltar à tela de login?')) {
    enterDisconnected();
  }
});

/* ── Auto-load on startup if credentials are saved ───── */
const saved = credsLoad();
if (saved && saved.plantId && saved.apiKey) {
  $('plant-id').value = saved.plantId;
  $('api-key').value  = saved.apiKey;
  enterConnected(saved.plantId, saved.apiKey);
}
