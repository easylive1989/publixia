import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DashboardSettingsDialog } from '../src/components/DashboardSettingsDialog';
import { _reset, registerCard } from '../src/cards/registry';
import { useCardPrefsStore } from '../src/store/card-prefs-store';

const Stub = () => null;

describe('DashboardSettingsDialog', () => {
  beforeEach(() => {
    _reset();
    registerCard({ id: 'a', label: 'A 卡', defaultPage: 'dashboard', component: Stub });
    registerCard({ id: 'b', label: 'B 卡', defaultPage: 'dashboard', component: Stub });
    useCardPrefsStore.setState({ hiddenIds: new Set() });
    localStorage.clear();
  });

  it('opens on trigger click and lists dashboard cards', async () => {
    render(<DashboardSettingsDialog />);
    await userEvent.click(screen.getByRole('button', { name: '設定' }));
    expect(screen.getByText('A 卡')).toBeInTheDocument();
    expect(screen.getByText('B 卡')).toBeInTheDocument();
  });

  it('checkbox reflects current hidden state and toggling updates the store', async () => {
    render(<DashboardSettingsDialog />);
    await userEvent.click(screen.getByRole('button', { name: '設定' }));
    const checkboxA = screen.getByRole('checkbox', { name: 'A 卡' });
    expect(checkboxA).toBeChecked();
    await userEvent.click(checkboxA);
    expect(useCardPrefsStore.getState().isHidden('a')).toBe(true);
  });
});
