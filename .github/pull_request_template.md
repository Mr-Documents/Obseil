# Summary

<!-- What does this change, and why? One paragraph. -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] New quality detector
- [ ] New anomaly detection algorithm
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Build / CI

## How was it tested?

<!-- Name the tests you added, and anything you verified by hand. -->

## Checklist

- [ ] `ruff check .`, `black --check .`, `mypy app` and `pytest` pass in `backend/`
- [ ] `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm test` and
      `npm run build` pass in `frontend/`
- [ ] New behaviour is covered by tests
- [ ] Database changes ship with an Alembic migration that also downgrades
- [ ] New configuration is documented in `.env.example`
- [ ] No secrets, credentials, or real data are included
- [ ] User-facing errors are understandable and expose no stack traces
- [ ] UI changes were checked at mobile and desktop widths, in light and dark themes
- [ ] Methodology changes are reflected in `docs/METHODOLOGY.md`

## Screenshots

<!-- For UI changes: before and after, light and dark. -->
