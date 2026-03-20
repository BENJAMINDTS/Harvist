# CLAUDE.md — Guía de trabajo para Claude Code en Proyecto Scraping

## ⚠️ LEE ESTO ANTES DE HACER CUALQUIER COSA

Este archivo define las reglas estrictas de desarrollo para el proyecto Scraping.
Debes seguirlas SIN EXCEPCIÓN en cada tarea que realices.

---

## El Proyecto

**Scraper de Imágenes de Producto** es una aplicación web para la descarga masiva y
automatizada de imágenes de productos a partir de un CSV de inventario.
Busca imágenes en Bing Images mediante un patrón Productor/Consumidor, las valida,
redimensiona y las sirve al usuario como archivo ZIP descargable.

**Stack:**

- Backend → Python 3.11 + FastAPI + Celery + Redis
- Frontend → React 18 + TypeScript + Vite + Tailwind CSS
- Validación de entorno → Pydantic Settings v2
- Logging → loguru (JSON estructurado)
- Scraping → undetected-chromedriver + Selenium 4 + requests + Pillow

### Equipo

- **BenjaminDTS**
- **Carlitos6712**

### Credenciales / Accesos de desarrollo

- Swagger UI → `http://localhost:8000/api/docs`
- Redis → `localhost:6379` (sin contraseña en desarrollo)
- Frontend dev → `http://localhost:5173`

---

## 🌿 Reglas de Git — OBLIGATORIAS

### Antes de empezar cualquier tarea

```bash
git checkout main
git pull origin main
git checkout -b feat/nombre-descriptivo
```

### Nomenclatura de ramas

- `feat/descripcion`     → Nueva funcionalidad
- `fix/descripcion`      → Corrección de bug
- `refactor/descripcion` → Mejora sin cambio de comportamiento
- `docs/descripcion`     → Solo documentación
- `style/descripcion`    → Cambios visuales sin lógica
- `test/descripcion`     → Solo pruebas

### Commits — REGLA DE ORO

**Un commit por acción concreta.** NUNCA uses `git add .` para mezclar
cambios de módulos distintos en un solo commit.

#### Hazlo así

```bash
# Esquema Pydantic
git add api/v1/schemas/job.py
git commit -m "feat: add JobStatus and EstadoJob schemas"

# Endpoint
git add api/v1/endpoints/jobs.py
git commit -m "feat: implement POST /api/v1/jobs with CSV upload"

# Servicio
git add services/scraper/producer.py
git commit -m "feat: add configurable browser factory in producer"

# Worker
git add workers/tasks.py
git commit -m "feat: implement ejecutar_scraping Celery task"

# Componente frontend
git add frontend/src/components/CsvUploader.tsx
git commit -m "feat: create CsvUploader component with drag and drop"
```

#### Mensajes de commit — Conventional Commits

| Prefijo     | Cuándo usarlo                                 |
|-------------|-----------------------------------------------|
| `feat:`     | Nueva funcionalidad                           |
| `fix:`      | Corrección de error                           |
| `refactor:` | Refactorización sin cambio de comportamiento  |
| `docs:`     | Solo documentación o comentarios              |
| `style:`    | Cambios visuales / CSS sin lógica             |
| `test:`     | Añadir o modificar pruebas                    |
| `chore:`    | Tareas de mantenimiento (deps, config, CI)    |

### Al terminar un bloque completo

```bash
git push -u origin feat/nombre-rama
# → Crear Pull Request en GitHub hacia main
# → Avisar al compañero para revisión
# → Esperar Merge antes de empezar el siguiente bloque
```

### Después del Merge

```bash
git checkout main
git pull origin main
git branch -d feat/nombre-rama
```

---

## 🏗️ Arquitectura — Reglas de código

### Separación de responsabilidades — OBLIGATORIA

```
api/          → Capa HTTP: recibe requests, valida, delega. Sin lógica de negocio.
services/     → Lógica de negocio pura. Sin conocimiento de FastAPI ni HTTP.
workers/      → Integración Celery. Solo envuelve servicios en tareas async.
frontend/src/ → UI React. Solo consume la API REST y el WebSocket. Sin lógica de scraping.
```

