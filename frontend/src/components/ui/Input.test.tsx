import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Input } from './Input';

describe('Input', () => {
  it('associates the label with the control', () => {
    render(<Input label="Email address" />);
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it('exposes the hint through aria-describedby', () => {
    render(<Input label="Password" hint="At least 8 characters." />);
    const input = screen.getByLabelText(/password/i);
    expect(input).toHaveAccessibleDescription('At least 8 characters.');
  });

  it('announces errors and marks the field invalid', () => {
    render(<Input label="Email address" error="That email is already registered." />);
    const input = screen.getByLabelText(/email address/i);

    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('That email is already registered.');
  });

  it('hides the hint once an error is present, to avoid conflicting guidance', () => {
    render(<Input label="Email" hint="Work email preferred." error="Enter a valid email." />);
    expect(screen.queryByText('Work email preferred.')).not.toBeInTheDocument();
  });
});
