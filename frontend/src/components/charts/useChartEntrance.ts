import { useEffect, useRef, useState } from 'react'

// Pequeno atraso após a montagem antes de aplicar o valor final — dá tempo
// ao navegador de pintar o estado inicial "vazio" (largura/altura/traço 0)
// antes da mudança para o valor real, para a transição CSS já existente em
// cada primitiva (`transition-[width]`/`transition-[height]`/
// `transition-[stroke-dashoffset]`) ter um "antes" e um "depois" visíveis
// para animar entre eles. `requestAnimationFrame` não existe em jsdom (ver
// `useChartEntrance.test.ts`), e um `setTimeout` curto é a alternativa
// explicitamente aceita pela instrução desta etapa ("um
// requestAnimationFrame/pequeno timeout").
const ENTRANCE_TICK_MS = 16

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Coordena a animação única de entrada ("crescer do zero ao valor
 * final"/"desenhar o traço") de uma primitiva de `charts/`.
 *
 * Contrato:
 * - Retorna `false` no primeiro render de uma montagem nova (o chamador
 *   deve desenhar o estado "vazio": largura/altura/traço 0) e passa a
 *   `true` ~16ms depois (o chamador troca para o valor real; a transição
 *   CSS já existente em cada primitiva faz o resto).
 * - Dispara **uma única vez por montagem do componente**, nunca de novo —
 *   `hasAnimatedRef` garante que nem uma reexecução do efeito (ex.:
 *   double-invoke do React StrictMode em dev) nem uma troca de props por
 *   refetch (que não desmonta a primitiva, só muda o valor que ela recebe)
 *   reagendam a animação. Ver `usePlantResource`: um refetch da MESMA usina
 *   preserva `data` anterior e só troca o valor final, sem desmontar quem
 *   consome o dado — a primitiva já montada apenas recebe um novo `value`/
 *   `items` e re-renderiza direto no valor novo, sem passar pelo estado 0
 *   de novo.
 * - Quando `prefers-reduced-motion: reduce` está ativo, começa já em
 *   `true` (valor final desde o primeiro render, sem nenhum "0" visível
 *   nem transição) — checado uma única vez, de forma síncrona, no
 *   inicializador de `useState` (antes da primeira pintura), para nunca
 *   haver um frame de "vazio" piscando antes do valor final.
 */
export function useChartEntrance(): boolean {
  const [entered, setEntered] = useState(prefersReducedMotion)
  const hasAnimatedRef = useRef(entered)

  useEffect(() => {
    if (hasAnimatedRef.current) return
    hasAnimatedRef.current = true

    const timer = window.setTimeout(() => setEntered(true), ENTRANCE_TICK_MS)
    return () => window.clearTimeout(timer)
  }, [])

  return entered
}
