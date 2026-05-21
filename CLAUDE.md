# CLAUDE.md — Guía de trabajo para Claude Code en Harvist

## ⚠️ LEE ESTO ANTES DE HACER CUALQUIER COSA

Este archivo define las reglas estrictas de desarrollo para el proyecto Harvist.
Debes seguirlas SIN EXCEPCIÓN en cada tarea que realices.

---

## El Proyecto

**Harvist** es una plataforma web para enriquecimiento masivo de catálogos de producto
y gestión integrada de ERPs y CMS. Sus cuatro pilares son:

1. **Scraping** — Descarga masiva de imágenes de producto desde CSV via Selenium + ThreadPool
2. **IA** — Generación de descripciones SEO y textos de producto con Groq (llama-3.3-70b)
3. **Marcas** — Resolución EAN → marca via cascada 8 niveles (Amazon, Open*Facts, GS1…)
4. **Integraciones** — Gestión completa de Dolibarr, Odoo y WordPress/WooCommerce via API

**Stack:**

- Backend  → Python 3.11 + FastAPI + Celery + Redis
- Frontend → React 18 + TypeScript + Vite + Tailwind CSS
- Scraping → undetected-chromedriver + Selenium 4 + Pillow
- IA       → Groq API (llama-3.3-70b-versatile)
- Testing  → pytest · 130+ tests

### Equipo

- **BenjaminDTS**
- **Carlos Vico**

### Credenciales / Accesos de desarrollo

- Swagger UI → `http://localhost:8000/api/docs`
- Redis      → `localhost:6379` (sin contraseña en desarrollo)
- Frontend   → `http://localhost:5173`

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

```bash
git add api/v1/schemas/job.py
git commit -m "feat: add JobStatus and EstadoJob schemas"

git add api/v1/endpoints/jobs.py
git commit -m "feat: implement POST /api/v1/jobs with CSV upload"

git add services/scraper/producer.py
git commit -m "feat: add configurable browser factory in producer"

git add workers/tasks.py
git commit -m "feat: implement ejecutar_scraping Celery task"

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
# → Pull Request hacia main
# → Avisar al compañero para revisión
# → Esperar Merge antes del siguiente bloque
```

### Después del Merge

```bash
git checkout main && git pull origin main
git branch -d feat/nombre-rama
```

---

## 🏗️ Arquitectura — Reglas de código

### Separación de responsabilidades — OBLIGATORIA

```
api/          → Capa HTTP: recibe, valida, delega. CERO lógica de negocio.
services/     → Lógica pura. SIN imports de api/ ni de workers/.
workers/      → Solo envuelve servicios en tareas Celery async.
frontend/src/ → Solo consume API REST y WebSocket. Sin lógica de negocio.
```

**Regla de oro:** `services/` nunca importa de `api/`. Los tipos compartidos
se definen en `api/v1/schemas/` y ambas capas los importan desde ahí.

### Documentación — pydoc / JSDoc

**Python** → docstrings en módulos, clases y funciones:

```python
"""
Descripción del módulo.

:author: BenjaminDTS
:version: x.x.x
"""

class MiServicio:
    """
    Descripción.

    :author: BenjaminDTS
    """

    def mi_metodo(self, param: str) -> bool:
        """
        Descripción.

        Args:
            param: descripción.

        Returns:
            True si éxito.

        Raises:
            ValueError: si param vacío.
        """
```

- `@author` SOLO en cabecera de módulo y clase. NUNCA en métodos.
- Docstrings en formato Google Style (Args / Returns / Raises).

**TypeScript / React** → JSDoc en componentes y hooks:

```typescript
/**
 * Descripción del componente.
 *
 * @author BenjaminDTS | Carlos Vico
 * @param props - Descripción.
 */
```

### Variables de entorno — OBLIGATORIO

```python
# ✅ Correcto
from api.core.config import get_settings
settings = get_settings()

# ❌ Prohibido
ruta = "imagenes_descargadas"
GROQ_API_KEY = "gsk_..."
```

Si añades variable nueva → actualiza `.env.example` en el **mismo commit**.

