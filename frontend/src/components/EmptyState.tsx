import type { ReactNode } from 'react'
import { OperationalState, type OperationalStateTone } from './OperationalState'

export function EmptyState({
  eyebrow,
  title,
  description,
  action,
  tone = 'neutral',
  className = '',
}: {
  eyebrow?: string
  title: string
  description: string
  action?: ReactNode
  tone?: OperationalStateTone
  className?: string
}) {
  return (
    <OperationalState
      eyebrow={eyebrow}
      title={title}
      description={description}
      action={action}
      tone={tone}
      icon="empty"
      className={`px-4 py-8 sm:px-6 sm:py-10 ${className}`.trim()}
    />
  )
}
