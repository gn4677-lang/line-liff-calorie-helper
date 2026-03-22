import { useState } from 'react';
import { Icon } from '../../ui/Icon';
import type { IconName } from '../../../lib/icons';
import './FavoriteStores.css';

interface Store {
  id: string;
  name: string;
  iconName?: IconName;
}

interface FavoriteStoresProps {
  stores: Store[];
  onSelect: (storeId: string) => void;
  onAddStore: (name: string) => Promise<void>;
  isLoading?: boolean;
}

export function FavoriteStores({ stores, onSelect, onAddStore, isLoading }: FavoriteStoresProps) {
  const [isAdding, setIsAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [saving, setSaving] = useState(false);

  const handleAdd = async () => {
    if (!newName.trim()) return;
    setSaving(true);
    try {
      await onAddStore(newName.trim());
      setNewName('');
      setIsAdding(false);
    } finally {
      setSaving(false);
    }
  };
  if (!stores || stores.length === 0) {
    return null;
  }

  return (
    <div className="favorite-stores mt-6">
      <div className="mb-3 flex items-center justify-between px-4">
        <h3 className="text-[var(--text-title)] font-bold text-[var(--text-primary)]">常去店家</h3>
        <button className="text-[var(--text-small)] font-medium text-[var(--olive-deep)]" type="button">
          編輯
        </button>
      </div>

      <div className="store-scroller px-4">
        {stores.map((store) => (
          <button
            key={store.id}
            type="button"
            className="store-card"
            disabled={isLoading}
            onClick={() => onSelect(store.id)}
          >
            <div className="store-icon mb-2 text-[var(--olive-deep)]">
              <Icon name={store.iconName || 'store'} size={24} />
            </div>
            <span className="whitespace-nowrap text-[var(--text-small)] font-medium text-[var(--text-secondary)]">
              {store.name}
            </span>
          </button>
        ))}
        {isAdding ? (
          <div className="flex flex-col gap-2 min-w-[120px] p-2 bg-[var(--bg-card)] rounded-xl border border-[var(--olive-light)]">
            <input 
              className="text-[var(--text-small)] bg-transparent border-b border-[var(--border-subtle)] outline-none w-full pb-1"
              placeholder="輸入店名"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              disabled={saving}
              autoFocus
            />
            <div className="flex gap-1 justify-end">
              <button 
                type="button" 
                className="text-[10px] text-[var(--text-muted)] p-1"
                onClick={() => setIsAdding(false)}
                disabled={saving}
              >取消</button>
              <button 
                type="button" 
                className="text-[10px] text-[var(--olive-deep)] font-bold p-1"
                onClick={() => void handleAdd()}
                disabled={saving || !newName.trim()}
              >儲存</button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="store-card store-card-add"
            disabled={isLoading || saving}
            onClick={() => setIsAdding(true)}
          >
            <div className="store-icon mb-2 border border-dashed border-[var(--olive-light)] bg-transparent text-[var(--olive-medium)]">
              <Icon name="plus" size={24} />
            </div>
            <span className="whitespace-nowrap text-[var(--text-small)] font-medium text-[var(--text-muted)]">
              新增店家
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
