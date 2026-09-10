import { type FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Alert } from '@/components/ui/Alert';
import { OAuthButtons } from '@/components/auth/OAuthButtons';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useAuth } from '@/hooks/authContext';
import { AuthLayout } from '@/layouts/AuthLayout';
import { ApiError } from '@/services/apiClient';

const MIN_PASSWORD_LENGTH = 8;

/** Mirrors the server-side policy so the user is told before a round trip. */
function validate(values: {
  full_name: string;
  email: string;
  password: string;
}): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!values.full_name.trim()) errors.full_name = 'Please enter your name.';
  if (!values.email.trim()) errors.email = 'Please enter your email address.';
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
    errors.email = 'That does not look like a valid email address.';
  }

  if (values.password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  } else if (!/[A-Za-z]/.test(values.password) || !/\d/.test(values.password)) {
    errors.password = 'Include at least one letter and one number.';
  }

  return errors;
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [values, setValues] = useState({ full_name: '', email: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function update(field: keyof typeof values) {
    return (event: React.ChangeEvent<HTMLInputElement>) => {
      setValues((current) => ({ ...current, [field]: event.target.value }));
      setFieldErrors((current) => {
        if (!current[field]) return current;
        const { [field]: _removed, ...rest } = current;
        return rest;
      });
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const errors = validate(values);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setIsSubmitting(true);
    try {
      await register({
        full_name: values.full_name.trim(),
        email: values.email.trim(),
        password: values.password,
      });
      navigate('/projects', { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        // The server is the authority; surface its per-field messages verbatim.
        const serverFields = error.fieldErrors();
        if (Object.keys(serverFields).length > 0) setFieldErrors(serverFields);
        else setFormError(error.message);
      } else {
        setFormError('Something went wrong creating your account. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Create your Obseil account"
      subtitle="Upload a dataset and find out whether you can trust it."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-accent underline-offset-4 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <OAuthButtons action="Sign up" />

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {formError && <Alert tone="danger">{formError}</Alert>}

        <Input
          label="Full name"
          name="full_name"
          autoComplete="name"
          placeholder="Ada Lovelace"
          value={values.full_name}
          onChange={update('full_name')}
          error={fieldErrors.full_name}
          required
          // The form is the entire purpose of this page, so focusing the first
          // field is expected here rather than disorienting.
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus
        />

        <Input
          label="Email address"
          type="email"
          name="email"
          autoComplete="email"
          placeholder="you@company.com"
          value={values.email}
          onChange={update('email')}
          error={fieldErrors.email}
          required
        />

        <Input
          label="Password"
          type="password"
          name="password"
          autoComplete="new-password"
          placeholder="••••••••"
          value={values.password}
          onChange={update('password')}
          error={fieldErrors.password}
          hint="At least 8 characters, including a letter and a number."
          required
        />

        <Button type="submit" variant="primary" size="lg" fullWidth isLoading={isSubmitting}>
          {isSubmitting ? 'Creating account' : 'Create account'}
        </Button>
      </form>
    </AuthLayout>
  );
}
