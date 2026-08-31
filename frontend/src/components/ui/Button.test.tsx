import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Button } from './Button';

describe('Button', () => {
  it('renders its label and calls the handler', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Run analysis</Button>);

    await userEvent.click(screen.getByRole('button', { name: 'Run analysis' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('defaults to type="button" so it never submits a form by accident', () => {
    render(<Button>Cancel</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
  });

  it('cannot be double-submitted while loading', async () => {
    const onClick = vi.fn();
    render(
      <Button isLoading onClick={onClick}>
        Uploading
      </Button>,
    );

    const button = screen.getByRole('button', { name: /uploading/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');

    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('does not fire when disabled', async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Export
      </Button>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Export' }));
    expect(onClick).not.toHaveBeenCalled();
  });
});
