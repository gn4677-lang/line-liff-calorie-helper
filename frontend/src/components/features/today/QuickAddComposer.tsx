import { useState, type FormEvent } from 'react';
import { Card } from '../../ui/Card';
import { Input } from '../../ui/Input';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';

interface QuickAddComposerProps {
  onSubmit: (input: string, type: 'text' | 'image' | 'voice' | 'video') => void;
  isLoading?: boolean;
}

export function QuickAddComposer({
  onSubmit,
  isLoading = false,
}: QuickAddComposerProps) {
  const [text, setText] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    onSubmit(text, 'text');
    setText('');
  };

  return (
    <Card padding="md" elevation="card" className="mx-4 mb-4 mt-2">
      <form onSubmit={handleSubmit} className="flex gap-2 w-full">
        <Input
          placeholder="吃了什麼？（例如：排骨便當一半）"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={isLoading}
        />
        <Button 
          type="submit" 
          variant="primary" 
          disabled={!text.trim() || isLoading}
          aria-label="Submit"
          style={{ width: '44px', minWidth: '44px', padding: 0 }}
        >
          {isLoading ? <Icon name="loader" className="animate-spin" size="sm" /> : <Icon name="arrowRight" size="sm" />}
        </Button>
      </form>

      {/* Media buttons row */}
      <div className="flex justify-between items-center mt-3 pt-3 border-t border-[var(--border-subtle)]">
        <div className="flex gap-2">
          <Button type="button" variant="ghost" className="!p-2 min-h-0 h-10 w-10 text-[var(--icon-secondary)]">
            <Icon name="camera" size="sm" />
          </Button>
          <Button type="button" variant="ghost" className="!p-2 min-h-0 h-10 w-10 text-[var(--icon-secondary)]">
            <Icon name="mic" size="sm" />
          </Button>
          <Button type="button" variant="ghost" className="!p-2 min-h-0 h-10 w-10 text-[var(--icon-secondary)]">
            <Icon name="video" size="sm" />
          </Button>
        </div>
      </div>
    </Card>
  );
}
