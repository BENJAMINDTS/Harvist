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
- `services/ai/description_generator.py` — Descripciones SEO batch (corta + larga + keywords + meta)
- `workers/celery_app.py` + `workers/tasks.py` — Celery + Redis persistencia
- Frontend: CsvUploader · SearchConfig · JobProgress · JobHistory · App state machine
- `frontend/src/api/client.ts` — Axios + WebSocket builder
- `frontend/src/hooks/useJobWebSocket.ts` — Reconexión automática backoff
- Historial de jobs con paginación (sorted set Redis)
- Recuperación de jobs perdidos por crash (marcados FALLIDO al arrancar)
- 130+ tests (unitarios + integración)
- `.env.example` completo · `.gitignore` · `LICENSE` · `pyproject.toml`

### 🔒 Pendiente

#### Fase 6.4 — Frontend panel de marcas

- `frontend/src/components/BrandsPanel.tsx`
- Tabla: código · ean · brand_name · manufacturer · source · confidence
- Filtros por `source` y `confidence` con badges de color
  (high=green-500, medium=yellow-500, low=red-500)
- Botón "Descargar marcas.csv" → `GET /api/v1/files/{job_id}/brands`

#### Fase 7.1 — Textos SEO (Groq)

- `TipoJob.SEO` en schema o flag en job existente
- Prompt SEO → `meta_title` (≤60 chars) + `meta_description` (≤160 chars) por producto
- Endpoint `GET /api/v1/files/{job_id}/seo` → `seo.csv`

#### Fase 7.2 — Traducción automática (Groq)

- Idiomas soportados: ES · EN · FR · DE · IT · PT
- Selector multi-idioma en `SearchConfig.tsx`
- Output: `descripciones_en.csv`, `descripciones_fr.csv`…
- Endpoint `GET /api/v1/files/{job_id}/translations/{lang}`

#### Fase 7.3 — Panel de revisión manual de descripciones

- Tabla editable: aprobar / rechazar / editar por producto
- Estado persistente en Redis: `job:{job_id}:review:{codigo}`
- Solo exporta descripciones aprobadas
- Endpoint `PATCH /api/v1/jobs/{job_id}/descriptions/{codigo}`

---

#### Fase 7.4 — Validación de marcas antes de añadir a batería local ⭐
>
> Esta fase se implementa ANTES de las integraciones ERP/CMS.

**Por qué es necesaria:** el `brand_scraper.py` aprende automáticamente — cuando
resuelve un EAN nuevo, registra su prefijo (7 dígitos) en `brand_cache.json` para
acelerar jobs futuros. Sin validación, una marca mal identificada contamina la batería
para siempre. Esta fase añade una pantalla de revisión **opcional** antes de esa escritura.

**Comportamiento según modo:**

```
VALIDACIÓN ACTIVADA (toggle en SearchConfig al crear el job)
  Scraping de marcas completa
    ↓
  Estado job: PENDIENTE_VALIDACION_MARCAS
    ↓
  Usuario abre BrandValidationPanel (aparece automáticamente)
    ↓
  Revisa cada marca nueva: ean · brand_name editable · source · confidence
    ↓
  Acepta / Rechaza / Edita nombre de marca por fila
    ↓
  Pulsa "Confirmar selección"
    ↓
  Solo las ACEPTADAS se escriben en brand_cache.json
  Job pasa a COMPLETADO

VALIDACIÓN DESACTIVADA (comportamiento por defecto)
  Scraping de marcas completa
    ↓
  Todas las marcas nuevas se añaden automáticamente a brand_cache.json
  Job pasa a COMPLETADO directamente
```

**Implementación requerida:**

- `services/scraper/brand_scraper.py` → separar resolución de escritura en caché.
  Añadir parámetro `write_cache: bool = True`. Si `False`, devuelve las marcas nuevas
  sin escribirlas — el endpoint de validación se encarga de la escritura posterior.
- `api/v1/schemas/job.py` → nuevo estado `EstadoJob.PENDIENTE_VALIDACION_MARCAS`
- `api/v1/endpoints/jobs.py` → nuevo endpoint:

  ```
  POST /api/v1/jobs/{job_id}/brands/validate
  Body: [{ "ean": str, "brand_name": str, "action": "accept" | "reject" | "edit" }]
  Efecto: escribe en brand_cache.json solo los items con action != "reject"
          cambia estado del job a COMPLETADO
  ```

