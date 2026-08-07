export function SectionTitle({
  children,
  as: Heading = 'h3',
  id,
}: {
  children: string
  // Nível de heading condizente com o outline da página que compõe esta
  // seção — o padrão (`h3`) preserva o comportamento anterior para quem não
  // passa a prop; `DashboardPage` promove suas seções principais para `h2`.
  as?: 'h2' | 'h3'
  id?: string
}) {
  return (
    <Heading id={id} className="mb-4 text-base font-bold text-gray-800 tracking-tight">
      {children}
    </Heading>
  )
}