### Manejo de errores — OBLIGATORIO

```python
# ✅ Correcto
except FileNotFoundError as exc:
    logger.error("CSV no encontrado", exc_info=exc, extra={"job_id": job_id})
    raise HTTPException(status_code=404, detail="El archivo no existe.") from exc

# ❌ Prohibido
except Exception:
    pass
```

### Logging — OBLIGATORIO

- **Prohibido `print()`** en cualquier módulo.
- Usar siempre `from loguru import logger`.
- Respetar jerarquía: `ERROR` → `WARN` → `INFO` → `DEBUG`.
- **Nunca loguear** keys de API, tokens, passwords ni datos personales.

```python
logger.info("Job encolado", extra={"job_id": job_id, "tipo": config.tipo})
logger.error("Pipeline falló", exc_info=exc, extra={"job_id": job_id})
```

### Respuestas API — Estructura estándar

```json
{ "success": true, "data": { "...": "..." }, "message": "Operación exitosa" }
```

### Almacenamiento — Siempre via factory

```python
# ✅ Correcto
storage = get_storage_service(settings)

# ❌ Prohibido
open("imagenes_descargadas/producto.jpg", "wb")
```

### Cascada EAN → Marca — Orden estricto

El orden de `brand_scraper.py` NO debe modificarse sin documentar el motivo:

```
1. Validación checksum (GS1 Módulo 10)
2. Caché GS1 en memoria (brand_cache.json)
3. Amazon.es
4. Open Pet Food Facts
5. Open Food Facts
6. UPCItemDb
7. Google Dorking
8. Bing Search
9. not_found
```

La escritura en `brand_cache.json` es independiente de la resolución.
Si la validación de marcas (Fase 7.4) está activa, NO se escribe hasta confirmación del usuario.

---

## 🗺️ Estado del proyecto

### ✅ Completado

**Core Harvist**
- Core scraping imágenes (Productor/Consumidor, Selenium, ThreadPool, Pillow)
- Fábrica de navegadores configurable (5 tipos)
- API REST completa + WebSocket progreso en tiempo real
- Schemas Pydantic: JobStatus, JobCreate, SearchConfig, ModosBusqueda, TipoJob
- `api/core/config.py` — Settings con validación al arranque (Pydantic v2)
- `api/core/logging.py` — loguru JSON estructurado
- `api/main.py` — App factory, CORS, rate limiting, cabeceras de seguridad
- Endpoints: POST/GET jobs · WS progreso · GET/DELETE files · GET historial paginado
- `services/storage_service.py` — LocalStorageService + S3 + Azure + factory
- `services/csv_parser.py` — Lectura, validación y normalización
- `services/scraper/pipeline.py` — Orquestador completo con callbacks Redis
- `services/scraper/producer.py` — Selenium + fábrica navegadores
- `services/scraper/consumer.py` — ThreadPoolExecutor + validación Pillow
- `services/scraper/brand_scraper.py` — Cascada 8 niveles EAN → marca (httpx, sin Selenium)
- `services/ai/groq_client.py` — Cliente Groq con reintentos + backoff exponencial
- `services/ai/description_generator.py` + `description_pipeline.py` — Descripciones SEO batch
- `workers/celery_app.py` + `workers/tasks.py` — Celery + Redis persistencia
- Frontend: CsvUploader · SearchConfig · JobProgress · JobHistory · App state machine
- `frontend/src/api/client.ts` — Axios + WebSocket builder
- `frontend/src/hooks/useJobWebSocket.ts` — Reconexión automática backoff
- **Dashboard principal** — `DashboardHome.tsx` con 4 módulos: Harvist, Dolibarr, Odoo, WordPress
- **Navegación contextual** — `Breadcrumb.tsx` + reorganización `App.tsx` para routing modular
- Historial de jobs con paginación (sorted set Redis) — accesible desde cualquier módulo
- Recuperación de jobs perdidos por crash (marcados FALLIDO al arrancar)
- 130+ tests Python (unitarios + integración) · 29 tests TypeScript (Vitest)
- `.env.example` completo · `.gitignore` · `LICENSE` · `pyproject.toml`

