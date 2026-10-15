// MPlacas · Observatório Solar: editorialismo tecnológico, evidência antes de promessa e assimetria intencional.
import { useEffect, useRef, useState, type ReactNode } from "react";
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

// Fotografias auto-hospedadas em `public/images/` e dimensionadas em WebP.
// Os fundos ficam no stylesheet local para respeitar `style-src 'self'` da CSP.
const logoImage = "/mplacas-mark.svg";
const contactBody = [
  "Olá, equipe MPlacas! Quero entender se a plataforma faz sentido para minha usina.",
  "",
  "Portal ou inversor: ",
  "Cidade/UF: ",
  "O que quero entender: ",
].join("\n");
const contactHref = `mailto:oi@mplacas.com.br?subject=${encodeURIComponent("Quero avaliar minha usina solar")}&body=${encodeURIComponent(contactBody)}`;

const navItems = [
  { label: "Como funciona", href: "#como-funciona" },
  { label: "O que você acompanha", href: "#leituras" },
  { label: "Confiabilidade", href: "#confiabilidade" },
  { label: "Dúvidas", href: "#duvidas" },
];

const capabilities = [
  {
    number: "01",
    eyebrow: "Telemetria consolidada",
    title: "Uma linha do tempo que não perde o contexto.",
    body: "Produção, consumo, importação e injeção convivem na mesma leitura — com histórico próprio, ciclos e origem de cada indicador.",
    icon: Activity,
    tone: "teal",
    href: "#como-funciona",
  },
  {
    number: "02",
    eyebrow: "Diagnóstico determinístico",
    title: "O sinal chega antes de virar custo.",
    body: "Anomalias, desvios e saúde da usina são interpretados por regras explícitas, com severidade e próxima ação visíveis.",
    icon: Gauge,
    tone: "amber",
    href: "#confiabilidade",
  },
  {
    number: "03",
    eyebrow: "Relatório auditável",
    title: "A decisão continua explicável depois da reunião.",
    body: "Snapshots imutáveis e exportações em JSON, CSV, PDF e XLSX guardam valor, unidade, fonte, período e versão do cálculo.",
    icon: FileCheck2,
    tone: "navy",
    href: "#duvidas",
  },
];