**Regla de oro:** un módulo de `services/` NUNCA importa de `api/`.
Si necesitas compartir tipos, defínelos en `api/v1/schemas/` y los dos sentidos los importan.

### Documentación — pydoc / JSDoc

**Python** → docstrings en todas las clases, funciones y módulos:

```python
"""
Descripción breve del módulo.

:author: BenjaminDTS
:version: 1.x.x
"""

class MiServicio:
    """
    Descripción de la clase.

    :author: BenjaminDTS
    """

    def mi_metodo(self, param: str) -> bool:
        """
        Descripción del método.

        Args:
            param: descripción del parámetro.

        Returns:
            True si tuvo éxito, False si falló.

        Raises:
            ValueError: si param está vacío.
        """
```

- `@author` SOLO en la cabecera del módulo y de la clase, NUNCA en los métodos.
- Docstrings en formato Google Style (Args / Returns / Raises).

**TypeScript / React** → JSDoc en todos los componentes y hooks:

```typescript
/**
 * Componente de carga de CSV con drag & drop.
 * Valida el tipo MIME en el cliente antes de enviarlo.
 *
 * @author BenjaminDTS | Carlitos6712
 * @param onFileSelected - Callback que recibe el File seleccionado.
 */
export const CsvUploader: React.FC<CsvUploaderProps> = ({ onFileSelected }) => {
```

### Variables de entorno — OBLIGATORIO

- **NUNCA** hardcodear rutas, URLs, credenciales ni parámetros de scraping en el código.
- Siempre leer desde `Settings` (`api/core/config.py`).
- Si añades una variable nueva al `.env`, actualiza también `.env.example` en el mismo commit.

```python
# ✅ Correcto
from api.core.config import get_settings
settings = get_settings()
ruta = settings.directorio_salida

# ❌ Prohibido
ruta = "imagenes_descargadas"
```

### Navegador configurable — OBLIGATORIO

- La ruta al ejecutable del navegador **nunca** puede estar hardcodeada.
- El tipo de navegador se lee de `BROWSER_TYPE` (chrome | opera | edge | brave | chromium).
- La ruta al ejecutable se lee de `BROWSER_BINARY_PATH`.
- Si añades soporte a un navegador nuevo, añade su `_BrowserProfile` en
  `services/scraper/producer.py` y documenta su ruta en `.env.example`.

### Almacenamiento — OBLIGATORIO

- Las imágenes se guardan siempre a través de `LocalStorageService`
  (o la clase que devuelva `get_storage_service()`).
- **NUNCA** escribir rutas de archivo directamente en los endpoints ni en el pipeline.
- Para añadir almacenamiento en cloud (S3, Azure), crear una nueva clase en
  `services/storage_service.py` y registrarla en `get_storage_service()`.
  Los endpoints no deben cambiar.

### Respuestas de la API — Estructura estándar

Todas las respuestas JSON deben seguir este contrato:

```json
{
  "success": true,
  "data": { "...": "..." },
  "message": "Operación exitosa"
}
```

Usar siempre los schemas `JobResponse` de `api/v1/schemas/job.py`.

### Manejo de errores — OBLIGATORIO

- Nunca dejar un `except` vacío o con solo `pass`.
- Siempre loguear con `logger.error(..., exc_info=exc)`.
- Devolver al cliente un mensaje seguro (sin stack traces en producción).
- Los errores esperados (validación, not found) usan `HTTPException` con código correcto.

```python
# ✅ Correcto
except FileNotFoundError as exc:
    logger.error("CSV no encontrado", exc_info=exc)
    raise HTTPException(status_code=404, detail="El archivo no existe.") from exc

# ❌ Prohibido
except Exception:
    pass
```

### Logging — OBLIGATORIO

- **Prohibido `print()`** en cualquier módulo excepto en el bloque de arranque
  antes de que loguru esté inicializado.
- Usar siempre `from loguru import logger`.
- Respetar la jerarquía: `ERROR` → `WARN` → `INFO` → `DEBUG`.
- Nunca loguear passwords, tokens, paths completos de usuario ni datos personales.
- Los logs llevan siempre `extra={...}` con el contexto mínimo necesario:

