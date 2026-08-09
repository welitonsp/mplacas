// Barra de ação "Atualizar" compartilhada pelos 4 módulos do painel
// (`pages/dashboard/*.tsx`, ADR-072, Etapa 6). Antes desta extração, cada
// módulo tinha sua própria cópia do mesmo JSX/lógica: um botão com texto
// "Atualizar"/"Atualizando..." conforme `loading`, disparando o refetch
// combinado dos recursos daquele módulo. `onRefresh`/`loading` continuam a
// cargo de cada módulo (cada um sabe combinar seus próprios recursos via
// `usePlantResource` — este componente não conhece nem `usePlantResource`
// nem quantos recursos existem por trás do botão).
export function RefreshBar({
  onRefresh,
  loading,
  className = 'mb-6',
}: {
  onRefresh: () => void
  loading: boolean
  className?: string
}) {
  return (
    <div className={`flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end ${className}`.trim()}>
      <div className="flex items-center gap-3">
        <button
          onClick={onRefresh}
          disabled={loading}
          className="rounded text-xs text-[var(--color-brand-primary)] hover:text-[var(--color-brand-primary-dark)] disabled:opacity-50 transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
        >
          {loading ? 'Atualizando...' : 'Atualizar'}
        </button>
      </div>
    </div>
  )
}
