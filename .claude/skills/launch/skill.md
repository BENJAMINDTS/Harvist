---
name: launch
description: Launch all Harvist project services (Redis, Celery, FastAPI, Vite). Project-local skill.
---

Launch all Harvist services in order. Use Bash tool for each step sequentially.

## Sequence

**Step 1 — Redis (Docker Compose)**
```bash
docker compose up -d
```
Wait for healthy. Verify with:
```bash
docker compose ps
```

**Step 2 — Celery worker (background)**
```bash
celery -A workers.celery_app worker --loglevel=info --pool=solo
```
Run in background (`run_in_background: true`). Working dir: project root.

**Step 3 — FastAPI / uvicorn (background)**
```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```
Run in background. Working dir: project root.

**Step 4 — Vite dev server (background)**
```bash
cd frontend && npm run dev
```
Run in background. Working dir: `frontend/`.

## After all services started

Report status table:

| Service  | URL / Port                        | Status  |
|----------|-----------------------------------|---------|
| Redis    | localhost:6379                    | ✓       |
| Celery   | (background worker)               | ✓       |
| FastAPI  | http://localhost:8000/api/docs    | ✓       |
| Frontend | http://localhost:5173             | ✓       |

## Error handling

- If `docker compose up -d` fails → check Docker is running, report error exact.
- If Celery fails → check Redis is healthy first (`docker compose ps`).
- If uvicorn fails → check `.env.development` exists and has required vars.
- If Vite fails → check `frontend/node_modules` exists; suggest `cd frontend && npm install`.

## Notes

- Windows: Celery needs `--pool=solo` (no fork support).
- All services use `.env.development` via Pydantic Settings at startup.
- Swagger UI only available in `development` environment.
- Do NOT launch if already running — check first with `docker compose ps` and ask user.