```python
logger.info("Trabajo encolado", extra={"job_id": job_id, "modo": config.modo})
logger.error("Fallo al descargar imagen", exc_info=exc, extra={"url": url, "codigo": codigo})
```

### Paginación

- Ningún endpoint devuelve listas sin paginar que puedan crecer indefinidamente.
- Implementar `limit` / `offset` o cursores en todos los endpoints de listado.

### Versionado de la API

- Todos los endpoints bajo `/api/v1/`.
- Breaking changes → crear `/api/v2/` sin modificar `v1`.
- Deprecaciones → cabecera `Deprecation: true` en las respuestas durante al menos
  un ciclo de aviso antes de eliminar el endpoint.

---

## 🗺️ Estado del proyecto

### ✅ Completado

- Arquitectura general definida (ARQUITECTURA.md)
- Esquemas Pydantic: `JobStatus`, `JobCreate`, `SearchConfig`, `ModosBusqueda`
- `api/core/config.py` — Settings con validación al arranque
- `api/core/logging.py` — loguru con sink JSON + sink consola
- `api/main.py` — App factory, CORS, rate limiting, cabeceras de seguridad
- `api/v1/endpoints/jobs.py` — POST crear job · GET estado · WS progreso
- `api/v1/endpoints/files.py` — GET descarga ZIP · DELETE limpiar archivos
- `services/scraper/producer.py` — Fábrica de navegadores configurable (5 browsers)
- `services/scraper/pipeline.py` — Orquestador Productor/Consumidor con callback
- `services/storage_service.py` — LocalStorageService + get_storage_service()
- `workers/celery_app.py` — Instancia Celery configurada
- `workers/tasks.py` — Tarea `ejecutar_scraping`
- `.env.example` completo con todas las variables documentadas
- `pyproject.toml` con dependencias fijadas
- `.gitignore`

### 🚧 En progreso

- Bloque 1.1: `services/csv_parser.py` — Lectura, validación y normalización del CSV
- Bloque 1.2: `services/scraper/consumer.py` — Workers de descarga HTTP + validación Pillow

### 🔒 Pendiente

- Bloque 1.3: `api/v1/router.py` — Montar jobs + files en el router principal
- Bloque 2.1: Frontend — `CsvUploader.tsx` con drag & drop y validación de columnas
- Bloque 2.2: Frontend — `SearchConfig.tsx` con selector de modo (EAN / Nombre+Marca / Personalizado)
- Bloque 2.3: Frontend — `JobProgress.tsx` con barra de progreso en tiempo real (WebSocket)
- Bloque 2.4: Frontend — `useJobWebSocket.ts` hook con reconexión automática
- Bloque 2.5: Frontend — `api/client.ts` Axios con base URL `/api/v1/`
- Bloque 3.1: `openapi.yaml` — Contrato OpenAPI sincronizado con todos los endpoints
- Bloque 3.2: Tests unitarios — `services/csv_parser.py`, `_construir_query()`, `_sanitizar()`
- Bloque 3.3: Tests de integración — endpoints con `httpx.AsyncClient`
- Bloque 4.1: Soporte multi-motor de búsqueda (Google Images / DuckDuckGo)
- Bloque 4.2: Almacenamiento en cloud (S3 / Azure Blob)
- Bloque 4.3: Panel de historial de trabajos con filtros y paginación

### 🔭 Hoja de ruta (fases futuras ya planificadas)

> Estas fases **condicionan decisiones de arquitectura hoy**.
> Claude Code debe tenerlas en cuenta antes de diseñar cualquier módulo nuevo
> para no crear deuda técnica que las bloquee.

#### Fase 5 — Generación automática de descripciones (Grok API)

- Bloque 5.1: `services/ai/grok_client.py` — Cliente HTTP para la API de xAI/Grok
  con reintentos, timeout y rate limiting propio.
- Bloque 5.2: `services/ai/description_generator.py` — Servicio que recibe
  nombre + marca + categoría + imagen descargada y devuelve una descripción
  de producto lista para catálogo.
