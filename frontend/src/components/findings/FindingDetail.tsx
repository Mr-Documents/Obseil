import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  CircleSlash,
  Lightbulb,
  Microscope,
  Target,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { type ReactNode, useEffect, useState } from 'react';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { useToast } from '@/hooks/toastContext';
import { ApiError } from '@/services/apiClient';
import { findingKeys, findingsApi, findingTypeLabel } from '@/services/findingsApi';
import type { Finding, FindingUpdatePayload } from '@/types/api';
import { formatNumber, formatPercent } from '@/utils/format';

import { CategoryBadge, SeverityBadge, StatusBadge } from './SeverityBadge';

function Section({
  icon: Icon,
  heading,
  children,
}: {
  icon: typeof Target;
  heading: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h3 className="flex items-center gap-1.5 text-[12px] font-medium uppercase tracking-wide text-fg-subtle">
        <Icon className="size-3.5" aria-hidden="true" />
        {heading}
      </h3>
      <div className="mt-2 text-[13px] leading-relaxed text-fg">{children}</div>
    </section>
  );
}

function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (Array.isArray(value)) return value.map((entry) => String(entry)).join(', ') || '—';
  if (typeof value === 'object') return JSON.stringify(value);
  if (typeof value === 'number') return formatNumber(value, 4);
  return String(value);
}

function humanizeKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/^./, (character) => character.toUpperCase());
}

/**
 * The full explanation of one finding, structured around the five questions a
 * finding must answer: what happened, where, why it matters, how it was
 * detected, and what to do.
 */
export function FindingDetail({
  finding,
  open,
  onClose,
}: {
  finding: Finding | null;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();

  // The dialog holds its own copy so that triaging updates what is on screen
  // immediately. Reading straight from the prop would leave the reviewer
  // looking at stale state until they closed and reopened the finding — and
  // the list behind the dialog may have re-filtered the row away entirely.
  const [current, setCurrent] = useState<Finding | null>(finding);
  useEffect(() => setCurrent(finding), [finding]);

  const triage = useMutation({
    mutationFn: (payload: FindingUpdatePayload) => findingsApi.update(current!.id, payload),
    onSuccess: (updated) => {
      setCurrent(updated);
      void queryClient.invalidateQueries({ queryKey: findingKeys.forDataset(updated.dataset_id) });
      notify({ tone: 'success', title: 'Finding updated.' });
    },
    onError: (cause) =>
      notify({
        tone: 'error',
        title: 'Could not update the finding',
        description: cause instanceof ApiError ? cause.message : 'Please try again.',
      }),
  });

  if (!current) return null;

  const isFalsePositive = current.feedback?.verdict === 'false_positive';
  const isValidIssue = current.feedback?.verdict === 'valid_issue';

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="md"
      title={current.title}
      description={findingTypeLabel(current.type)}
      footer={
        <>
          <Button
            variant={isFalsePositive ? 'secondary' : 'ghost'}
            leadingIcon={<ThumbsDown className="size-4" />}
            isLoading={triage.isPending && triage.variables?.verdict === 'false_positive'}
            onClick={() => triage.mutate({ verdict: 'false_positive' })}
          >
            False positive
          </Button>
          <Button
            variant={isValidIssue ? 'secondary' : 'ghost'}
            leadingIcon={<ThumbsUp className="size-4" />}
            isLoading={triage.isPending && triage.variables?.verdict === 'valid_issue'}
            onClick={() => triage.mutate({ verdict: 'valid_issue' })}
          >
            Valid issue
          </Button>
          <span className="hidden flex-1 sm:block" />
          {current.status === 'open' ? (
            <Button
              variant="primary"
              leadingIcon={<CheckCircle2 className="size-4" />}
              isLoading={triage.isPending && triage.variables?.status === 'reviewed'}
              onClick={() => triage.mutate({ status: 'reviewed' })}
            >
              Mark reviewed
            </Button>
          ) : (
            <Button
              variant="secondary"
              leadingIcon={<CircleSlash className="size-4" />}
              isLoading={triage.isPending && triage.variables?.status === 'open'}
              onClick={() => triage.mutate({ status: 'open' })}
            >
              Reopen
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={current.severity} />
          <StatusBadge status={current.status} />
          <CategoryBadge category={current.category} />
          {current.column_name && (
            <span className="rounded-md bg-surface-muted px-2 py-0.5 font-mono text-[12px] text-fg-muted">
              {current.column_name}
            </span>
          )}
        </div>

        {current.feedback && (
          <Alert tone={isFalsePositive ? 'warning' : 'success'}>
            You marked this a <strong>{isFalsePositive ? 'false positive' : 'valid issue'}</strong>.
            {current.feedback.note && <> “{current.feedback.note}”</>}
          </Alert>
        )}

        <Section icon={Target} heading="What happened">
          <p>{current.description}</p>
          {current.affected_rows !== null && (
            <p className="mt-2 text-fg-muted">
              Affects <span className="tabular text-fg">{formatNumber(current.affected_rows)}</span>{' '}
              rows
              {current.affected_percentage !== null && (
                <> ({formatPercent(current.affected_percentage)} of the dataset)</>
              )}
              .
            </p>
          )}
        </Section>

        <Section icon={CircleSlash} heading="Why it matters">
          <p>{current.impact}</p>
        </Section>

        <Section icon={Microscope} heading="How it was detected">
          <p>
            <span className="font-medium">{current.detection_method_label}</span>
          </p>
          {current.details && Object.keys(current.details).length > 0 && (
            <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 rounded-lg border border-border-default bg-surface-muted p-3 sm:grid-cols-2">
              {Object.entries(current.details).map(([key, value]) => (
                <div key={key} className="flex items-baseline justify-between gap-3">
                  <dt className="text-[12px] text-fg-subtle">{humanizeKey(key)}</dt>
                  <dd
                    className="tabular truncate text-right font-mono text-[12px] text-fg"
                    title={formatDetailValue(value)}
                  >
                    {formatDetailValue(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </Section>

        <Section icon={Lightbulb} heading="What to do">
          <p>{current.recommendation}</p>
        </Section>

        {current.sample_row_indices && current.sample_row_indices.length > 0 && (
          <Section icon={Target} heading="Example rows">
            <p className="font-mono text-[12px] text-fg-muted">
              {current.sample_row_indices.map((index) => index + 1).join(', ')}
            </p>
            <p className="mt-1 text-[12px] text-fg-subtle">Row numbers as shown in the Rows tab.</p>
          </Section>
        )}
      </div>
    </Modal>
  );
}
