import { Info } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card, CardBody } from '@/components/ui/Card';
import { Modal } from '@/components/ui/Modal';
import { findingTypeLabel } from '@/services/findingsApi';
import type { QualityGrade, QualityScore } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatNumber, formatPercent } from '@/utils/format';

/**
 * The headline figure.
 *
 * A single number is not a chart: there is nothing to compare it against
 * within itself, so it gets the hero-number treatment — very large, one
 * qualitative label, one sentence of meaning — rather than a gauge with a
 * needle, which spends a lot of pixels encoding one value badly.
 *
 * The meter beneath it is the only graphical element, and it exists to place
 * the number inside its grade bands, which a bare figure cannot do.
 */

const GRADE_COLOR: Record<QualityGrade, string> = {
  excellent: 'text-success',
  good: 'text-low',
  needs_attention: 'text-medium',
  poor: 'text-high',
  critical: 'text-critical',
};

const GRADE_TRACK: Record<QualityGrade, string> = {
  excellent: 'bg-success',
  good: 'bg-low',
  needs_attention: 'bg-medium',
  poor: 'bg-high',
  critical: 'bg-critical',
};

/** Band boundaries, mirroring `app.quality.scoring.GRADE_BANDS`. */
const BANDS = [
  { from: 0, to: 40, label: 'Critical' },
  { from: 40, to: 60, label: 'Poor' },
  { from: 60, to: 80, label: 'Needs attention' },
  { from: 80, to: 95, label: 'Good' },
  { from: 95, to: 100, label: 'Excellent' },
];