- Bloque 5.3: Integración en el pipeline — La generación de descripción se
  ejecuta como paso opcional **después** de la descarga de imagen, controlado
  por un flag `ENABLE_AI_DESCRIPTIONS=true` en `.env`.
- Bloque 5.4: Nuevo campo en `JobStatus` → `descripciones_generadas: int`
- Bloque 5.5: Exportación enriquecida — El ZIP incluirá un `descripciones.csv`
  con `codigo`, `nombre`, `descripcion_generada` además de las imágenes.
- Bloque 5.6: Frontend — Toggle "Generar descripciones con IA" en `SearchConfig.tsx`

#### Fase 6 — Scraping de información de marca

- Bloque 6.1: `services/scraper/brand_scraper.py` — Extrae información pública
  de la marca (web oficial, descripción, logo) a partir del nombre de marca
  del CSV. Sigue el mismo patrón Productor/Consumidor del scraper de imágenes.
- Bloque 6.2: `services/ai/brand_enricher.py` — Usa Grok para sintetizar la
  información scrapeada en una ficha de marca estructurada (JSON).
- Bloque 6.3: Exportación de fichas de marca — Nuevo endpoint
  `GET /api/v1/files/{job_id}/brands` que sirve `marcas.json` con las fichas.
- Bloque 6.4: Frontend — Sección "Marcas" en el panel de resultados.

#### Fase 7 — Extensiones por definir

Posibles líneas identificadas pero no comprometidas aún:

- Generación de textos SEO (meta title + meta description) por producto.
- Traducción automática de descripciones a varios idiomas.
- Integración directa con plataformas de e-commerce (Shopify, WooCommerce) vía API.
- Panel de revisión manual de descripciones generadas antes de exportar.

---

## 📁 Estructura de archivos

```
proyecto_scraping/
├── CLAUDE.md                         # ← Este archivo
├── ARQUITECTURA.md                   # Decisiones de diseño y código base
├── .env.example                      # Plantilla de variables (sí en git)
├── .env.development                  # Variables dev (NO en git)
├── .env.staging                      # Variables staging (NO en git)
├── .env.production                   # Variables prod (NO en git)
├── .gitignore
├── pyproject.toml                    # Dependencias Python (lockfile sí en git)
├── openapi.yaml                      # Contrato OpenAPI — actualizar con cada endpoint nuevo
│
├── api/
│   ├── __init__.py
│   ├── main.py                       # App factory
│   ├── core/
│   │   ├── config.py                 # Pydantic Settings — leer siempre via get_settings()
│   │   ├── logging.py                # Setup loguru — llamar en main.py únicamente
│   │   └── security.py              # CORS, rate limiting, cabeceras HTTP
│   └── v1/
│       ├── router.py                 # Monta jobs + files
│       ├── schemas/
│       │   └── job.py               # JobCreate, JobResponse, JobStatus, SearchConfig
│       └── endpoints/
│           ├── jobs.py              # /api/v1/jobs
│           └── files.py             # /api/v1/files
│
├── services/                         # Lógica de negocio — sin imports de api/
│   ├── csv_parser.py                # Lectura y validación del CSV
│   ├── storage_service.py           # LocalStorageService + factory
│   ├── scraper/
│   │   ├── pipeline.py              # Orquestador
│   │   ├── producer.py              # Selenium + fábrica de navegadores
│   │   ├── consumer.py             # ThreadPoolExecutor + Pillow
│   │   └── brand_scraper.py        # (Fase 6) Scraping de información de marca
│   └── ai/                          # (Fase 5-6) Capa de inteligencia artificial
│       ├── grok_client.py           # Cliente HTTP para xAI/Grok API
│       ├── description_generator.py # Genera descripciones de producto
│       └── brand_enricher.py        # Sintetiza fichas de marca en JSON
│
├── workers/
│   ├── celery_app.py
│   └── tasks.py
│
├── tests/
│   ├── unit/
│   │   ├── test_csv_parser.py
│   │   └── test_producer.py
│   └── integration/
│       └── test_jobs_endpoint.py
│
├── logs/                            # Git-ignored, generado en runtime
└── frontend/
    ├── package.json
    ├── package-lock.json            # Sí en git
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/
        │   └── client.ts
        ├── components/
        │   ├── CsvUploader.tsx
        │   ├── SearchConfig.tsx
        │   └── JobProgress.tsx
        └── hooks/
            └── useJobWebSocket.ts
```