- `frontend/src/components/BrandValidationPanel.tsx`
  — Lista de marcas nuevas pendientes
  — Por fila: EAN · brand_name editable inline · source · badge confidence · toggle Aceptar/Rechazar
  — Contador "X marcas aceptadas / Y totales"
  — Botón "Confirmar" → `POST /api/v1/jobs/{job_id}/brands/validate`
  — Si job en `PENDIENTE_VALIDACION_MARCAS` → panel aparece automáticamente

**Reglas críticas de brand_cache.json:**

- Es la fuente de verdad local. **NUNCA** modificar sin loguear la operación.
- Estructura: `{ "prefijo_7_digitos": "nombre_marca", ... }`
- Ruta configurable via `BRAND_CACHE_PATH` en `.env`.
- Incluir en `.gitignore` bajo `data/`.

**Variables de entorno:**

```bash
BRAND_CACHE_PATH=data/brand_cache.json
```

---

#### Fase 7.5 — Selección visual de fotos antes de descarga ⭐
>
> Esta fase se implementa ANTES de las integraciones ERP/CMS.

**Por qué es necesaria:** el scraper descarga múltiples candidatas por producto
(hasta `MAX_INTENTOS_URL`) y actualmente conserva solo la primera válida.
Esta fase permite al usuario ver todas las candidatas y elegir la mejor
**antes** de generar el ZIP, eliminando el resto del disco.

**Comportamiento según modo:**

```
VALIDACIÓN ACTIVADA (toggle en SearchConfig al crear el job)
  Descarga de imágenes completa (TODAS las candidatas válidas por producto)
    ↓
  Guardadas como {codigo}_candidate_0.jpg, {codigo}_candidate_1.jpg…
  en job_{job_id}/candidates/ (directorio temporal)
    ↓
  Estado job: PENDIENTE_SELECCION_FOTOS
    ↓
  Usuario abre PhotoSelectionPanel (aparece automáticamente)
    ↓
  Por producto: ve thumbnails de todas las candidatas en fila horizontal
    ↓
  Click en thumbnail → selecciona esa como definitiva
    ↓
  Pulsa "Confirmar selección" (habilitado cuando todos los productos tienen selección)
    ↓
  Seleccionada → renombrada a {codigo}.jpg
  Resto        → eliminadas del disco
  ZIP generado con solo las fotos seleccionadas
  Job pasa a siguiente estado (PENDIENTE_VALIDACION_MARCAS o COMPLETADO)

VALIDACIÓN DESACTIVADA (comportamiento por defecto)
  Descarga completa → conserva primera imagen válida por producto
  ZIP generado directamente (comportamiento actual)
```

**Implementación requerida:**

- `services/scraper/consumer.py` → en modo validación, descargar **todas** las candidatas
  válidas. Nombrarlas `{codigo}_candidate_{n}.jpg` en subdirectorio temporal
  `job_{job_id}/candidates/`. En modo normal, comportamiento actual sin cambios.
- `services/storage_service.py` → nuevos métodos:
  - `list_candidates(job_id, codigo) → list[int]` — índices disponibles
  - `get_candidate_path(job_id, codigo, n) → Path`
  - `confirm_selection(job_id, selections: dict[str, int]) → None`
    — renombra seleccionadas, elimina el resto, borra directorio candidates/
  - `cleanup_candidates(job_id) → None` — limpieza por TTL
- `api/v1/schemas/job.py` → nuevo estado `EstadoJob.PENDIENTE_SELECCION_FOTOS`
- `api/v1/endpoints/jobs.py` → nuevos endpoints:

  ```
  GET  /api/v1/jobs/{job_id}/photos
       → lista productos con número de candidatas disponibles
  POST /api/v1/jobs/{job_id}/photos/confirm
       Body: [{ "codigo": str, "selected_index": int }]
       Efecto: confirma selecciones, genera ZIP, avanza estado del job
  ```

- `api/v1/endpoints/files.py` → nuevo endpoint:

  ```
  GET /api/v1/jobs/{job_id}/photos/{codigo}/candidates/{n}
      → sirve imagen candidata como image/jpeg para previsualización
  ```

