## Descripción
<!-- Describe qué hace este PR de forma breve -->

Fixes #<!-- issue number -->

## Cambios
<!-- Checklist de cambios principales -->
- [ ] Backend: [qué cambió]
- [ ] Frontend: [qué cambió]
- [ ] Tests: [qué se agregó]
- [ ] Documentación: [qué se actualizó]
- [ ] Dependencias: [qué se agregó/actualizó]

## Testing
<!-- Cómo verificar que funciona -->
- [ ] Tests locales pasan: `pytest`
- [ ] Tipos verificados: `npm run type-check` (si hay TS)
- [ ] Build completa: `npm run build` (si hay frontend)
- [ ] Funcionalidad probada en http://localhost:8000/api/docs (backend)
- [ ] Funcionalidad probada en http://localhost:5173 (frontend)

## Checklist Harvist
<!-- Obligatorio para todos los PRs -->
- [ ] Commits atómicos (uno por acción concreta)
- [ ] Mensajes Conventional Commits (feat:, fix:, docs:, etc)
- [ ] Docstrings/JSDoc en todas las funciones/componentes
- [ ] `@author` SOLO en cabecera de módulo/clase, nunca en métodos
- [ ] Sin `print()` en Python — usar `logger.*` de loguru
- [ ] Variables de entorno via `get_settings()` (Python) o env (TS)
- [ ] Sin valores hardcodeados (rutas, URLs, credenciales)
- [ ] Ningún `except` vacío o con solo `pass`
- [ ] Sin `any` en TypeScript — tipos explícitos
- [ ] `.env` nuevo agregado? → actualizar `.env.example` en mismo commit
- [ ] Endpoint nuevo? → actualizar `openapi.yaml`
- [ ] Dependencia nueva? → lockfile (`package-lock.json` / `pyproject.toml`) committeado

## Capturas / Demos
<!-- Si es cambio visual, agregar capturas -->

## Notas
<!-- Notas adicionales, decisiones, trade-offs, etc -->

---

