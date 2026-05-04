import { Settings } from 'lucide-react';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { listCards } from '@/cards/registry';
import { useCardPrefsStore } from '@/store/card-prefs-store';

export function DashboardSettingsDialog() {
  const cards = listCards('dashboard');
  const hiddenIds = useCardPrefsStore((s) => s.hiddenIds);
  const toggle = useCardPrefsStore((s) => s.toggle);

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" aria-label="設定">
          <Settings className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>顯示設定</DialogTitle>
          <DialogDescription>選擇要在 dashboard 顯示的卡片。</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          {cards.map((c) => {
            const visible = !hiddenIds.has(c.id);
            return (
              <label key={c.id} className="flex items-center gap-3 cursor-pointer">
                <Checkbox
                  checked={visible}
                  onCheckedChange={() => toggle(c.id)}
                  aria-label={c.label}
                />
                <span className="text-sm">{c.label}</span>
              </label>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
