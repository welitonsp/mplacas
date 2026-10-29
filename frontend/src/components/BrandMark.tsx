// Marca MPlacas (ADR-077): o MESMO símbolo da landing e do favicon
// (`public/mplacas-mark.svg`) + o nome em Space Grotesk. Antes o produto usava
// um "A" num quadrado vazado, diferente da landing, e o header repetia o nome
// duas vezes (texto dentro do SVG + `<span>` ao lado).
//
// O símbolo tem fundo próprio (quadrado escuro), então funciona igual nos dois
// temas; só o nome segue `currentColor`.
export function BrandMark({
  className = '',
  showWordmark = true,
}: {
  className?: string
  showWordmark?: boolean
}) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`.trim()}>
      <svg
        viewBox="0 0 128 128"
        aria-hidden="true"
        className="h-8 w-8 shrink-0"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect width="128" height="128" rx="28" fill="#102126" />
        <path
          d="M26 79.5L42.5 42L61 79.5L76.5 46L102 79.5"
          stroke="#4BB9A9"
          strokeWidth="9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M30 94H98" stroke="#E6AE58" strokeWidth="7" strokeLinecap="round" />
        <path d="M38 35H83" stroke="#EEF4EA" strokeWidth="7" strokeLinecap="round" opacity=".92" />
      </svg>
      {showWordmark ? (
        <span className="font-display text-lg font-bold leading-none tracking-[-0.01em]">MPlacas</span>
      ) : (
        <span className="sr-only">MPlacas</span>
      )}
    </span>
  )
}
