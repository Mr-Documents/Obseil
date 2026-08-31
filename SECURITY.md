# Security Policy

## Supported versions

Obseil is pre-1.0. Security fixes are applied to `main` only.

## Reporting a vulnerability

**Please do not open a public GitHub issue for a security problem.**

Report it privately through
[GitHub Security Advisories](https://github.com/Obseil/Obseil/security/advisories/new).

Please include:

- A description of the issue and its impact
- Steps to reproduce, or a proof of concept
- The affected version or commit
- Any suggested mitigation

You can expect an acknowledgement within 72 hours and a status update within
seven days.

## Scope

In scope:

- Authentication and authorisation bypass
- Cross-tenant data access (reading another user's projects, datasets,
  analyses or findings)
- Injection of any kind (SQL, command, path traversal in upload handling)
- Remote code execution through dataset parsing
- Secrets exposure in logs, API responses, or built artefacts

Out of scope:

- Findings that require a compromised host or database
- Denial of service through deliberately enormous uploads beyond the configured
  `OBSEIL_MAX_UPLOAD_BYTES`
- Missing security headers on the development server
- Anything in a fork or a modified deployment

## Hardening notes for operators

- Set a strong `OBSEIL_SECRET_KEY`. The application refuses to start in
  `production` with the default value.
- Set `OBSEIL_ENV=production` and `OBSEIL_DEBUG=false`. This also disables the
  interactive API documentation.
- Restrict `OBSEIL_CORS_ORIGINS` to the exact origins that serve your frontend.
- Terminate TLS in front of the API; Obseil does not serve HTTPS itself.
- Uploaded files are written to `OBSEIL_STORAGE_PATH` under generated names.
  Mount that path on a volume that is not web-accessible.
- Run behind a reverse proxy that enforces a request body limit at least as
  strict as `OBSEIL_MAX_UPLOAD_BYTES`.
