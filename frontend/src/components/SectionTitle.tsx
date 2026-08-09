// `h2` (título de seção principal dentro de um módulo, ex. "Fluxo de
// energia") e `h3` (sub-seção dentro de uma seção já titulada) tinham a
// mesma classe CSS até aqui — resultado: hierarquia tipográfica achatada,
// um dos achados do diagnóstico de UX que motivou este ajuste. Agora cada
// nível tem peso visual próprio:
// - `h2`: mais peso/tamanho (`text-lg font-semibold`), para se destacar do
//   corpo dos cards que ele agrupa.
// - `h3`: tratamento de "olho de sobrancelha" (`text-xs font-medium
//   uppercase tracking-wide text-gray-500`) — reaproveita exatamente a
//   classe já usada em ~39 outros lugares do projeto para rótulo secundário
//   (ver `CurrencyCard`, `MetricCard`, `Gauge`, etc.), não uma classe nova.
const HEADING_CLASS: Record<'h2' | 'h3', string> = {
  h2: 'relative mb-4 flex items-center gap-2 text-lg font-semibold text-gray-900 tracking-tight before:h-5 before:w-1 before:rounded-full before:bg-[var(--color-brand-primary)]',
  h3: 'text-xs font-medium text-gray-500 uppercase tracking-wide',
}

export function SectionTitle({
  children,
  as: Heading = 'h3',
  id,
}: {
  children: string
  // Nível de heading condizente com o outline da página que compõe esta
  // seção — o padrão (`h3`) preserva o comportamento anterior para quem não
  // passa a prop; os módulos do dashboard promovem suas seções principais
  // para `h2` (nenhum uso atual do componente depende do `h3` default —
  // confirmado via grep antes desta mudança).
  as?: 'h2' | 'h3'
  id?: string
}) {
  return (
    <Heading id={id} className={HEADING_CLASS[Heading]}>
      {children}
    </Heading>
  )
}
