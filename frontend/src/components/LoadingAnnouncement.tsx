// Padrão único de anúncio acessível de carregamento (T10, auditoria de
// frontend 2026-08-12). Vários botões trocam de rótulo durante o
// carregamento (`Baixar PDF` → `Gerando PDF...`) e ficam `disabled`, mas
// mudança de nome acessível sem live region não é garantidamente anunciada
// por leitor de tela (WCAG 4.1.3 — Status Messages).
//
// Réplica do padrão já correto de `RefreshBar.tsx:36-45`: um elemento
// `aria-live="polite"` SEPARADO do botão (o `aria-live` não vai no próprio
// botão, que também troca `disabled`/rótulo ao mesmo tempo — isso é
// justamente o que os leitores de tela não garantem anunciar). `polite` para
// não interromper o usuário no meio de outra leitura. `sr-only` porque, ao
// contrário de `RefreshBar` (que já tinha uma pílula de status visível por
// design), estes botões não têm nenhuma UI de status visível — anunciar sem
// acrescentar elemento visual novo evita redesenho fora do escopo da tarefa.
// Fica vazio fora do carregamento: nenhuma verbosidade quando o estado não
// mudou (uma live region que sempre tem texto seria lida de novo a cada
// remontagem, sem necessidade).
export function LoadingAnnouncement({ active, message }: { active: boolean; message: string }) {
  return (
    <span aria-live="polite" className="sr-only">
      {active ? message : ''}
    </span>
  )
}
