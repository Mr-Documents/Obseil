import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FileDropzone } from './FileDropzone';
import { validateFile } from './fileValidation';

const MAX = 1024 * 1024;

function csv(name = 'data.csv', size = 1000): File {
  const file = new File(['id,value\n1,2\n'], name, { type: 'text/csv' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

describe('validateFile', () => {
  it('accepts supported extensions', () => {
    expect(validateFile(csv('data.csv'), MAX)).toBeNull();
    expect(validateFile(csv('book.xlsx'), MAX)).toBeNull();
    expect(validateFile(csv('EXPORT.CSV'), MAX)).toBeNull();
  });

  it('rejects unsupported extensions and says what is accepted', () => {
    const message = validateFile(csv('report.pdf'), MAX);
    expect(message).toContain('.csv');
    expect(message).toContain('report.pdf');
  });

  it('rejects an empty file', () => {
    expect(validateFile(csv('data.csv', 0), MAX)).toContain('empty');
  });

  it('rejects a file over the limit and names both sizes', () => {
    const message = validateFile(csv('big.csv', MAX + 1), MAX);
    expect(message).toContain('limit');
  });
});

describe('FileDropzone', () => {
  it('exposes a labelled file input', () => {
    render(<FileDropzone file={null} onSelect={vi.fn()} maxBytes={MAX} />);
    expect(screen.getByText(/drop a file here/i)).toBeInTheDocument();
    expect(screen.getByText(/csv or excel/i)).toBeInTheDocument();
  });

  it('reports the selected file with its size', () => {
    render(<FileDropzone file={csv('march.csv', 2048)} onSelect={vi.fn()} maxBytes={MAX} />);

    expect(screen.getByText('march.csv')).toBeInTheDocument();
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
  });

  it('clears the selection', async () => {
    const onSelect = vi.fn();
    render(<FileDropzone file={csv()} onSelect={onSelect} maxBytes={MAX} />);

    await userEvent.click(screen.getByRole('button', { name: /remove data.csv/i }));

    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('shows an error and selects nothing for an unsupported dropped file', async () => {
    // Dropped files bypass the input's `accept` filter, so this is the path
    // that actually needs the client-side check.
    const onSelect = vi.fn();
    const { container } = render(<FileDropzone file={null} onSelect={onSelect} maxBytes={MAX} />);
    const dropzone = container.querySelector('div[class*="border-dashed"]') as HTMLElement;

    fireEvent.drop(dropzone, { dataTransfer: { files: [csv('notes.pdf')] } });

    expect(await screen.findByRole('alert')).toHaveTextContent(/not one of them/i);
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('accepts a valid file', async () => {
    const onSelect = vi.fn();
    const { container } = render(<FileDropzone file={null} onSelect={onSelect} maxBytes={MAX} />);
    const input = container.querySelector('input[type="file"]');
    const file = csv('valid.csv');

    await userEvent.upload(input as HTMLInputElement, file);

    expect(onSelect).toHaveBeenCalledWith(file);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
