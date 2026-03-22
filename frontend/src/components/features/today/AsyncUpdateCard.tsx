import { useState } from 'react'

import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Icon } from '../../ui/Icon'
import type { Notification } from '../../../types'

interface AsyncUpdateCardProps {
  notification: Notification
  onApply: (notification: Notification) => Promise<void>
  onDismiss: (notification: Notification) => Promise<void>
  onMarkRead: (id: string) => Promise<void>
}

function hasSuggestedUpdate(notification: Notification): boolean {
  const payload = notification.payload as { suggested_update?: unknown }
  return Boolean(
    payload.suggested_update &&
      typeof payload.suggested_update === 'object' &&
      Object.keys(payload.suggested_update as object).length,
  )
}

export function AsyncUpdateCard({
  notification,
  onApply,
  onDismiss,
  onMarkRead,
}: AsyncUpdateCardProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleAction = async (action: () => Promise<void>) => {
    setLoading(true)
    setError(null)
    try {
      await action()
    } catch {
      setError('操作失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  const actionable = hasSuggestedUpdate(notification)
  const dateStr = new Date(notification.created_at).toLocaleString('zh-TW', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <Card padding="md" elevation="card" className="mx-4 mb-4 border-l-4 border-l-[var(--olive-medium)]">
      <div className="mb-2 flex items-start justify-between">
        <div className="flex flex-col">
          <div className="text-[var(--text-heading)] font-semibold text-[var(--text-primary)]">
            {notification.title}
          </div>
          <div className="text-[var(--text-caption)] text-[var(--text-muted)]">{dateStr}</div>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--olive-muted)] text-[var(--olive-deep)]">
          <Icon name="check" size="sm" />
        </div>
      </div>

      <p className="mb-4 text-[var(--text-body)] text-[var(--text-secondary)]">{notification.body}</p>

      {error && (
        <div className="inline-error mb-4 flex items-center gap-2 rounded-md bg-[var(--olive-soft)] p-3 text-[var(--text-small)] text-[var(--olive-deep)]">
          <Icon name="alertTriangle" size="sm" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex justify-end gap-2">
        {actionable ? (
          <>
            <Button variant="outline" isLoading={loading} onClick={() => handleAction(() => onDismiss(notification))}>
              忽略
            </Button>
            <Button
              variant="primary"
              isLoading={loading}
              loadingText="套用中..."
              onClick={() => handleAction(() => onApply(notification))}
            >
              套用更新
            </Button>
          </>
        ) : (
          <Button variant="ghost" isLoading={loading} onClick={() => handleAction(() => onMarkRead(notification.id))}>
            標記已讀
          </Button>
        )}
      </div>
    </Card>
  )
}
