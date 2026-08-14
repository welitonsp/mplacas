// MPlacas · Observatório Solar: editorialismo tecnológico, evidência antes de promessa e assimetria intencional.
import { useState, type ReactNode } from "react";
import "./public-home.css";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Check,
  ChevronDown,
  CircleCheck,
  Clock3,
  CloudSun,
  FileCheck2,
  Gauge,
  Menu,
  ShieldCheck,
  Sparkles,
  SunMedium,
  Waves,
  X,
} from "lucide-react";

const heroImage = "https://images.unsplash.com/photo-1509391366360-2e959784a276?auto=format&fit=crop&w=2200&q=88";
const energyImage = "https://images.unsplash.com/photo-1509391366360-2e959784a276?auto=format&fit=crop&w=1800&q=85";
const climateImage = "https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=1800&q=85";
const logoImage = "/mplacas-mark.svg";

const navItems = [
  { label: "Como funciona", href: "#como-funciona" },
  { label: "Leituras", href: "#leituras" },
  { label: "Confiabilidade", href: "#confiabilidade" },
];

const capabilities = [
  {
    number: "01",
    eyebrow: "Telemetria consolidada",
    title: "Uma linha do tempo que não perde o contexto.",
    body: "Produção, consumo, importação e injeção convivem na mesma leitura — com histórico próprio, ciclos e origem de cada indicador.",
    icon: Activity,
    tone: "teal",
  },
  {
    number: "02",
    eyebrow: "Diagnóstico determinístico",
    title: "O sinal chega antes de virar custo.",
    body: "Anomalias, desvios e saúde da usina são interpretados por regras explícitas, com severidade e próxima ação visíveis.",
    icon: Gauge,
    tone: "amber",
  },
  {
    number: "03",
    eyebrow: "Relatório auditável",
    title: "A decisão continua explicável depois da reunião.",
    body: "Snapshots imutáveis e exportações em JSON, CSV, PDF e XLSX guardam valor, unidade, fonte, período e versão do cálculo.",
    icon: FileCheck2,
    tone: "navy",
  },
];

const evidence = [
  { value: "D+1", label: "consolidação diária", icon: Clock3 },
  { value: "4", label: "formatos de relatório", icon: FileCheck2 },
  { value: "100%", label: "rastreabilidade de métricas", icon: ShieldCheck },
];

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <a className={`brand ${compact ? "brand--compact" : ""}`} href="#top" aria-label="MPlacas, início">
      <img src={logoImage} alt="" className="brand__mark" />
      <span className="brand__name">M<span>Placas</span></span>
      {!compact && <span className="brand__rule" aria-hidden="true" />}
    </a>
  );
}

function SectionLabel({ children, dark = false }: { children: ReactNode; dark?: boolean }) {
  return (
    <div className={`section-label ${dark ? "section-label--dark" : ""}`}>
      <span className="section-label__dot" />
      <span>{children}</span>
    </div>
  );
}

