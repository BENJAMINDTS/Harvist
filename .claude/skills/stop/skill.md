---
name: stop
description: Stop all Harvist services (Redis, Celery, FastAPI, Vite). Project-local skill.
---

Stop all Harvist services gracefully in reverse order.

## Sequence

**Step 1 — Kill Vite (frontend)**
```bash
pkill -f "npm run dev" || true
sleep 1
```

**Step 2 — Kill FastAPI (uvicorn)**
```bash
pkill -f "uvicorn api.main" || true
sleep 1
```

**Step 3 — Kill Celery (worker)**
```bash
pkill -f "celery.*worker" || true
sleep 2
```

**Step 4 — Stop Redis (Docker Compose)**
```bash
cd C:\Users\Usuario\Desktop\Repositorios\Harvist && docker compose down
```

Verify stopped:
```bash
docker compose ps
```

## Force Kill (if needed)

If processes stuck, force kill:
```bash
pkill -9 -f "npm run dev" || true
pkill -9 -f "uvicorn" || true
pkill -9 -f "celery" || true
sleep 1
```

## Report Status

After all steps:

| Service  | Status     |
|----------|-----------|
| Vite     | ✓ Stopped |
| FastAPI  | ✓ Stopped |
| Celery   | ✓ Stopped |
| Redis    | ✓ Stopped |

## Notes

- Graceful shutdown via pkill
- Docker compose down removes containers
- Ports liberated for next launch
- Redis data persisted in volume (if using docker-compose)