**Fase 6.4 — Panel de marcas** ✅
- `BrandsPanel.tsx` — tabla código · ean · brand_name · manufacturer · source · confidence
- Filtros por source y confidence con badges de color (high/medium/low)
- Botón "Descargar marcas.csv" → `GET /api/v1/files/{job_id}/brands`

**Fase 7.1 — Textos SEO (Groq)** ✅
- `TipoJob.SEO` en schema
- `services/ai/seo_pipeline.py` — meta_title (≤60) + meta_description (≤160) por producto
- Endpoint `GET /api/v1/files/{job_id}/seo` → `seo.csv`

**Fase 7.2 — Traducción automática (Groq)** ✅
- `services/ai/translation_pipeline.py` — ES · EN · FR · DE · IT · PT
- Selector multi-idioma en `SearchConfig.tsx`
- Endpoint `GET /api/v1/files/{job_id}/translations/{lang}`

**Fase 7.3 — Panel de revisión manual de descripciones** ✅
- `ReviewPanel.tsx` — tabla editable: aprobar / rechazar / editar por producto
- Estado persistente en Redis: `job:{job_id}:review:{codigo}`
- Endpoint `PATCH /api/v1/jobs/{job_id}/descriptions/{codigo}`

**Fase 7.4 — Validación de marcas** ✅
- `brand_scraper.py` separación resolución/escritura caché con `write_cache: bool`
- Estado `EstadoJob.PENDIENTE_VALIDACION_MARCAS`
- Endpoint `POST /api/v1/jobs/{job_id}/brands/validate`
- `BrandValidationPanel.tsx` — revisión fila a fila, confirmación → escribe en brand_cache.json

**Fase 7.5 — Selección visual de fotos** ✅
- `consumer.py` descarga todas las candidatas en modo validación (`{codigo}_candidate_{n}.jpg`)
- Estado `EstadoJob.PENDIENTE_SELECCION_FOTOS`
- Endpoints `GET /jobs/{job_id}/photos` · `POST /jobs/{job_id}/photos/confirm`
- `PhotoSelectionPanel.tsx` — grid thumbnails por producto, confirmación genera ZIP
- Celery beat limpia candidates/ huérfanos cada hora

**Fase 8 — Integración Dolibarr** ✅
- `services/integrations/dolibarr/` — client · products · categories · thirdparties · orders · invoices · stocks · extrafields · extrafields_db · brands
- Endpoints `/api/v1/dolibarr/` completos
- Frontend: `DolibarrPanel` · `DolibarrProducts` · `DolibarrCategories` · `DolibarrBrands` · `DolibarrThirdparties` · `DolibarrOrders` · `DolibarrInvoices` · `DolibarrStocks` · `DolibarrExtraFields` · `DolibarrConfig`
- Sincronización bidireccional WP ↔ Dolibarr (por producto y catálogo completo)

**Fase 9 — Integración Odoo** ✅
- `services/integrations/odoo/` — client · products · categories · partners · purchases · sales · inventory · invoices · product_properties · brands + categorías eCommerce (`product.public.category`)
- Endpoints `/api/v1/odoo/` completos
- Frontend: `OdooPanel` · `OdooProducts` · `OdooCategories` · `OdooBrands` · `OdooEcommerceCategories` · `OdooPartners` · `OdooPurchases` · `OdooSales` · `OdooInventory` · `OdooInvoices` · `OdooCamposExtra` · `OdooProductProperties` · `OdooCsvImport` · `OdooConfig`

**Fase 10 — Integración WordPress / WooCommerce** ✅
- `services/integrations/wordpress/` — client · products · categories · brands (dual-backend: nativo + atributo pa_) · orders · customers · media · database
- Endpoints `/api/v1/wordpress/` completos
- Frontend: `WordPressPanel` · `WordPressProducts` · `WordPressCategories` · `WordPressBrands` · `WordPressOrders` · `WordPressCustomers` · `WordPressMedia` · `WordPressDatabase` · `WordPressConfig`
- Sincronización bidireccional WP ↔ Dolibarr (por producto y catálogo completo)