function DashboardMockup() {
  return (
    <div className="dashboard-mockup" aria-label="Prévia ilustrativa do painel MPlacas">
      <div className="dashboard-mockup__topbar">
        <div className="dashboard-mockup__window-dots"><span /><span /><span /></div>
        <span className="dashboard-mockup__path">visão executiva / usina lagoa</span>
        <span className="dashboard-mockup__status"><i /> dados atualizados</span>
      </div>
      <div className="dashboard-mockup__body">
        <aside className="dashboard-mockup__side">
          <div className="dashboard-mockup__mini-logo"><img src={logoImage} alt="" /></div>
          <div className="dashboard-mockup__side-line dashboard-mockup__side-line--active" />
          <div className="dashboard-mockup__side-line" />
          <div className="dashboard-mockup__side-line" />
          <div className="dashboard-mockup__side-line" />
          <div className="dashboard-mockup__side-line dashboard-mockup__side-line--last" />
        </aside>
        <div className="dashboard-mockup__content">
          <div className="dashboard-mockup__heading">
            <div><span className="dashboard-mockup__kicker">LEITURA DE EXEMPLO · JUL 2026</span><strong>Saúde da usina</strong></div>
            <span className="dashboard-mockup__pill"><CircleCheck size={12} /> estável</span>
          </div>
          <div className="dashboard-mockup__metrics">
            <div><span>Produção no ciclo</span><strong>1.248 <small>kWh</small></strong><em>+8,4% vs. mediana</em></div>
            <div><span>Autossuficiência</span><strong>74,8<small>%</small></strong><em className="is-neutral">leitura consolidada</em></div>
            <div><span>Índice de saúde</span><strong>92<small>/100</small></strong><em>sem alerta crítico</em></div>
          </div>
          <div className="dashboard-mockup__chart-card">
            <div className="dashboard-mockup__chart-head"><span>Produção diária</span><span className="chart-legend"><i /> realizado <b /> esperado</span></div>
            <div className="dashboard-mockup__chart">
              <div className="chart-grid"><span /><span /><span /><span /></div>
              <svg viewBox="0 0 640 148" preserveAspectRatio="none" role="img" aria-label="Gráfico ilustrativo de produção diária">
                <path className="chart-area" d="M0 122 C24 118 34 92 58 98 S89 72 116 88 S146 45 176 70 S211 64 238 78 S271 22 300 51 S342 67 365 38 S401 44 424 57 S456 29 480 39 S512 78 538 55 S574 30 600 42 S624 31 640 18 L640 148 L0 148 Z" />
                <path className="chart-line chart-line--expected" d="M0 111 C28 108 45 98 72 92 S118 82 144 78 S189 71 220 67 S264 62 296 60 S346 58 376 55 S425 49 452 47 S502 43 531 38 S588 35 640 30" />
                <path className="chart-line" d="M0 122 C24 118 34 92 58 98 S89 72 116 88 S146 45 176 70 S211 64 238 78 S271 22 300 51 S342 67 365 38 S401 44 424 57 S456 29 480 39 S512 78 538 55 S574 30 600 42 S624 31 640 18" />
              </svg>
            </div>
            <div className="dashboard-mockup__chart-axis"><span>01 jul</span><span>08 jul</span><span>15 jul</span><span>22 jul</span><span>31 jul</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="site-shell" id="top">
      <header className="site-header">
        <div className="site-header__inner">
          <Brand />
          <nav className={`site-nav ${menuOpen ? "site-nav--open" : ""}`} aria-label="Navegação principal">
            {navItems.map((item) => <a key={item.href} href={item.href} onClick={closeMenu}>{item.label}</a>)}
            <a className="site-nav__mobile-cta" href="mailto:oi@mplacas.com.br?subject=Quero conhecer a MPlacas" onClick={closeMenu}>Falar com a equipe <ArrowUpRight size={15} /></a>
          </nav>
          <a className="header-cta" href="mailto:oi@mplacas.com.br?subject=Quero conhecer a MPlacas">Falar com a equipe <ArrowUpRight size={15} /></a>
          <button className="menu-toggle" type="button" aria-label={menuOpen ? "Fechar menu" : "Abrir menu"} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
            {menuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </header>

      <main>
        <section className="hero-section">
          <div className="hero-section__image" style={{ backgroundImage: `url(${heroImage})` }} />
          <div className="hero-section__shade" />
          <div className="hero-section__content site-container">
            <div className="hero-copy">
              <SectionLabel dark>Inteligência para energia residencial</SectionLabel>
              <h1>Energia medida.<br /><em>Decisão explicada.</em></h1>
              <p className="hero-copy__lead">MPlacas transforma telemetria, clima e faturas em uma leitura única da sua usina — para você saber o que mudou, por que importa e qual é o próximo passo.</p>
              <div className="hero-actions">
                <a className="button button--primary" href="mailto:oi@mplacas.com.br?subject=Quero conhecer a MPlacas">Conhecer a plataforma <ArrowRight size={17} /></a>
                <a className="text-link text-link--light" href="#como-funciona">Ver como funciona <ChevronDown size={16} /></a>
              </div>
              <div className="hero-note"><span className="hero-note__line" /><span>Leitura auditável, não achismo</span></div>
            </div>
            <div className="hero-meta">
              <span>01 / 04</span>
              <span className="hero-meta__line" />
              <span>observatório solar</span>
            </div>
          </div>
          <div className="hero-bottom-marker"><span>role para explorar</span><ChevronDown size={16} /></div>
        </section>

        <section className="evidence-strip" aria-label="Indicadores de produto">
          <div className="site-container evidence-strip__inner">
            <div className="evidence-intro"><span className="evidence-intro__index">MPL / 01</span><span>Uma camada de<br /><strong>clareza operacional.</strong></span></div>
            {evidence.map(({ value, label, icon: Icon }) => <div className="evidence-item" key={label}><Icon size={17} /><strong>{value}</strong><span>{label}</span></div>)}
            <div className="evidence-mark"><Waves size={30} strokeWidth={1.2} /><span>energia<br />em contexto</span></div>
          </div>
        </section>

        <section className="intro-section site-container" id="como-funciona">
          <div className="intro-section__aside"><SectionLabel>O problema certo</SectionLabel><span className="vertical-note">01 — ORIENTAR</span></div>
          <div className="intro-section__copy">
            <h2>Não basta saber quanto a usina produziu. <em>É preciso entender o sistema.</em></h2>
            <p>Uma boa decisão energética nasce do encontro entre o dado técnico e o contexto da casa. A MPlacas cria essa ponte com histórico próprio, conciliação por ciclo de leitura e diagnósticos que deixam a próxima ação visível.</p>
            <a className="text-link" href="#leituras">Acompanhar a leitura <ArrowUpRight size={16} /></a>
          </div>
          <div className="intro-section__stamp"><Sparkles size={18} /><span>clareza<br />é um recurso</span></div>
        </section>

        <section className="capabilities-section" id="leituras">
          <div className="site-container">
            <div className="section-heading section-heading--split">
              <div><SectionLabel>Uma plataforma, três camadas</SectionLabel><h2>Da captura ao próximo passo.</h2></div>
              <p>O produto organiza a jornada completa sem esconder as partes difíceis: fonte, qualidade do dado, diagnóstico e rastreabilidade continuam juntos.</p>
            </div>
            <div className="capability-list">
              {capabilities.map(({ number, eyebrow, title, body, icon: Icon, tone }) => <article className={`capability-card capability-card--${tone}`} key={number}>
                <div className="capability-card__top"><span>{number}</span><Icon size={20} strokeWidth={1.5} /></div>
                <div className="capability-card__content"><span className="eyebrow">{eyebrow}</span><h3>{title}</h3><p>{body}</p><a href="#confiabilidade" aria-label={`Saiba mais sobre ${eyebrow}`}><ArrowUpRight size={17} /></a></div>
              </article>)}
            </div>
          </div>
        </section>

        <section className="product-section site-container">
          <div className="product-section__copy"><SectionLabel>Uma visão antes da planilha</SectionLabel><h2>O painel que transforma sinal em <em>conversa.</em></h2><p>Uma superfície executiva para a reunião de hoje e um registro auditável para a decisão de amanhã. Cada métrica chega com unidade, fonte, período e qualidade do dado.</p><div className="product-checks"><span><Check size={15} /> produção e consumo no mesmo ciclo</span><span><Check size={15} /> saúde da usina com severidade explícita</span><span><Check size={15} /> tendência sem recalcular o passado</span></div><a className="text-link" href="mailto:oi@mplacas.com.br?subject=Quero ver uma leitura MPlacas">Quero ver uma leitura <ArrowRight size={16} /></a></div>
          <div className="product-section__visual"><div className="visual-annotation visual-annotation--top"><span>leitura executiva</span><span className="visual-annotation__rule" /></div><DashboardMockup /><div className="visual-annotation visual-annotation--bottom"><span className="visual-annotation__rule" /><span>exemplo ilustrativo</span></div></div>
        </section>

        <section className="split-story split-story--energy">
          <div className="split-story__image" style={{ backgroundImage: `url(${energyImage})` }}><span className="image-caption">02 — MOSTRAR / luz depois da chuva</span></div>
          <div className="split-story__content"><SectionLabel>Produção com contexto</SectionLabel><h2>O número que você vê é só o começo da história.</h2><p>Quando a série histórica se encontra com o clima e a fatura, o desvio deixa de ser um susto e vira uma pergunta boa: o que mudou no ambiente, no equipamento ou no ciclo?</p><div className="story-stat"><strong>+8,4%</strong><span>variação de exemplo<br />contra a mediana de 30 dias</span></div><a className="text-link" href="#confiabilidade">Entender a evidência <ArrowUpRight size={16} /></a></div>
        </section>

        <section className="split-story split-story--climate">
          <div className="split-story__content"><SectionLabel>Explicação assistida</SectionLabel><h2>Clima, telemetria e fatura na mesma conversa.</h2><p>A MPlacas combina motores determinísticos com explicações assistidas por IA ancoradas em evidências normalizadas. A IA ajuda a explicar; os indicadores continuam sendo calculados por regras explícitas.</p><div className="quote-card"><CloudSun size={21} /><p>“A produção ficou abaixo do esperado no início do ciclo, mas recuperou após a janela de nebulosidade.”</p><span>exemplo de explicação com grounding</span></div></div>
          <div className="split-story__image" style={{ backgroundImage: `url(${climateImage})` }}><span className="image-caption">03 — INTERPRETAR / clima em perspectiva</span></div>
        </section>

        <section className="trust-section" id="confiabilidade">
          <div className="site-container trust-section__inner">
            <div className="trust-section__header"><SectionLabel dark>Confiabilidade por projeto</SectionLabel><h2>Quando o dado é importante, a origem também importa.</h2><p>A plataforma mantém explícito o que está confirmado, provisório ou indisponível — e não deixa uma narrativa bonita encobrir uma lacuna.</p></div>
            <div className="trust-grid">
              <div className="trust-grid__item"><span className="trust-grid__number">01</span><ShieldCheck size={22} /><h3>Snapshots imutáveis</h3><p>O relatório confirmado preserva o resultado que foi usado na decisão.</p></div>
              <div className="trust-grid__item"><span className="trust-grid__number">02</span><BarChart3 size={22} /><h3>Fonte em cada métrica</h3><p>Valor, unidade, natureza, período e versão permanecem rastreáveis.</p></div>
              <div className="trust-grid__item"><span className="trust-grid__number">03</span><SunMedium size={22} /><h3>Dados ausentes visíveis</h3><p>Sem preencher lacunas com suposições ou esconder a qualidade da leitura.</p></div>
            </div>
            <div className="trust-section__footer"><span className="trust-section__footer-line" /><span>04 — AGIR</span><strong>Da próxima pergunta à próxima ação.</strong><a className="button button--outline-light" href="mailto:oi@mplacas.com.br?subject=Quero conversar sobre a MPlacas">Conversar com a MPlacas <ArrowUpRight size={16} /></a></div>
          </div>
        </section>
      </main>

      <footer className="site-footer"><div className="site-container site-footer__inner"><div><Brand compact /><p>Inteligência energética<br />com contexto e rastreabilidade.</p></div><div className="site-footer__links"><span>mplacas / observatório solar</span><a href="mailto:oi@mplacas.com.br">oi@mplacas.com.br <ArrowUpRight size={14} /></a></div><div className="site-footer__bottom"><span>© 2026 MPlacas</span><span>Energia medida. Decisão explicada.</span><a href="#top">Voltar ao topo <ArrowUpRight size={14} /></a></div></div></footer>
    </div>
  );
}
