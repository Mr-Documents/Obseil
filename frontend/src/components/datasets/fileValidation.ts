import { formatBytes } from '@/utils/format';

export const ACCEPTED_EXTENSIONS = ['.csv', '.tsv', '.txt', '.xlsx', '.xlsm'] as const;
export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(',');

/**
 * Client-side checks are a courtesy, not a control: the server validates the
 * extension, the size and the actual file contents again. Catching the obvious
 * cases here just saves the user a round trip.
 */
export function validateFile(file: File, maxBytes: number): string | null {
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if (!ACCEPTED_EXTENSIONS.includes(extension as (typeof ACCEPTED_EXTENSIONS)[number])) {
    return `Obseil reads ${ACCEPTED_EXTENSIONS.join(', ')} files. “${file.name}” is not one of them.`;
  }
  if (file.size === 0) {
    return `“${file.name}” is empty.`;
  }
  if (file.size > maxBytes) {
    return `“${file.name}” is ${formatBytes(file.size)}, above the ${formatBytes(maxBytes)} limit.`;
  }
  return null;
}
