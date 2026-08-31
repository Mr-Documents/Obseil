# Contributing to Obseil

Thanks for considering a contribution. Obseil is meant to be extended, and the
codebase is deliberately organised so that the most common contributions - a
new quality detector, a new anomaly detector, a new file format, a new chart -
touch one small area each.

## Ground rules

- Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Open an issue before starting anything large, so we can agree on the approach.
- Every change ships with tests. CI enforces this.
- No secrets, credentials, or real customer data in the repository - ever.

## Getting set up

```bash
git clone https://github.com/<you>/Obseil.git
cd Obseil
cp .env.example .env

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# Frontend
cd ../frontend
npm install
```

Bring up PostgreSQL with `docker compose up db`, then `alembic upgrade head`.

## Before you open a pull request

Run exactly what CI runs:

```bash
# Backend
cd backend
ruff check .
black --check .
mypy app
pytest

# Frontend
cd frontend
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

## Commit and PR conventions

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(quality): detect mixed-type columns
fix(api): return 413 instead of 500 for oversized uploads
docs(readme): document the quality-score methodology
test(ml): cover Isolation Forest with too few numeric columns
```

Keep pull requests focused. A PR that does one thing well is reviewed in
minutes; a PR that does five things sits for a week.

## Where things live

| You want to… | Work in |
| --- | --- |
| Add an API endpoint | `backend/app/api/v1/routes/` + `schemas/` + `services/` |
| Change business logic | `backend/app/services/` |
| Add a profiling statistic | `backend/app/profiling/` |
| Add a quality detector | `backend/app/quality/detectors/` |
| Add an anomaly algorithm | `backend/app/ml/detectors/` |
| Add a file format | `backend/app/data/readers/` |
| Add a report format | `backend/app/reports/` |
| Add a UI component | `frontend/src/components/` |
| Add a chart | `frontend/src/components/charts/` |

Route handlers stay thin: parse, authorise, delegate, serialise. Business logic
belongs in `services/`; data logic belongs in `profiling/`, `quality/` and
`ml/`, which know nothing about HTTP or the ORM.

## Adding a quality detector

1. Create a module in `backend/app/quality/detectors/`.
2. Subclass `QualityDetector` and implement `detect(context) -> list[FindingDraft]`.
3. Register it in `backend/app/quality/registry.py`.
4. Add a unit test in `backend/tests/unit/quality/` using a small, purpose-built
   DataFrame that isolates the condition you are detecting.
5. Document the check in `docs/METHODOLOGY.md`.

A detector must be **deterministic** and must explain itself: the finding it
produces states what was observed, where, and by which method.

## Adding an anomaly detector

1. Create a module in `backend/app/ml/detectors/`.
2. Subclass `AnomalyDetector` and implement `fit_predict(features) -> AnomalyResult`.
3. Register it in `backend/app/ml/registry.py`.
4. Add a unit test with a synthetic dataset containing known anomalies.
5. Explain the method - and its limitations - in `docs/METHODOLOGY.md`.

Do not claim a model knows *why* a row is anomalous. Report the score, the
features that were used, and the values that stood out.

## Good first issues

- Add a `.parquet` or `.json` reader.
- Add a detector for mixed-type columns (numbers stored as text).
- Add a detector for leading/trailing whitespace in categorical values.
- Add a detector for near-duplicate rows (duplicates ignoring case/whitespace).
- Add per-column sparkline distributions to the dataset explorer.
- Add a Markdown report exporter alongside PDF and CSV.
- Improve empty and error states on any page.
- Expand the Playwright suite with a findings-triage journey.

Issues labelled `good first issue` on GitHub always have an acceptance
criteria section - if one does not, ask and we will add it.

## Reporting bugs and vulnerabilities

Bugs: open an issue using the bug template, and include the `request_id` from
the error message if the API returned one.

Security vulnerabilities: **do not open a public issue.** See
[SECURITY.md](SECURITY.md).
