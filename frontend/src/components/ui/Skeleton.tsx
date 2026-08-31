import { cn } from '@/utils/cn';

/**
 * Loading placeholder. Skeletons mirror the shape of the content they replace
 * so the layout does not jump when data arrives - the single biggest source of
 * perceived jank in data-heavy dashboards.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('animate-shimmer rounded-md bg-surface-muted', className)}
    />
  );
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className={cn('h-3.5', index === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  );
}
