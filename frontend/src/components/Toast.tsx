import { useEffect, useState } from 'react'
import { ICONS } from '../lib/icons'
import './Toast.css'

export type ToastType = 'success' | 'error'

export interface ToastMessage {
  id: string
  message: string
  type: ToastType
}

interface ToastProps {
  message: string
  type: ToastType
  onDismiss: () => void
}

function ToastItem({ message, type, onDismiss }: ToastProps) {
  const [isExiting, setIsExiting] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsExiting(true)
    }, 2700)

    const dismissTimer = setTimeout(() => {
      onDismiss()
    }, 3000)

    return () => {
      clearTimeout(timer)
      clearTimeout(dismissTimer)
    }
  }, [onDismiss])

  const handleClick = () => {
    setIsExiting(true)
    setTimeout(onDismiss, 300)
  }

  const IconComponent = type === 'success' ? ICONS.check : ICONS.alertTriangle
  const CloseIcon = ICONS.x

  return (
    <div 
      className={`toast-item toast-item--${type} ${isExiting ? 'toast-item--exit' : ''}`}
      onClick={handleClick}
      role="alert"
      aria-live="polite"
    >
      <IconComponent size={18} strokeWidth={1.5} />
      <span className="toast-message">{message}</span>
      <button className="toast-close" aria-label="關閉">
        <CloseIcon size={14} strokeWidth={1.5} />
      </button>
    </div>
  )
}

interface ToastContainerProps {
  toasts: ToastMessage[]
  onDismiss: (id: string) => void
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null

  return (
    <div className="toast-container">
      {toasts.map((toast) => (
        <ToastItem
          key={toast.id}
          message={toast.message}
          type={toast.type}
          onDismiss={() => onDismiss(toast.id)}
        />
      ))}
    </div>
  )
}

export function useToast() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  const showToast = (message: string, type: ToastType = 'success') => {
    const id = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    setToasts((prev) => [...prev, { id, message, type }])
  }

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  return { toasts, showToast, dismissToast }
}
