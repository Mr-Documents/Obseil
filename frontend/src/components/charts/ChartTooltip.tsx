import { type ReactNode } from 'react';

interface TooltipEntry {
  name?: string | number;
  value?: string | number;
  color?: string;
  payload?: Record<string, unknown>;
}

interface ChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: TooltipEntry[];
  /** Overrides the rendered value, e.g. to append a unit. */
  formatValue?: (value: number, entry: TooltipEntry) => ReactNode;
  /** Secondary line under the value. */
  renderDetail?: (entry: TooltipEntry) => ReactNode;
}

/**
 * One tooltip for every chart in the product.
 *
 * Values wear text tokens, not the series colour — the swatch beside them
 * carries the identity. Coloured numbers are harder to read and imply that the
 * hue means something about the value, which it does not.
 */
export function ChartTooltip({
  active,
  label,
  payload,
  formatValue,
  renderDetail,
}: ChartTooltipProps) {
  if (!active || !payload?.length) return null;

  return (
    <div className="pointer-events-none rounded-lg border border-border-default bg-surface px-3 py-2 shadow-md">
      {label !== undefined && (
        <p className="mb-1.5 text-[12px] font-medium text-fg">{String(label)}</p>
      )}
      <ul className="space-y-1">
        {payload.map((entry, index) => (
          <li key={index} className="flex items-center gap-2 text-[12px]">
            {entry.color && (
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rounded-[2px]"
                style={{ backgroundColor: entry.color }}
              />
            )}
            {entry.name !== undefined && <span className="text-fg-muted">{entry.name}</span>}
            <span className="tabular ml-auto font-medium text-fg">
              {formatValue && typeof entry.value === 'number'
                ? formatValue(entry.value, entry)
                : String(entry.value ?? '—')}
            </span>
          </li>
        ))}
      </ul>
      {renderDetail && payload[0] && (
        <div className="mt-1.5 border-t border-border-default pt-1.5 text-[11px] text-fg-subtle">
          {renderDetail(payload[0])}
        </div>
      )}
    </div>
  );
}
