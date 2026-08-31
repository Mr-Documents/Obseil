# Obseil end-to-end tests

Playwright tests that drive the real application: a real API, a real production
build of the frontend, and the committed sample datasets.

## Running them

```bash
cd e2e
npm install
npm run install:browsers   # once

npm test                   # everything
npm run test:headed        # watch it happen
npm run test:ui            # Playwright's interactive runner
npm run report             # open the last HTML report
```

Playwright starts **both servers itself**, so there is one command to run and CI
needs no orchestration script.

### What it needs

The backend environment must be on `PATH` — an activated virtualenv, or CI's
installed dependencies. This is the same requirement as running `pytest`:

```bash
# Windows
..\backend\.venv\Scripts\activate
# macOS / Linux
source ../backend/.venv/bin/activate
```

The API runs against a **file-backed SQLite database** (`backend/var/e2e.db`),
not PostgreSQL. The migrations are deliberately dialect-neutral and are verified
against a real PostgreSQL service in a separate CI job, so proving the user
journey works does not need a database service.

Delete `backend/var/e2e.db` for a clean slate. Tests do not depend on it being
empty — each one registers its own account.

### One gotcha

`reuseExistingServer` is enabled outside CI, which keeps the loop fast but means
**a preview server left running from an earlier session will serve a stale
bundle**. If a test fails on a change you just made to the frontend, stop the
old server (or run `npm run build` in `frontend/`) and try again. CI always
starts fresh.

## What is covered

| Spec                      | Covers                                                                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `journey.spec.ts`         | The acceptance journey: register → project → upload → score → findings → triage → anomalies → rows → columns → export                 |
| `auth-and-errors.spec.ts` | Sign-in failures, deep-link redirects, session persistence, upload rejections, cross-account access, 404s, and the clean-dataset path |
| `screenshots.spec.ts`     | Not assertions — captures every screen in both themes for design review. Skipped unless `OBSEIL_CAPTURE=1`.                           |

### Capturing screens for design review

```bash
OBSEIL_CAPTURE=1 npx playwright test screenshots
```

Writes `screenshots/{desktop,mobile}-NN-name.png` — every screen, both themes,
both breakpoints. The directory is git-ignored; the copies used by the root
README live in `docs/screenshots/`. Reviewing these is how the invisible
sub-1% bars in the missing-values chart and the clipped tab strip were found.

`journey.spec.ts` also runs under a **Pixel 7 viewport**. The product promises
its tables stay usable on a phone, so that is exercised rather than asserted in
review. The desktop run additionally asserts the page never scrolls sideways.

## Writing a test

Use `tests/helpers.ts` — it has `register`, `signIn`, `createProject` and
`uploadDataset`, each of which waits on a real signal (a URL change, a dialog
closing) rather than a timeout.

Two rules that keep these tests honest:

1. **Query the way a user perceives the page** — by role and accessible name.
   If a locator is hard to write, that is usually a real accessibility gap.
2. **Never wait on a fixed delay.** Every helper waits for an assertion.
   Analysis runs inline and takes a few seconds, so the upload helper waits on
   the resulting navigation with a generous timeout instead.

## When one fails

Playwright keeps a trace, a screenshot and a video for every failure:

```bash
npx playwright show-trace test-results/<test-name>/trace.zip
```

The trace is a time-travelling DOM snapshot — usually faster than re-running.

Two real bugs in Obseil were found this way, not by the unit tests:

- signing in from a deep link landed on `/projects` instead of the requested
  page, because the inverse auth guard raced the login page's own redirect;
- the finding detail dialog kept showing stale state after a triage, so a
  reviewer saw no change until they closed and reopened it.