const evidence = [
  { value: "D+1", label: "consolidação diária", icon: Clock3 },
  { value: "4", label: "formatos de relatório", icon: FileCheck2 },
  { value: "Rastreável", label: "fonte, unidade e período por métrica", icon: ShieldCheck },
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
    // `role="img"` junto do `aria-label` (auditoria v6, A-11): `aria-label`
    // sozinho num `div` genérico é ignorado por parte dos leitores de tela,
    // porque a role implícita de `div` não aceita nome acessível. A composição
    // inteira é uma ilustração — números, rótulos e gráfico são fictícios —,
    // então expor um nome único e não a árvore interna é o que descreve a
    // realidade. Mesmo padrão que o `<svg role="img">` mais abaixo neste
    // arquivo já usava corretamente.
    <div className="dashboard-mockup" role="img" aria-label="Prévia ilustrativa do painel MPlacas">
      <div className="dashboard-mockup__topbar">
        <div className="dashboard-mockup__window-dots"><span /><span /><span /></div>
        <span className="dashboard-mockup__path">visão executiva / usina exemplo</span>
        <span className="dashboard-mockup__status"><i /> dados ilustrativos</span>
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
            <div><span className="dashboard-mockup__kicker">DEMONSTRAÇÃO · JUL 2026</span><strong>Saúde da usina</strong></div>
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
  const menuToggleRef = useRef<HTMLButtonElement>(null);
  const siteNavigationRef = useRef<HTMLElement>(null);

  const closeMenu = () => setMenuOpen(false);

  useEffect(() => {
    if (!menuOpen) return;

    siteNavigationRef.current?.querySelector<HTMLAnchorElement>("a")?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuToggleRef.current?.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [menuOpen]);

  return (
    <div className="site-shell" id="top">
      <a className="skip-link" href="#main-content">Pular para o conteúdo</a>
      <header className="site-header">
        <div className="site-header__inner">
          <Brand />
          <button ref={menuToggleRef} className="menu-toggle" type="button" aria-label={menuOpen ? "Fechar menu" : "Abrir menu"} aria-expanded={menuOpen} aria-controls="site-navigation" onClick={() => setMenuOpen((open) => !open)}>
            {menuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
          <nav ref={siteNavigationRef} id="site-navigation" className={`site-nav ${menuOpen ? "site-nav--open" : ""}`} aria-label="Navegação principal">
            {navItems.map((item) => <a key={item.href} href={item.href} onClick={closeMenu}>{item.label}</a>)}
            <a className="site-nav__mobile-cta" href={contactHref} onClick={closeMenu}>Avaliar minha usina <ArrowUpRight size={15} /></a>
          </nav>
          <a className="header-cta" href={contactHref}>Avaliar minha usina <ArrowUpRight size={15} /></a>
        </div>
      </header>

      <main id="main-content" tabIndex={-1}>
        <section className="hero-section">
          <div className="hero-section__image" />
          <div className="hero-section__shade" />
          <div className="hero-section__content site-container">
            <div className="hero-copy">
              <SectionLabel dark>Mais clareza para quem gera energia solar</SectionLabel>
              <h1>O que sua usina gera<br /><em>aparece na conta?</em></h1>
              <p className="hero-copy__lead">A MPlacas reúne dados do NEPViewer, clima e fatura Equatorial para mostrar produção, consumo e créditos no contexto do ciclo — com a origem e a qualidade de cada leitura à vista.</p>
              <div className="hero-actions">
                <a className="button button--primary" href={contactHref}>Quero avaliar minha usina <ArrowRight size={17} /></a>
                <a className="text-link text-link--light" href="#como-funciona">Entender em 1 minuto <ChevronDown size={16} /></a>
              </div>
              <div className="hero-note"><span className="hero-note__line" /><span>Indicadores calculados por regras explícitas</span></div>
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
          <div className="intro-section__aside"><SectionLabel>A pergunta por trás da conta</SectionLabel><span className="vertical-note">01 — ORIENTAR</span></div>
          <div className="intro-section__copy">
            <h2>Produção, consumo e fatura contam partes da mesma história. <em>A MPlacas ajuda a juntá-las.</em></h2>
            <p>Em vez de olhar cada número isoladamente, veja os dados organizados por ciclo: o que foi produzido, consumido, importado ou injetado — e o que merece uma investigação mais cuidadosa.</p>
            <a className="text-link" href="#leituras">Ver o que você acompanha <ArrowUpRight size={16} /></a>
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
              {capabilities.map(({ number, eyebrow, title, body, icon: Icon, tone, href }) => <article className={`capability-card capability-card--${tone}`} key={number}>
                <div className="capability-card__top"><span>{number}</span><Icon size={20} strokeWidth={1.5} /></div>
                <div className="capability-card__content"><span className="eyebrow">{eyebrow}</span><h3>{title}</h3><p>{body}</p><a href={href} aria-label={`Saiba mais sobre ${eyebrow}`}><ArrowUpRight size={17} /></a></div>
              </article>)}
            </div>
          </div>
        </section>

        <section className="product-section site-container">
          <div className="product-section__copy"><SectionLabel>Da pergunta à evidência</SectionLabel><h2>Veja sua usina além do <em>portal do inversor.</em></h2><p>Uma leitura executiva reúne produção, consumo, saúde da usina e fatura. Em cada métrica, ficam visíveis a unidade, a fonte, o período e a qualidade do dado.</p><div className="product-checks"><span><Check size={15} /> produção e consumo no mesmo ciclo</span><span><Check size={15} /> alertas com severidade e próxima ação</span><span><Check size={15} /> histórico e relatórios exportáveis</span></div><a className="text-link" href={contactHref}>Quero entender minha usina <ArrowRight size={16} /></a></div>
          <div className="product-section__visual"><div className="visual-annotation visual-annotation--top"><span>leitura executiva</span><span className="visual-annotation__rule" /></div><DashboardMockup /><div className="visual-annotation visual-annotation--bottom"><span className="visual-annotation__rule" /><span>exemplo ilustrativo</span></div></div>
        </section>

        <section className="split-story split-story--energy">
          <div className="split-story__image split-story__image--energy"><span className="image-caption">02 — MOSTRAR / luz depois da chuva</span></div>
          <div className="split-story__content"><SectionLabel>Produção com contexto</SectionLabel><h2>O número que você vê é só o começo da história.</h2><p>Quando a série histórica se encontra com o clima e a fatura, o desvio deixa de ser um susto e vira uma pergunta boa: o que mudou no ambiente, no equipamento ou no ciclo?</p><div className="story-stat"><strong>+8,4%</strong><span>variação de exemplo<br />contra a mediana de 30 dias</span></div><a className="text-link" href="#confiabilidade">Entender a evidência <ArrowUpRight size={16} /></a></div>
        </section>

        <section className="split-story split-story--climate">
          <div className="split-story__content"><SectionLabel>Explicação assistida</SectionLabel><h2>Clima, telemetria e fatura na mesma conversa.</h2><p>A MPlacas combina motores determinísticos com explicações assistidas por IA ancoradas em evidências normalizadas. A IA ajuda a explicar; os indicadores continuam sendo calculados por regras explícitas.</p><div className="quote-card"><CloudSun size={21} /><p>“A produção ficou abaixo do esperado no início do ciclo, mas recuperou após a janela de nebulosidade.”</p><span>exemplo de explicação com grounding</span></div></div>
          <div className="split-story__image split-story__image--climate"><span className="image-caption">03 — INTERPRETAR / clima em perspectiva</span></div>
        </section>

        <section className="faq-section" id="duvidas">
          <div className="site-container faq-section__inner">
            <div className="faq-section__intro">
              <SectionLabel>Perguntas importantes</SectionLabel>
              <h2>Clareza também é saber <em>o que esperar.</em></h2>
              <p>Sem prometer leitura perfeita quando os dados não permitem. Veja como a MPlacas lida com integração, indicadores e lacunas.</p>
            </div>
            <div className="faq-list">
              <details className="faq-item">
                <summary>Quais dados a MPlacas considera?</summary>
                <p>A plataforma reúne telemetria do NEPViewer, dados climáticos e informações das faturas Equatorial para montar leituras por ciclo. A disponibilidade depende dos dados e da configuração de cada usina.</p>
              </details>
              <details className="faq-item">
                <summary>Os indicadores de energia são calculados por IA?</summary>
                <p>Não. Os indicadores são calculados por regras determinísticas. A IA pode ajudar a explicar resultados a partir de evidências organizadas, mas não inventa medições nem decide a severidade dos diagnósticos.</p>
              </details>
              <details className="faq-item">
                <summary>O que acontece quando faltam dados?</summary>
                <p>A lacuna permanece visível como dado parcial, provisório ou indisponível. A MPlacas não preenche o que falta com suposições para fazer o painel parecer completo.</p>
              </details>
            </div>
            <div className="faq-cta">
              <div>
                <span>O próximo passo</span>
                <strong>Conte o que você quer entender sobre a sua usina.</strong>
                <small>O e-mail abre com algumas informações úteis para começar a conversa.</small>
              </div>
              <a className="button button--primary" href={contactHref}>
                Avaliar minha usina <ArrowRight size={17} />
              </a>
            </div>
          </div>
        </section>

        <section className="trust-section" id="confiabilidade">
          <div className="site-container trust-section__inner">
            <div className="trust-section__header"><SectionLabel dark>Confiabilidade por projeto</SectionLabel><h2>Quando o dado é importante, a origem também importa.</h2><p>A plataforma mantém explícito o que está confirmado, provisório ou indisponível — e não deixa uma narrativa bonita encobrir uma lacuna.</p></div>
            <div className="trust-grid">
              <div className="trust-grid__item"><span className="trust-grid__number">01</span><ShieldCheck size={22} /><h3>Snapshots imutáveis</h3><p>O relatório confirmado preserva o resultado que foi usado na decisão.</p></div>
              <div className="trust-grid__item"><span className="trust-grid__number">02</span><BarChart3 size={22} /><h3>Fonte em cada métrica</h3><p>Valor, unidade, natureza, período e versão permanecem rastreáveis.</p></div>
              <div className="trust-grid__item"><span className="trust-grid__number">03</span><SunMedium size={22} /><h3>Dados ausentes visíveis</h3><p>Sem preencher lacunas com suposições ou esconder a qualidade da leitura.</p></div>
            </div>
            <div className="trust-section__footer"><span className="trust-section__footer-line" /><span>04 — AGIR</span><strong>Da próxima pergunta à próxima ação.</strong><a className="button button--outline-light" href={contactHref}>Avaliar minha usina <ArrowUpRight size={16} /></a></div>
          </div>
        </section>
      </main>

      <footer className="site-footer"><div className="site-container site-footer__inner"><div><Brand compact /><p>Inteligência energética<br />com contexto e rastreabilidade.</p></div><div className="site-footer__links"><span>mplacas / observatório solar</span><a href="mailto:oi@mplacas.com.br">oi@mplacas.com.br <ArrowUpRight size={14} /></a></div><div className="site-footer__bottom"><span>© 2026 MPlacas</span><span>Energia medida. Decisão explicada.</span><a href="#top">Voltar ao topo <ArrowUpRight size={14} /></a></div></div></footer>
    </div>
  );
}
