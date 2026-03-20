import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { createPortal } from 'react-dom'

type SheetProps = {
  isOpen: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

function useBodyLock(isOpen: boolean) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])
}

export function BottomSheet({ isOpen, onClose, title, children }: SheetProps) {
  useBodyLock(isOpen)
  if (!isOpen) return null

  return createPortal(
    <div className="sheet-overlay" onClick={onClose}>
      <div className="bottom-sheet" onClick={(event) => event.stopPropagation()}>
        <div className="sheet-header">
          <h3 className="text-title font-bold">{title}</h3>
          <button className="btn btn-outline" type="button" onClick={onClose}>關閉</button>
        </div>
        <div className="sheet-content">{children}</div>
      </div>
    </div>,
    document.body,
  )
}

export function FullScreenSheet({ isOpen, onClose, title, children }: SheetProps) {
  useBodyLock(isOpen)
  if (!isOpen) return null

  return createPortal(
    <div className="full-screen-sheet">
      <div className="full-screen-sheet-header">
        <h3 className="text-title font-bold">{title}</h3>
        <button className="btn btn-outline" type="button" onClick={onClose}>關閉</button>
      </div>
      <div className="full-screen-sheet-content">{children}</div>
    </div>,
    document.body,
  )
}