- `frontend/src/components/PhotoSelectionPanel.tsx`
  — Grid de productos (scroll vertical)
  — Por producto: nombre + fila horizontal de thumbnails (máx 5 visibles)
  — Thumbnail seleccionado: `ring-2 ring-blue-500 scale-105`
  — Thumbnail no seleccionado: opacidad reducida al pasar el ratón
  — Contador "X / Y productos con foto seleccionada"
  — Botón "Confirmar selección" deshabilitado hasta X === Y
  — Si job en `PENDIENTE_SELECCION_FOTOS` → panel aparece automáticamente

**Orden de estados cuando AMBAS validaciones están activas:**

```
COMPLETADO_DESCARGA
  ↓
PENDIENTE_SELECCION_FOTOS   (usuario elige foto por producto)
  ↓
PENDIENTE_VALIDACION_MARCAS (usuario valida marcas nuevas)
  ↓
COMPLETADO
```

**Reglas de limpieza:**

- El directorio `candidates/` se elimina automáticamente al confirmar o al expirar el TTL.
- **NUNCA** dejar candidatas en disco de forma indefinida.
- Un job worker periódico (Celery beat) limpia candidates/ huérfanos cada hora.

**Variables de entorno:**

```bash
CANDIDATES_TTL_HOURS=24   # Horas antes de limpiar candidatas sin confirmar
```

---

### 🔭 Hoja de ruta — Integraciones ERP / CMS

> **Decisión arquitectónica clave:**
> Las integraciones viven en `services/integrations/` como servicios independientes.
> Cada plataforma tiene su propio cliente HTTP, sus propios schemas y sus propios
> endpoints bajo `/api/v1/{plataforma}/`. Comparten una interfaz base abstracta
> `IntegrationClient`. Ninguna integración importa de otra. El frontend tiene un
> tab dedicado por plataforma.

```
services/integrations/
├── base.py
├── dolibarr/   client · products · categories · thirdparties · orders · invoices · stocks
├── odoo/       client · products · categories · partners · purchase · sales · inventory · attachments
└── wordpress/  client · products · variations · categories · attributes · orders · customers · media · settings
```

---

#### Fase 8 — Integración Dolibarr
>
> API REST `/api/index.php/`. Auth: cabecera `DOLAPIKEY`. Versión mínima: Dolibarr 17+.

```bash
DOLIBARR_URL=https://mi-dolibarr.com
DOLIBARR_API_KEY=
```

- **8.1** `client.py` — httpx async, auth header, retry exponencial, paginación (limit/page)
- **8.2** Productos — CRUD + imagen + sincronización desde job Harvist
- **8.3** Categorías — árbol + creación + asignación
- **8.4** Terceros — clientes (`client=1`) + proveedores (`supplier=1`) · nombre, CIF, dirección
- **8.5** Pedidos — cliente (`orders`) + proveedor (`supplierorders`) · cambios de estado
- **8.6** Facturas — cliente + proveedor · líneas · estados · envío email
- **8.7** Stock — almacenes · movimientos · inventario actual
- **8.8** Endpoints `/api/v1/dolibarr/` — `/products`, `/categories`, `/thirdparties`,
  `/orders`, `/invoices`, `/stocks`
- **8.9** Frontend — Tab Dolibarr · panel por módulo · acción "Enviar a Dolibarr"

---

#### Fase 9 — Integración Odoo
>
> XML-RPC via `odoorpc`. Compatible Odoo 14–17.

```bash
ODOO_URL=https://mi-odoo.com
ODOO_DB=nombre_base_datos
ODOO_USER=admin@empresa.com
ODOO_PASSWORD=              # o ODOO_API_KEY (v14+)
```

- **9.1** `client.py` — odoorpc wrapper · `search_read`, `create`, `write`, `unlink` genérico
- **9.2** Productos — `product.template` + variantes · imagen via `ir.attachment`
- **9.3** Categorías — `product.category` · árbol recursivo
- **9.4** Partners — `res.partner` · `customer_rank` vs `supplier_rank`
  · **mismo modelo para clientes y proveedores** · UI con toggle
