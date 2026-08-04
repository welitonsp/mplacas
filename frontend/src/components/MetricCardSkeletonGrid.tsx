import { Card } from './Card'

// Espelha aproximadamente o grid de página real (`DashboardPage`) — faixa
// full-width no topo seguida de uma área maior (gráfico) ao lado de uma
// coluna estreita — para a página não "piscar" um layout no carregamento e
// trocar para um completamente diferente quando os dados chegam.
export function MetricCardSkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-6 lg:grid-cols-12 lg:gap-6 items-start">
      <Card className="animate-pulse md:col-span-6 lg:col-span-12 h-24">
        <div className="h-3 bg-gray-200 rounded w-1/3" />
      </Card>
      <Card className="animate-pulse md:col-span-6 lg:col-span-8 2xl:col-span-9 h-64">
        <div className="h-3 bg-gray-200 rounded w-1/3" />
      </Card>
      <div className="grid grid-cols-1 gap-4 md:col-span-6 lg:col-span-4 2xl:col-span-3">
        {Array.from({ length: count }).map((_, i) => (
          <Card key={i} className="animate-pulse">
            <div className="h-3 bg-gray-200 rounded w-1/2 mb-3" />
            <div className="h-7 bg-gray-200 rounded w-2/3" />
          </Card>
        ))}
      </div>
    </div>
  )
}
