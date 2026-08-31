import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, History, Pencil, Trash2, Upload } from 'lucide-react';
import { type FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { DatasetList } from '@/components/datasets/DatasetList';
import { UploadDialog } from '@/components/datasets/UploadDialog';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { buttonStyles } from '@/components/ui/buttonStyles';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { PageContent, PageHeader } from '@/components/ui/PageHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/toastContext';
import { ApiError } from '@/services/apiClient';
import { projectKeys, projectsApi } from '@/services/projectsApi';
import type { Project } from '@/types/api';
import { formatDateTime } from '@/utils/format';

function EditProjectDialog({
  project,
  open,
  onClose,
}: {
  project: Project;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? '');
  const [error, setError] = useState<string | null>(null);

  // Re-seed the form whenever a different project (or a fresh copy) arrives.
  useEffect(() => {
    setName(project.name);
    setDescription(project.description ?? '');
  }, [project]);

  const mutation = useMutation({
    mutationFn: () =>
      projectsApi.update(project.id, {
        name: name.trim(),
        description: description.trim() || null,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(projectKeys.detail(project.id), updated);
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      notify({ tone: 'success', title: 'Project updated.' });
      onClose();
    },
    onError: (cause) =>
      setError(cause instanceof ApiError ? cause.message : 'Could not save your changes.'),
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
      title="Edit project"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="edit-project-form"
            isLoading={mutation.isPending}
          >
            Save changes
          </Button>
        </>
      }
    >
      <form id="edit-project-form" onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <Input
          label="Name"
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
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={2000}
          rows={3}
        />
      </form>
    </Modal>
  );
}

function DeleteProjectDialog({
  project,
  open,
  onClose,
}: {
  project: Project;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { notify } = useToast();
  const [confirmation, setConfirmation] = useState('');

  const mutation = useMutation({
    mutationFn: () => projectsApi.remove(project.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      notify({ tone: 'success', title: `Project “${project.name}” deleted.` });
      navigate('/projects', { replace: true });
    },
    onError: (cause) =>
      notify({
        tone: 'error',
        title: 'Could not delete the project',
        description: cause instanceof ApiError ? cause.message : 'Please try again.',
      }),
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Delete this project?"
      description="Its datasets, analyses and findings are deleted with it. This cannot be undone."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            disabled={confirmation !== project.name}
            isLoading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Delete project
          </Button>
        </>
      }
    >
      <Input
        label={`Type “${project.name}” to confirm`}
        value={confirmation}
        onChange={(event) => setConfirmation(event.target.value)}
        autoComplete="off"
      />
    </Modal>
  );
}

export function ProjectDetailPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [isEditOpen, setEditOpen] = useState(false);
  const [isDeleteOpen, setDeleteOpen] = useState(false);
  const [isUploadOpen, setUploadOpen] = useState(false);

  const {
    data: project,
    isPending,
    isError,
    error,
  } = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => projectsApi.get(projectId),
    enabled: Boolean(projectId),
  });

  if (isPending) {
    return (
      <>
        <PageHeader title={<Skeleton className="h-7 w-56" />} />
        <PageContent>
          <Skeleton className="h-40 w-full" />
        </PageContent>
      </>
    );
  }

  if (isError || !project) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <PageContent>
        <Alert tone="danger" title={notFound ? 'Project not found' : 'Could not load this project'}>
          {notFound
            ? 'It may have been deleted, or you may not have access to it.'
            : error instanceof ApiError
              ? error.message
              : 'Please try again in a moment.'}
          <div className="mt-3">
            <Link
              to="/projects"
              className="font-medium text-accent underline-offset-4 hover:underline"
            >
              Back to projects
            </Link>
          </div>
        </Alert>
      </PageContent>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <Link
            to="/projects"
            className="inline-flex items-center gap-1 text-[13px] text-fg-muted transition-colors hover:text-fg"
          >
            <ChevronLeft className="size-3.5" aria-hidden="true" />
            Projects
          </Link>
        }
        title={project.name}
        description={project.description ?? undefined}
        actions={
          <>
            <Button
              variant="primary"
              leadingIcon={<Upload className="size-4" />}
              onClick={() => setUploadOpen(true)}
            >
              Upload dataset
            </Button>
            <Link
              to={`/projects/${project.id}/history`}
              className={buttonStyles({ variant: 'secondary' })}
            >
              <History className="size-4" aria-hidden="true" />
              History
            </Link>
            <Button
              variant="secondary"
              leadingIcon={<Pencil className="size-4" />}
              onClick={() => setEditOpen(true)}
            >
              Edit
            </Button>
            <Button
              variant="ghost"
              leadingIcon={<Trash2 className="size-4" />}
              onClick={() => setDeleteOpen(true)}
            >
              Delete
            </Button>
          </>
        }
      />

      <PageContent className="space-y-6">
        <Card>
          <CardHeader
            title="Datasets"
            description="Every file uploaded to this project, newest first."
            action={
              <Button
                size="sm"
                variant="secondary"
                leadingIcon={<Upload className="size-4" />}
                onClick={() => setUploadOpen(true)}
              >
                Upload
              </Button>
            }
          />
          <DatasetList projectId={project.id} onUploadClick={() => setUploadOpen(true)} />
        </Card>

        <Card>
          <CardHeader title="Details" />
          <CardBody>
            <dl className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-[13px] text-fg-subtle">Created</dt>
                <dd className="mt-0.5 text-sm text-fg">{formatDateTime(project.created_at)}</dd>
              </div>
              <div>
                <dt className="text-[13px] text-fg-subtle">Last updated</dt>
                <dd className="mt-0.5 text-sm text-fg">{formatDateTime(project.updated_at)}</dd>
              </div>
            </dl>
          </CardBody>
        </Card>
      </PageContent>

      <UploadDialog
        projectId={project.id}
        open={isUploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={(dataset) => navigate(`/datasets/${dataset.id}`)}
      />
      <EditProjectDialog project={project} open={isEditOpen} onClose={() => setEditOpen(false)} />
      <DeleteProjectDialog
        project={project}
        open={isDeleteOpen}
        onClose={() => setDeleteOpen(false)}
      />
    </>
  );
}