---

## 🖥️ Comandos útiles

```bash
# ── Instalación inicial ─────────────────────────────────
pip install -e ".[dev]"                         # Instalar dependencias Python
cd frontend && npm install                       # Instalar dependencias frontend

# ── Arrancar servicios (orden importante) ───────────────
docker run -d -p 6379:6379 redis:7-alpine       # 1. Redis
celery -A workers.celery_app worker \
  --loglevel=info                               # 2. Celery Worker
uvicorn api.main:app \
  --reload --host 0.0.0.0 --port 8000          # 3. FastAPI
cd frontend && npm run dev                       # 4. Vite (frontend)

# ── Comprobación de arranque ────────────────────────────
curl http://localhost:8000/api/docs              # Swagger UI (solo en development)
curl http://localhost:8000/api/v1/jobs           # Health check endpoint

# ── Tests ───────────────────────────────────────────────
pytest                                           # Todos los tests
pytest tests/unit/                              # Solo unitarios
pytest tests/integration/ -v                    # Solo integración con detalle
pytest --cov=api --cov=services                 # Con cobertura

# ── Calidad de código ───────────────────────────────────
pip-audit                                        # Auditoría de vulnerabilidades
ruff check .                                     # Linting Python (si está instalado)

# ── Frontend ────────────────────────────────────────────
cd frontend && npm run build                     # Build producción
cd frontend && npm run type-check                # Verificar tipos TypeScript
```

---

## 🔐 Seguridad — Recordatorios rápidos

| Regla | Detalle |
|-------|---------|
| Secrets en `.env` | Nunca en el código ni en Git |
| CORS en producción | Lista blanca explícita en `ALLOWED_ORIGINS`, nunca `*` |
| Rate limiting | Ya configurado en `main.py` vía `slowapi` |
| Cabeceras HTTP | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection` ya en middleware |
| HTTPS | Obligatorio en staging y producción (configurar en el proxy inverso) |
| Datos sensibles en logs | Nunca loguear passwords, tokens ni paths con datos de usuario |
| Validación CSV | Validar tipo MIME + contenido antes de procesar, en `csv_parser.py` |
| Grok API Key | Cuando se implemente la Fase 5, la clave se lee de `GROK_API_KEY` en `.env`. Nunca hardcodeada. El cliente `grok_client.py` debe tratarla como secreto y nunca incluirla en logs ni en respuestas de error. |

---

## ✅ Checklist antes de hacer un PR

- [ ] La rama parte de `main` actualizado
- [ ] Un commit por cada acción concreta (schema, endpoint, servicio, worker, componente, hook, test)
- [ ] Todos los módulos, clases y funciones tienen docstring / JSDoc con Args/Returns/Raises
- [ ] `@author` solo en cabecera de módulo y clase, nunca en métodos individuales
- [ ] Sin `print()` en Python — usar siempre `logger.*`
- [ ] Sin valores hardcodeados — todo via `get_settings()` (Python) o `api/client.ts` (TS)
- [ ] Ningún `except` vacío o con `pass` solo
- [ ] Sin `any` en TypeScript — tipos explícitos en todos los props y retornos
- [ ] Si se añadió variable de entorno → actualizado `.env.example` en el mismo commit
- [ ] Si se añadió/modificó endpoint → actualizado `openapi.yaml` en el mismo commit
- [ ] Tests escritos para la lógica de negocio nueva o modificada
- [ ] `npm run type-check` pasa sin errores (si hay cambios en frontend)
- [ ] `npm run build` ejecutado sin errores (si hay cambios en frontend)
- [ ] La aplicación arranca sin errores en local
- [ ] No hay archivos `.env` reales pusheados al repositorio
- [ ] `package-lock.json` / `pyproject.toml` actualizados si se modificaron dependencias
