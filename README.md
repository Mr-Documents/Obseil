<div align="center">

# Obseil

**Uncover what's hidden in your data.**

AI-powered data quality intelligence for modern teams.

[![CI](https://github.com/Obseil/Obseil/actions/workflows/ci.yml/badge.svg)](https://github.com/Obseil/Obseil/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-4C5BD4.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6.svg)](https://www.typescriptlang.org/)

</div>

---

## What is Obseil?

Upload a CSV or XLSX file and Obseil answers one question:

> **Can I trust this dataset?**

It profiles the data, runs a suite of deterministic quality detectors, runs an
unsupervised anomaly model over the numeric feature space, turns everything it
finds into individually reviewable **findings**, and rolls those findings up
into an explainable **0–100 quality score**.

Every number it shows you can be traced back to the rule or the statistic that
produced it.

## Status

🚧 **Under active development.** See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
for the architecture and the phase-by-phase delivery plan.

| Phase | Scope | Status |
| ----- | ----- | ------ |
| 1 | Repository, backend & frontend skeleton, Docker, CI | ✅ |
| 2 | Authentication, projects | ✅ |
| 3 | Dataset upload, profiling engine | ✅ |
| 4 | Quality detection engine | ✅ |
| 5 | Isolation Forest anomaly detection, quality score | ✅ |
| 6 | Dashboard, findings, dataset explorer | ✅ |
| 7 | Analysis history and comparison | ✅ |
| 8 | Report export (PDF / CSV) | ✅ |
| 9 | Testing expansion, E2E, security & performance review | ⏳ |
| 10 | UI/UX polish, documentation, open-source setup | ⏳ |

## Tech stack

| Layer | Choice |
| ----- | ------ |
| Frontend | React 18, TypeScript (strict), Vite, Tailwind CSS v4, Recharts, React Router, TanStack Query |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| Data / ML | pandas, NumPy, scikit-learn (Isolation Forest) |
| Database | PostgreSQL 16 |
| Reports | ReportLab (PDF) |
| Testing | pytest, Vitest, React Testing Library, Playwright |
| Tooling | Ruff, Black, mypy, ESLint, Prettier, Docker, GitHub Actions |

## Quick start

### With Docker (recommended)

```bash
git clone https://github.com/Obseil/Obseil.git
cd Obseil
cp .env.example .env          # then edit OBSEIL_SECRET_KEY
docker compose up --build
```

| Service | URL |
| ------- | --- |
| Web | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### Without Docker

**Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

A local PostgreSQL instance is required; the connection string comes from
`OBSEIL_DATABASE_URL`. Start one quickly with `docker compose up db`.

## Environment variables

Every setting is documented in [`.env.example`](.env.example). Nothing is
hardcoded, and the application refuses to boot in `production` with a default
`OBSEIL_SECRET_KEY`.

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Testing

```bash
# Backend — unit + API tests, no services required
cd backend && pytest

# Backend — lint, format and types
ruff check . && black --check . && mypy app

# Frontend — unit and component tests
cd frontend && npm test

# Frontend — lint, format and types
npm run lint && npm run format:check && npm run typecheck
```

## Repository layout

```
.
├── backend/            FastAPI service
│   ├── app/
│   │   ├── api/        HTTP routes (thin — no business logic)
│   │   ├── core/       config, logging, errors, security
│   │   ├── db/         engine, session, declarative base
│   │   ├── models/     SQLAlchemy models
│   │   ├── schemas/    Pydantic request/response contracts
│   │   ├── services/   business logic
│   │   ├── profiling/  dataset profiling engine
│   │   ├── quality/    deterministic quality detectors
│   │   ├── ml/         anomaly detection
│   │   ├── reports/    PDF / CSV export
│   │   └── storage/    pluggable file storage
│   ├── alembic/        migrations
│   └── tests/
├── frontend/           React client
│   └── src/{components,pages,layouts,hooks,services,types,utils}
├── data/samples/       purpose-built test datasets
├── docs/               architecture and methodology
├── e2e/                Playwright end-to-end tests
└── docker-compose.yml
```

## Contributing

Obseil is built to be extended — new quality detectors, new anomaly detectors,
new file formats, new report formats. Start with
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
