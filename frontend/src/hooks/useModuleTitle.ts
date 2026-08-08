import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

// `document.title` por módulo do painel (ADR-072, Etapa 6) — mesmo padrão já
// usado por `index.html` (`<title>Mplacas — Dashboard</title>`), só trocando
// o segundo termo pelo nome do módulo ativo (ex.: "Mplacas — Visão Geral").
//
// Também move o foco para o `<h1>` do módulo assim que ele monta: sem isso,
// um leitor de tela não percebe a troca de "página" numa navegação
// client-side entre `/dashboard/visao-geral`, `/dashboard/producao` etc. —
// `react-router` não reseta o foco sozinho (diferente de uma navegação de
// documento completo, que o browser manda para o topo por padrão). Padrão
// recomendado pelas WAI-ARIA Authoring Practices para SPAs: mover o foco
// para o heading principal do conteúdo novo, não para o topo do documento.
//
// Centralizado aqui em vez de duplicado 4x (um `useEffect` por módulo) ou
// empurrado para `DashboardLayout` (que só monta `<Outlet/>` — colocar a
// lógica lá exigiria um mapa `pathname -> título` acoplando o layout aos 4
// paths, ver ADR-072 seção 4 sobre o que fica fora de qualquer módulo). Cada
// módulo chama `useModuleTitle('Nome do módulo')` uma vez e aplica o `ref`
// devolvido ao seu próprio `<h1 ref={...} tabIndex={-1}>`.
//
// `tabIndex={-1}` no `<h1>` de quem consome este hook: torna o heading
// focável via `.focus()` sem inseri-lo na ordem normal de tabulação (Tab) —
// ele não é um controle interativo, só o alvo do foco programático desta
// navegação.
export function useModuleTitle(title: string): RefObject<HTMLHeadingElement | null> {
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    document.title = `Mplacas — ${title}`
    headingRef.current?.focus()
  }, [title])

  return headingRef
}