### 🔒 Pendiente

No hay fases pendientes en la hoja de ruta original. El proyecto está feature-complete.
Próximas mejoras serán definidas por el equipo según necesidades de producto.

---

### 🔗 Flujo integrado completo

```
CSV de inventario
      ↓
[Harvist — Job de enriquecimiento]
      ↓
  Imágenes descargadas (todas las candidatas si validación ON)
    ↓ ── si foto-validación ON ──────────────────────────────
  [PhotoSelectionPanel]   ← IMPLEMENTADO ✅
    usuario elige foto definitiva por producto
    resto eliminadas del disco
    ↓ ─────────────────────────────────────────────────────
  Descripciones SEO generadas (Groq)
    ↓ ── si revisión ON ─────────────────────────────────────
  [ReviewPanel]  usuario aprueba/edita descripciones   ← IMPLEMENTADO ✅
    ↓ ─────────────────────────────────────────────────────
  Marcas resueltas (cascada 8 niveles)
    ↓ ── si marca-validación ON ─────────────────────────────
  [BrandValidationPanel]   ← IMPLEMENTADO ✅
    usuario acepta marcas → se escriben en brand_cache.json
    ↓ ─────────────────────────────────────────────────────
[ZIP final + CSVs listos para descarga]
      ↓
[Acción "Exportar a plataforma"]
      ↓
  ┌───────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
  │  Dolibarr  ✅     │   │    Odoo  ✅           │   │ WordPress/WooComm ✅ │
  │  Productos        │   │  Productos            │   │  Productos           │
  │  Categorías       │   │  Categorías           │   │  + Imágenes          │
  │  Marcas           │   │  Categorías eComm     │   │  + Descripciones     │
  │  Proveedores      │   │  Marcas               │   │  Marcas (dual-back)  │
  │  Pedidos          │   │  Partners             │   │  Pedidos             │
  │  Facturas         │   │  Compras / Ventas     │   │  Clientes            │
  │  Stock            │   │  Inventario           │   │  Base de datos       │
  │  ExtraFields      │   │  Facturas             │   │  Config WC           │
  │  ↔ sync WP       │   │  CamposExtra          │   │  ↔ sync Dolibarr    │
  └───────────────────┘   └──────────────────────┘   └──────────────────────┘
```

---

## 📁 Estructura de archivos

