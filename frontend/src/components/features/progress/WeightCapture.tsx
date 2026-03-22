import React, { useState } from 'react';
import { Card } from '../../ui/Card';
import { Input } from '../../ui/Input';
import { Button } from '../../ui/Button';

interface WeightCaptureProps {
  initialWeight?: number | null;
  onSave: (weight: number) => Promise<void>;
}

export function WeightCapture({ initialWeight, onSave }: WeightCaptureProps) {
  const [weight, setWeight] = useState(initialWeight ? String(initialWeight) : '');
  const [loading, setLoading] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const val = Number(weight);
    if (!val || isNaN(val)) return;

    setLoading(true);
    try {
      await onSave(val);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card elevation="card" padding="md" className="mx-4 my-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[var(--text-body)] font-medium text-[var(--text-primary)]">
          今日體重
        </h3>
      </div>
      <form onSubmit={handleSave} className="flex gap-2 w-full">
        <Input
          type="number"
          step="0.1"
          placeholder="例如：65.5"
          value={weight}
          onChange={(e) => setWeight(e.target.value)}
          disabled={loading}
        />
        <Button 
          type="submit" 
          variant="primary" 
          disabled={!weight.trim() || loading}
          isLoading={loading}
          className="whitespace-nowrap"
        >
          儲存
        </Button>
      </form>
    </Card>
  );
}
