import { useState } from 'react'

import { Button } from '../../ui/Button'
import { Icon } from '../../ui/Icon'
import { Input } from '../../ui/Input'

interface Meal {
  id: string
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  description: string
  kcal: number
}

type EditableFields = {
  desc: string
  kcal: string
  type: Meal['type']
}

type InlineEditState =
  | { mode: 'view' }
  | ({ mode: 'editing' } & EditableFields)
  | { mode: 'saving' }
  | ({ mode: 'error'; message: string } & EditableFields)

interface InlineEditorProps {
  meal: Meal
  onSave: (id: string, updates: Omit<Meal, 'id'>) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onCancel: () => void
}

export function InlineEditor({ meal, onSave, onDelete, onCancel }: InlineEditorProps) {
  const [state, setState] = useState<InlineEditState>({
    mode: 'editing',
    desc: meal.description,
    kcal: String(meal.kcal),
    type: meal.type,
  })

  const editable: EditableFields =
    state.mode === 'editing' || state.mode === 'error'
      ? { desc: state.desc, kcal: state.kcal, type: state.type }
      : { desc: meal.description, kcal: String(meal.kcal), type: meal.type }

  const handleSave = async () => {
    if (!editable.desc.trim() || !editable.kcal) return

    setState({ mode: 'saving' })
    try {
      await onSave(meal.id, {
        description: editable.desc,
        kcal: Number(editable.kcal),
        type: editable.type,
      })
      onCancel()
    } catch {
      setState({
        mode: 'error',
        message: '更新失敗，請稍後再試。',
        ...editable,
      })
    }
  }

  const handleDelete = async () => {
    setState({ mode: 'saving' })
    try {
      await onDelete(meal.id)
      onCancel()
    } catch {
      setState({
        mode: 'error',
        message: '刪除失敗，請稍後再試。',
        ...editable,
      })
    }
  }

  const isSaving = state.mode === 'saving'

  return (
    <div className="inline-editor card card-elev-elevated mb-3 border-[2px] border-[var(--olive-light)] bg-white p-4">
      {state.mode === 'error' && (
        <div className="inline-error mb-3 flex items-center gap-2 rounded-md bg-[var(--olive-soft)] p-3 text-[var(--text-small)] text-[var(--olive-deep)]">
          <Icon name="alertTriangle" size="sm" />
          <span>{state.message}</span>
        </div>
      )}

      <div className="flex flex-col gap-3">
        <select
          className="input-field"
          value={editable.type}
          disabled={isSaving}
          onChange={(e) =>
            setState((prev) =>
              prev.mode === 'editing' || prev.mode === 'error'
                ? { ...prev, type: e.target.value as Meal['type'] }
                : prev,
            )
          }
        >
          <option value="breakfast">早餐</option>
          <option value="lunch">午餐</option>
          <option value="dinner">晚餐</option>
          <option value="snack">點心</option>
        </select>

        <Input
          placeholder="餐點描述"
          value={editable.desc}
          disabled={isSaving}
          onChange={(e) =>
            setState((prev) =>
              prev.mode === 'editing' || prev.mode === 'error'
                ? { ...prev, desc: e.target.value }
                : prev,
            )
          }
        />

        <Input
          type="number"
          placeholder="熱量"
          value={editable.kcal}
          disabled={isSaving}
          onChange={(e) =>
            setState((prev) =>
              prev.mode === 'editing' || prev.mode === 'error'
                ? { ...prev, kcal: e.target.value }
                : prev,
            )
          }
        />
      </div>

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel} disabled={isSaving}>
          取消
        </Button>
        <Button variant="outline" onClick={handleDelete} disabled={isSaving}>
          <Icon name="delete" size="sm" className="mr-1" />
          刪除
        </Button>
        <Button variant="primary" onClick={handleSave} isLoading={isSaving} disabled={!editable.desc.trim() || !editable.kcal}>
          儲存
        </Button>
      </div>
    </div>
  )
}