```
harvist/
├── CLAUDE.md
├── .env.example
├── .env.development / .env.staging / .env.production   # NO en git
├── .gitignore
├── pyproject.toml
├── openapi.yaml
│
├── api/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── security.py
│   └── v1/
│       ├── router.py
│       ├── schemas/
│       │   ├── job.py              # JobCreate · JobStatus · TipoJob · EstadoJob
│       │   └── integrations.py
│       └── endpoints/
│           ├── jobs.py
│           ├── files.py
│           ├── history.py
│           ├── dolibarr.py
│           ├── odoo.py
│           └── wordpress.py
│
├── services/
│   ├── csv_parser.py
│   ├── storage_service.py
│   ├── scraper/
│   │   ├── pipeline.py
│   │   ├── producer.py
│   │   ├── consumer.py
│   │   └── brand_scraper.py
│   ├── ai/
│   │   ├── groq_client.py
│   │   ├── claude_client.py
│   │   ├── description_generator.py
│   │   ├── description_pipeline.py
│   │   ├── seo_pipeline.py         # Fase 7.1
│   │   └── translation_pipeline.py # Fase 7.2
│   └── integrations/
│       ├── base.py
│       ├── dolibarr/               # client · products · categories · thirdparties
│       │                           # orders · invoices · stocks · extrafields · brands
│       ├── odoo/                   # client · products · categories · partners
│       │                           # purchases · sales · inventory · invoices
│       │                           # product_properties · brands
│       └── wordpress/              # client · products · categories · brands
│                                   # orders · customers · media · database
│
├── workers/
│   ├── celery_app.py
│   └── tasks.py                    # ejecutar_scraping · importar_productos_dolibarr
│                                   # importar_productos_wordpress · cleanup_stale_candidates
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── scripts/
│   └── setup_gs1_db.py
│
├── data/                           # Git-ignored
│   ├── brand_cache.json            # Batería local de prefijos GS1 conocidos
│   └── gs1_prefixes.db
│
├── logs/                           # Git-ignored
│
└── frontend/
    ├── package.json
    ├── package-lock.json
    ├── tsconfig.json
    └── src/
        ├── App.tsx
        ├── api/client.ts
        ├── components/
        │   ├── CsvUploader.tsx
        │   ├── SearchConfig.tsx
        │   ├── JobProgress.tsx
        │   ├── JobHistory.tsx
        │   ├── BrandsPanel.tsx
        │   ├── BrandValidationPanel.tsx   # Fase 7.4
        │   ├── PhotoSelectionPanel.tsx    # Fase 7.5
        │   ├── ReviewPanel.tsx
        │   ├── DashboardHome.tsx
        │   ├── HomeScreen.tsx
        │   ├── navigation/Breadcrumb.tsx
        │   ├── dolibarr/                  # DolibarrPanel · Products · Categories · Brands
        │   │                              # Thirdparties · Orders · Invoices · Stocks
        │   │                              # ExtraFields · Config
        │   ├── odoo/                      # OdooPanel · Products · Categories · Brands
        │   │                              # EcommerceCategories · Partners · Purchases
        │   │                              # Sales · Inventory · Invoices · CamposExtra
        │   │                              # ProductProperties · CsvImport · Config
        │   └── wordpress/                 # WordPressPanel · Products · Categories · Brands
        │                                  # Orders · Customers · Media · Database · Config
        └── hooks/
            └── useJobWebSocket.ts
```

---

## 🖥️ Comandos útiles

```bash
# ── Instalación ──────────────────────────────────────────
pip install -e ".[dev]"
cd frontend && npm install

# ── Arrancar servicios (orden importante) ────────────────
docker compose up -d                                          # Redis
celery -A workers.celery_app worker --loglevel=info --pool=solo   # Windows: --pool=solo
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
cd frontend && npm run dev

# ── Tests ─────────────────────────────────────────────────
pytest
pytest tests/unit/
pytest tests/integration/ -v
pytest --cov=api --cov=services

# ── Tests TypeScript (Vitest) ─────────────────────────────
cd frontend && npm test                 # run once
cd frontend && npm run test:watch       # watch mode
cd frontend && npm run test:coverage    # con cobertura

# ── Calidad ───────────────────────────────────────────────
pip-audit
ruff check .
cd frontend && npm run type-check
cd frontend && npm run build
```

---

## 🔐 Seguridad — Recordatorios rápidos

| Regla | Detalle |
|-------|---------|
| Secrets en `.env` | Nunca en el código ni en Git |
| CORS en producción | Lista blanca en `ALLOWED_ORIGINS`, nunca `*` |
| Rate limiting | `slowapi` en `main.py` |
| Cabeceras HTTP | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection` |
| HTTPS | Obligatorio en staging y producción |
| Logs | Nunca loguear passwords, tokens ni datos personales |
| Validación CSV | Tipo MIME + contenido antes de procesar |
| `GROQ_API_KEY` | Nunca en logs ni respuestas de error |
| `DOLIBARR_API_KEY` | Cabecera `DOLAPIKEY`, nunca hardcodeada |
| `ODOO_PASSWORD` / `ODOO_API_KEY` | Nunca logueados, enmascarar en trazas |
| `WP_CONSUMER_KEY/SECRET`, `WP_APP_PASSWORD` | Nunca en logs |
| `OFF_USER_AGENT` | No es secret pero nunca hardcodeado |
| `BRAND_CACHE_PATH` | Fichero local excluido del repo via `data/` en `.gitignore` |
| `GS1_DB_PATH` | SQLite local excluida del repo |
| `CANDIDATES_TTL_HOURS` | Imágenes candidatas se limpian automáticamente |

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
