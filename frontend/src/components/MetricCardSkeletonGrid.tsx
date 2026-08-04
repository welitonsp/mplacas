import { Card } from './Card'

export function MetricCardSkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <Card key={i} className="animate-pulse">
          <div className="h-3 bg-gray-200 rounded w-1/2 mb-3" />
          <div className="h-7 bg-gray-200 rounded w-2/3" />
        </Card>
      ))}
    </div>
  )
}
