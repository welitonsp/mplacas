// Marca "Mplacas" em SVG inline — sem asset externo, sem webfont. A cor segue
// `currentColor`, então o componente herda a cor de texto do elemento pai
// (permite usá-lo tanto sobre fundo escuro quanto claro sem prop de cor).
// Reutilizável: usado no login (Frente L) e, futuramente, no header do app.
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 220 40"
      role="img"
      aria-label="Mplacas"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="1" y="8" width="24" height="24" rx="5" stroke="currentColor" strokeWidth="2.5" />
      <path d="M7 26 L13 12 L19 26" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <text
        x="34"
        y="28"
        fontFamily="system-ui, -apple-system, Segoe UI, sans-serif"
        fontSize="22"
        fontWeight="600"
        fill="currentColor"
      >
        Mplacas
      </text>
    </svg>
  )
}
