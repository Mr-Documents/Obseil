import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, FolderPlus, Plus } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { PageContent, PageHeader } from '@/components/ui/PageHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/toastContext';
import { ApiError } from '@/services/apiClient';
import { projectKeys, projectsApi } from '@/services/projectsApi';
import type { ProjectSummary } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatNumber, formatRelative } from '@/utils/format';

/** Colour follows the score's grade band, matching the dataset dashboard. */
function scoreTone(score: number): string {
  if (score >= 95) return 'text-success';
  if (score >= 80) return 'text-low';
  if (score >= 60) return 'text-medium';
  if (score >= 40) return 'text-high';
  return 'text-critical';
}

function ProjectCard({ project }: { project: ProjectSummary }) {
  const score = project.latest_quality_score;

  return (
    <Card interactive className="h-full">
      <Link to={`/projects/${project.id}`} className="block h-full rounded-card p-5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="truncate text-sm font-semibold tracking-[-0.01em] text-fg">
            {project.name}
          </h2>
          {score !== null && (
            <span
              className={cn('tabular shrink-0 text-lg font-semibold', scoreTone(score))}
              title="Most recent quality score in this project"
            >
              {formatNumber(score, 0)}
              <span className="text-[11px] font-normal text-fg-subtle"> / 100</span>
            </span>
          )}
        </div>
        <p className="mt-1.5 line-clamp-2 min-h-[2.5rem] text-[13px] leading-relaxed text-fg-muted">
          {project.description || 'No description yet.'}
        </p>
        <dl className="mt-4 flex items-center gap-4 text-[13px]">
          <div className="flex items-center gap-1.5">
            <dt className="sr-only">Datasets</dt>
            <Database className="size-3.5 text-fg-subtle" aria-hidden="true" />
            <dd className="tabular text-fg-muted">{formatNumber(project.dataset_count)}</dd>
          </div>
          <div className="ml-auto text-fg-subtle">Updated {formatRelative(project.updated_at)}</div>
        </dl>
      </Link>
    </Card>
  );
}

function ProjectsSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }, (_, index) => (
        <Card key={index} className="p-5">
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-4/5" />
          <Skeleton className="mt-5 h-3 w-24" />
        </Card>
      ))}
    </div>
  );
}

function CreateProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      projectsApi.create({ name: name.trim(), description: description.trim() || null }),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      notify({ tone: 'success', title: `Project “${project.name}” created.` });
      setName('');
      setDescription('');
      setError(null);
      onClose();
    },
    onError: (cause) => {
      setError(
        cause instanceof ApiError ? cause.message : 'Could not create the project. Try again.',
      );
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      setError('Give the project a name.');
      return;
    }
    mutation.mutate();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New project"
      description="A project groups related datasets and their analysis history."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="create-project-form"
            isLoading={mutation.isPending}
          >
            Create project
          </Button>
        </>
      }
    >
      <form id="create-project-form" onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <Input
          label="Name"
          placeholder="Customer Transactions"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setError(null);
          }}
          required
          maxLength={120}
        />
        <Textarea
          label="Description"
          placeholder="Monthly card settlement exports from the payments warehouse."
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          hint="Optional. Helps collaborators understand what belongs here."
          maxLength={2000}
          rows={3}
        />
      </form>
    </Modal>
  );
}

export function ProjectsPage() {
  const [isDialogOpen, setDialogOpen] = useState(false);
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: projectKeys.list(),
    queryFn: () => projectsApi.list({ limit: 100 }),
  });

  const projects = data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Projects"
        description="Group your datasets, then upload a file to see what Obseil finds in it."
        actions={
          <Button
            variant="primary"
            leadingIcon={<Plus className="size-4" />}
            onClick={() => setDialogOpen(true)}
          >
            New project
          </Button>
        }
      />

      <PageContent>
        {isPending && <ProjectsSkeleton />}

        {isError && (
          <Alert
            tone="danger"
            title="Could not load your projects"
            action={
              <Button size="sm" variant="secondary" onClick={() => void refetch()}>
                Retry
              </Button>
            }
          >
            {error instanceof ApiError ? error.message : 'Please try again in a moment.'}
          </Alert>
        )}

        {!isPending && !isError && projects.length === 0 && (
          <Card>
            <EmptyState
              icon={FolderPlus}
              title="No projects yet"
              description="Create a project to hold your datasets. Most people start with one per data source."
              action={
                <Button
                  variant="primary"
                  leadingIcon={<Plus className="size-4" />}
                  onClick={() => setDialogOpen(true)}
                >
                  Create your first project
                </Button>
              }
            />
          </Card>
        )}

        {projects.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {projects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}
      </PageContent>

      <CreateProjectDialog open={isDialogOpen} onClose={() => setDialogOpen(false)} />
    </>
  );
}