function ScoreMeter({ score, grade }: { score: number; grade: QualityGrade }) {
  return (
    <div>
      <div
        className="relative flex h-2 w-full overflow-hidden rounded-full bg-surface-muted"
        role="img"
        aria-label={`Quality score ${score} out of 100, graded ${grade.replace('_', ' ')}`}
      >
        <div
          className={cn('h-full rounded-full transition-[width] duration-500', GRADE_TRACK[grade])}
          style={{ width: `${Math.max(score, 1.5)}%` }}
        />
        {/* Band boundaries: the number alone cannot tell you where the lines are. */}
        {BANDS.slice(1).map((band) => (
          <span
            key={band.from}
            aria-hidden="true"
            className="absolute top-0 h-full w-px bg-surface"
            style={{ left: `${band.from}%` }}
          />
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-fg-subtle">
        <span>0</span>
        <span>40</span>
        <span>60</span>
        <span>80</span>
        <span>95</span>
        <span>100</span>
      </div>
    </div>
  );
}

function DimensionBar({
  label,
  penalty,
  cap,
  capped,
  findingCount,
}: {
  label: string;
  penalty: number;
  cap: number;
  capped: boolean;
  findingCount: number;
}) {
  const share = cap > 0 ? (penalty / cap) * 100 : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className="text-fg">{label}</span>
        <span className="tabular text-fg-muted">
          {penalty === 0 ? (
            <span className="text-success">clear</span>
          ) : (
            <>
              −{formatNumber(penalty, 1)}
              <span className="text-fg-subtle"> of {formatNumber(cap)}</span>
            </>
          )}
        </span>
      </div>
      {/* Bar length always means "points lost", so a clear dimension is an
          empty track rather than a full green one — two encodings in the same
          chart would be worse than none. */}
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
        {penalty > 0 && (
          <div
            className="h-full rounded-full bg-fg-muted"
            style={{ width: `${Math.max(share, 3)}%` }}
          />
        )}
      </div>
      <p className="mt-1 text-[11px] text-fg-subtle">
        {findingCount === 0
          ? 'No findings'
          : `${formatNumber(findingCount)} finding${findingCount === 1 ? '' : 's'}`}
        {capped && ' · capped'}
      </p>
    </div>
  );
}

export function QualityScoreCard({ score }: { score: QualityScore }) {
  const [isExplainerOpen, setExplainerOpen] = useState(false);

  return (
    <>
      <Card>
        <CardBody className="grid gap-8 p-6 lg:grid-cols-[minmax(0,20rem)_1fr]">
          <div>
            <p className="text-[12px] font-medium uppercase tracking-wide text-fg-subtle">
              Dataset quality
            </p>
            <p className="mt-2 flex items-baseline gap-1.5">
              <span
                className={cn(
                  'tabular text-6xl font-semibold tracking-[-0.04em]',
                  GRADE_COLOR[score.grade],
                )}
              >
                {formatNumber(score.score, 1)}
              </span>
              <span className="text-xl font-medium text-fg-subtle">/ 100</span>
            </p>
            <p className={cn('mt-1 text-sm font-medium', GRADE_COLOR[score.grade])}>
              {score.grade_label}
            </p>

            <div className="mt-5">
              <ScoreMeter score={score.score} grade={score.grade} />
            </div>

            <p className="mt-4 text-[13px] leading-relaxed text-fg-muted">{score.summary}</p>

            <Button
              variant="link"
              size="sm"
              className="mt-3 text-[13px]"
              leadingIcon={<Info className="size-3.5" />}
              onClick={() => setExplainerOpen(true)}
            >
              Why this score?
            </Button>
          </div>

          <div>
            <h3 className="text-[12px] font-medium uppercase tracking-wide text-fg-subtle">
              Where the points went
            </h3>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {score.dimensions.map((dimension) => (
                <DimensionBar
                  key={dimension.dimension}
                  label={dimension.label}
                  penalty={dimension.penalty}
                  cap={dimension.cap}
                  capped={dimension.capped}
                  findingCount={dimension.finding_count}
                />
              ))}
            </div>
          </div>
        </CardBody>
      </Card>

      <Modal
        open={isExplainerOpen}
        onClose={() => setExplainerOpen(false)}
        size="md"
        title="How this score was calculated"
        description={score.methodology}
      >
        <div className="space-y-5">
          <div className="rounded-lg border border-border-default bg-surface-muted p-4">
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-fg-muted">Starting score</span>
              <span className="tabular font-medium text-fg">100.0</span>
            </div>
            {score.dimensions
              .filter((dimension) => dimension.penalty > 0)
              .map((dimension) => (
                <div
                  key={dimension.dimension}
                  className="mt-2 flex items-baseline justify-between text-sm"
                >
                  <span className="text-fg-muted">
                    {dimension.label}
                    {dimension.capped && (
                      <span className="ml-1.5 text-[11px] text-fg-subtle">
                        (capped from {formatNumber(dimension.raw_penalty, 1)})
                      </span>
                    )}
                  </span>
                  <span className="tabular font-medium text-fg">
                    −{formatNumber(dimension.penalty, 1)}
                  </span>
                </div>
              ))}
            <div className="mt-3 flex items-baseline justify-between border-t border-border-default pt-3 text-sm">
              <span className="font-medium text-fg">Final score</span>
              <span className="tabular text-lg font-semibold text-fg">
                {formatNumber(score.score, 1)}
              </span>
            </div>
          </div>

          {score.top_contributors.length > 0 && (
            <div>
              <h3 className="text-[12px] font-medium uppercase tracking-wide text-fg-subtle">
                Most expensive findings
              </h3>
              <ul className="mt-3 space-y-2">
                {score.top_contributors.map((contribution, index) => (
                  <li
                    key={`${contribution.finding_type}-${contribution.column}-${index}`}
                    className="flex items-baseline justify-between gap-4 text-[13px]"
                  >
                    <span className="min-w-0 text-fg">
                      {findingTypeLabel(contribution.finding_type)}
                      {contribution.column && (
                        <span className="ml-1.5 font-mono text-[12px] text-fg-subtle">
                          {contribution.column}
                        </span>
                      )}
                    </span>
                    <span className="tabular shrink-0 text-fg-muted">
                      −{formatNumber(contribution.penalty, 1)}
                      {contribution.affected_percentage !== null && (
                        <span className="ml-1.5 text-fg-subtle">
                          ({formatPercent(contribution.affected_percentage)})
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-[13px] leading-relaxed text-fg-subtle">
            Each dimension has a ceiling so that one noisy category cannot dominate the result. The
            ceilings deliberately sum to more than 100, so a dataset broken in every dimension can
            reach zero.
          </p>
        </div>
      </Modal>
    </>
  );
}
