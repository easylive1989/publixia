import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TokenGate } from '../src/components/TokenGate';
import { useAuthStore } from '../src/store/auth-store';

describe('TokenGate', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ token: null });
  });

  it('renders login form when no token', () => {
    render(<TokenGate><div>SECRET CONTENT</div></TokenGate>);
    expect(screen.getByText(/輸入 API token/)).toBeInTheDocument();
    expect(screen.queryByText('SECRET CONTENT')).not.toBeInTheDocument();
  });

  it('renders children when token is set', () => {
    useAuthStore.setState({ token: 'sd_abc' });
    render(<TokenGate><div>SECRET CONTENT</div></TokenGate>);
    expect(screen.getByText('SECRET CONTENT')).toBeInTheDocument();
    expect(screen.queryByText(/輸入 API token/)).not.toBeInTheDocument();
  });

  it('login form sets token in store', async () => {
    const user = userEvent.setup();
    render(<TokenGate><div>SECRET CONTENT</div></TokenGate>);
    await user.type(screen.getByPlaceholderText('sd_...'), 'sd_typed');
    await user.click(screen.getByRole('button', { name: '登入' }));
    expect(useAuthStore.getState().token).toBe('sd_typed');
  });
});
