import { Card } from './Card'

// Espelha aproximadamente o grid de página real (`DashboardPage`) — faixa
// full-width no topo seguida de uma área maior (gráfico) ao lado de uma
// coluna estreita — para a página não "piscar" um layout no carregamento e
// trocar para um completamente diferente quando os dados chegam.
export function MetricCardSkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Carregando painel"
      className="grid grid-cols-1 gap-4 md:grid-cols-6 lg:grid-cols-12 lg:gap-6 items-start"
    >
      <span className="sr-only">Carregando painel</span>
      <Card className="animate-pulse md:col-span-6 lg:col-span-12">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-3">
            <div className="h-3 w-28 rounded-full bg-gray-200" />
            <div className="h-8 w-64 max-w-full rounded-lg bg-gray-200" />
          </div>
          <div className="h-10 w-36 rounded-lg bg-gray-100" />
        </div>
      </Card>
      <Card className="animate-pulse md:col-span-4 lg:col-span-8 2xl:col-span-9 h-64 overflow-hidden">
        <div className="h-3 bg-gray-200 rounded w-1/3" />
        <div className="mt-8 flex h-40 items-end gap-3">
          {[50, 78, 62, 88, 70, 92, 64].map((height, index) => (
            <div
              key={index}
              className="flex-1 rounded-t-lg bg-gray-100"
              style={{ height: `${height}%` }}
            />
          ))}
        </div>
      </Card>
      <div className="grid grid-cols-1 gap-4 md:col-span-2 lg:col-span-4 2xl:col-span-3">
        {Array.from({ length: count }).map((_, i) => (
          <Card key={i} className="animate-pulse">
            <div className="mb-4 h-1 w-10 rounded-full bg-gray-200" />
            <div className="h-3 bg-gray-200 rounded w-1/2 mb-3" />
            <div className="h-7 bg-gray-200 rounded w-2/3" />
            <div className="mt-4 h-6 w-24 rounded-full bg-gray-100" />
          </Card>
        ))}
      </div>
    </div>
  )
}