- **9.5** Compras — `purchase.order` · confirmar · recepción
- **9.6** Ventas — `sale.order` · confirmar · facturar
- **9.7** Inventario — `stock.quant` + `stock.picking`
- **9.8** Facturas — `account.move` (`out_invoice` / `in_invoice`)
- **9.9** Endpoints `/api/v1/odoo/` — `/products`, `/categories`, `/partners`,
  `/purchases`, `/sales`, `/inventory`, `/invoices`
- **9.10** Frontend — Tab Odoo · acción "Enviar a Odoo"

---

#### Fase 10 — Integración WordPress / WooCommerce
>
> REST API v3 + wp/v2. Auth: OAuth 1.0 (WC) + Application Password (WP core).

```bash
WP_URL=https://mi-tienda.com
WP_CONSUMER_KEY=ck_...
WP_CONSUMER_SECRET=cs_...
WP_APP_PASSWORD=
```

- **10.1** `client.py` — httpx async · OAuth1 WC · AppPassword WP · paginación X-WP-TotalPages
- **10.2** Productos — CRUD · simple/variable/agrupado · sincronización desde job
- **10.3** Variantes — `products/{id}/variations` · precio/stock por variante
- **10.4** Categorías y Tags — CRUD · árbol · slug automático
- **10.5** Atributos — globales + términos · locales por producto
- **10.6** Pedidos — listar · cambiar estado · notas
- **10.7** Clientes — CRUD · historial
- **10.8** Media _(crítico)_ — multipart a `/wp-json/wp/v2/media`
  · flujo: imagen Harvist → Media Library → `featured_image` del producto
- **10.9** Configuración — settings WC (moneda, impuestos, envíos, pasarelas)
- **10.10** Endpoints `/api/v1/wordpress/` — `/products`, `/variations`, `/categories`,
  `/tags`, `/attributes`, `/orders`, `/customers`, `/media`, `/settings`
- **10.11** Frontend — Tab WordPress · flujo "Publicar en WordPress"

---

### 🔗 Flujo integrado completo (visión final)

```
CSV de inventario
      ↓
[Harvist — Job de enriquecimiento]
      ↓
  Imágenes descargadas (todas las candidatas si validación ON)
    ↓ ── si foto-validación ON ──────────────────────────────
  [PhotoSelectionPanel]
    usuario elige foto definitiva por producto
    resto eliminadas del disco
    ↓ ─────────────────────────────────────────────────────
  Descripciones SEO generadas (Groq)
    ↓ ── si revisión ON ─────────────────────────────────────
  [ReviewPanel]  usuario aprueba/edita descripciones
    ↓ ─────────────────────────────────────────────────────
  Marcas resueltas (cascada 8 niveles)
    ↓ ── si marca-validación ON ─────────────────────────────
  [BrandValidationPanel]
    usuario acepta marcas → se escriben en brand_cache.json
    ↓ ─────────────────────────────────────────────────────
[ZIP final + CSVs listos para descarga]
      ↓
[Acción "Exportar a plataforma"]
      ↓
  ┌─────────────┐   ┌─────────────┐   ┌──────────────────┐
  │  Dolibarr   │   │    Odoo     │   │ WordPress/WooComm│
  │  Productos  │   │  Productos  │   │  Productos       │
  │  Categorías │   │  Variantes  │   │  + Imágenes      │
  │  Proveedores│   │  Partners   │   │  + Descripciones │
  │  Pedidos    │   │  Compras    │   │  Pedidos         │
  │  Facturas   │   │  Ventas     │   │  Clientes        │
  │  Stock      │   │  Inventario │   │  Configuración   │
  └─────────────┘   └─────────────┘   └──────────────────┘
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
│   │   └── description_generator.py
│   └── integrations/
│       ├── base.py
│       ├── dolibarr/
│       ├── odoo/
│       └── wordpress/
│
├── workers/
│   ├── celery_app.py
│   └── tasks.py
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
        ├── App.tsx                 # 5 tabs: Harvist / Dolibarr / Odoo / WordPress / Historial
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
        │   ├── dolibarr/
        │   ├── odoo/
        │   └── wordpress/
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
docker run -d -p 6379:6379 redis:7-alpine
celery -A workers.celery_app worker --loglevel=info
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
cd frontend && npm run dev

# ── Tests ─────────────────────────────────────────────────
pytest
pytest tests/unit/
pytest tests/integration/ -v
pytest --cov=api --cov=services

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
