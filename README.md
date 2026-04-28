# 🚀 Harvist

**Plataforma integral de enriquecimiento de catálogos de producto** — Descarga masiva de imágenes, generación de descripciones SEO con IA, y resolución automática de marcas mediante cascada de 8 niveles (Amazon, Open*Facts, GS1, Google, Bing).

## 🎯 Características

### 1. **Scraping de Imágenes** 📸
- Descarga masiva de imágenes de productos desde CSV
- Búsqueda en Bing Images (configurable: Google, DuckDuckGo)
- Validación automática con Pillow (dimensiones, formato, corrupción)
- Redimensionado automático a 300x300px
- Patrón Productor/Consumidor (Selenium + ThreadPool)
- Descarga final en ZIP comprimido

### 2. **Generación IA de Descripciones SEO** 🤖
- Descripciones optimizadas para buscadores usando Groq (llama-3.3-70b)
- Salida estructurada: descripción corta (gancho 10 palabras) + larga (persuasiva 60+) + keywords + meta_description
- Batch processing (múltiples productos por llamada)
- Exportación CSV integrada en resultado final

### 3. **Resolución EAN → Marca** 🏷️
- Cascada automática de 8 niveles sin Selenium (solo httpx):
  1. Validación checksum EAN (GS1 Módulo 10)
  2. Caché GS1 en memoria (prefijos conocidos)
  3. Amazon.es (ficha + listing)
  4-6. Open*Facts (PetFood, Food, UPC)
  7. Google Dorking
  8. Bing Search
  9. Not found
- **Aprendizaje automático**: registra prefijos nuevos para acelerar futuras búsquedas
- Resultado: CSV con marca, fabricante, fuente, nivel de confianza

### 4. **Integraciones ERP/CMS** (Fase 8-10) 🔄
- **Dolibarr** — CRUD productos, categorías, terceros, pedidos, facturas, stock (9 módulos)
- **Odoo** — XML-RPC, gestión de product templates, variantes, partners, compras, ventas, inventario (10 módulos)
- **WordPress/WooCommerce** — REST API, productos simple/variable/agrupado, variantes, medios, órdenes (11 módulos)

### 5. **Frontend Moderno** 💻
- React 18 + TypeScript + Vite + Tailwind CSS
- Interfaz drag-and-drop para CSV
- Progreso en tiempo real vía WebSocket
- Historial de trabajos paginado
- Componentes reutilizables y accesibles

---

## 📊 Stack Técnico

| Capa | Tecnología |
|------|-----------|
| **Backend API** | Python 3.11 + FastAPI |
| **Queue/Worker** | Celery + Redis |
| **Scraping** | undetected-chromedriver + Selenium 4 + Pillow |
| **IA** | Groq API (llama-3.3-70b) |
| **Storage** | LocalStorageService + S3 + Azure Blob |
| **Frontend** | React 18 + TypeScript + Vite + Tailwind |
| **Testing** | pytest (130+ tests unitarios + integración) |
| **Docs** | OpenAPI 3.1.0 + Swagger UI |

---

## 🚀 Quick Start

### Requisitos
- Python 3.11+
- Node.js 18+ (npm)
- Docker + Docker Compose (para Redis)
- Navegador instalado (Chrome, Chromium, Edge, Brave, Opera)

### 1️⃣ Clonar y Configurar

```bash
git clone https://github.com/BENJAMINDTS/Harvist.git
cd Harvist

# Python
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Node
cd frontend && npm install && cd ..

# Variables de entorno
cp .env.example .env.development
# Editar .env.development con credenciales reales
```

### 2️⃣ Iniciar Servicios (en orden)

```bash
# Terminal 1: Redis
docker compose up -d

# Terminal 2: Celery Worker
.venv/bin/celery -A workers.celery_app worker --loglevel=info --pool=solo

# Terminal 3: FastAPI
.venv/bin/uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 4: Vite (frontend)
cd frontend && npm run dev
```

**URLs:**
- API Swagger: http://localhost:8000/api/docs
- Frontend: http://localhost:5173
- Redis: localhost:6379

### 3️⃣ Usar la Aplicación

1. Ve a http://localhost:5173
2. Sube CSV con columnas: `codigo`, `nombre`, `marca`, `categoria`
3. Elige modo búsqueda (EAN / Nombre+Marca / Custom)
4. Activa opciones: Generar descripciones IA, Resolver marcas
5. Crea job y espera progreso en tiempo real
6. Descarga ZIP con imágenes + descripciones + marcas

---

## 📁 Estructura del Proyecto

```
harvist/
├── api/
│   ├── core/
│   │   ├── config.py           # Pydantic Settings v2
│   │   ├── logging.py          # loguru JSON
│   │   └── security.py         # CORS + rate limiting
│   ├── main.py                 # App factory FastAPI
│   └── v1/
│       ├── schemas/
│       │   └── job.py          # JobStatus, JobCreate, SearchConfig
│       ├── endpoints/
│       │   ├── jobs.py         # POST/GET jobs, WS progreso
│       │   └── files.py        # GET descarga, DELETE cleanup
│       └── router.py           # Monta endpoints
│
├── services/
│   ├── csv_parser.py           # Lectura y validación CSV
│   ├── storage_service.py      # LocalStorageService + S3/Azure
│   ├── scraper/
│   │   ├── pipeline.py         # Orquestador Productor/Consumidor
│   │   ├── producer.py         # Selenium + fábrica navegadores
│   │   ├── consumer.py         # ThreadPool + validación Pillow
│   │   ├── brand_scraper.py    # Cascada EAN → marca (8 niveles)
│   │   ├── brand_cache.py      # GS1 cache + aprendizaje automático
│   │   └── brand_validator.py  # EAN checksum + longest prefix match
│   ├── ai/
│   │   ├── groq_client.py      # Cliente Groq con reintentos
│   │   └── description_generator.py # Descripciones SEO batch
│   └── utils/
│       ├── ean_http_clients.py # Open*Facts, UPC, Google, Bing
│       └── amazon_brand_client.py # Scraping Amazon sin Selenium
│
├── workers/
│   ├── celery_app.py           # Configuración Celery
│   └── tasks.py                # Tarea ejecutar_scraping
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.ts       # Axios + WebSocket builder
│   │   ├── components/
│   │   │   ├── CsvUploader.tsx
│   │   │   ├── SearchConfig.tsx
│   │   │   ├── JobProgress.tsx
│   │   │   ├── JobHistory.tsx
│   │   │   └── BrandsPanel.tsx (Fase 6.4)
│   │   ├── hooks/
│   │   │   └── useJobWebSocket.ts # Reconexión automática
│   │   └── App.tsx             # State machine
│   ├── package.json
│   └── vite.config.ts
│
├── tests/
│   ├── unit/test_csv_parser.py
│   ├── services/scraper/test_brand_*.py
│   └── integration/test_jobs_endpoint.py
│
├── .github/
│   ├── workflows/
│   │   ├── harvist-roadmap.yml        # Auto-labels, comentarios
│   │   └── update-project-status.yml  # Cierra issues, actualiza proyecto
│   ├── AUTOMATION.md                  # Detalles de workflows
│   └── ROADMAP_SETUP.md               # Pasos manuales para proyecto v2
│
├── CLAUDE.md                   # Reglas de desarrollo + arquitectura
├── ROADMAP_QUICK_START.md      # Guía práctica + ejemplos
├── .env.example                # Plantilla variables
├── pyproject.toml              # Dependencias Python (lockfile)
└── openapi.yaml                # Contrato OpenAPI 3.1.0
```

---

## 🧪 Testing

```bash
# Todos los tests
pytest

# Solo unitarios
pytest tests/unit/

# Solo integración
pytest tests/integration/ -v

# Con cobertura
pytest --cov=api --cov=services --cov=workers
```

**Cobertura actual:** 130+ tests (unitarios + integración)

---

## 📋 Roadmap

### ✅ Completado (Fase 1-6.3)
- Core scraping imágenes + ThreadPool
- API REST + WebSocket tiempo real
- Frontend 4 componentes + state machine
- Celery + Redis persistencia
- Generación descripciones SEO (Groq)
- Historial + paginación
- Resolución EAN → marca (cascada 8 niveles, sin Selenium)

### 🔒 En Desarrollo (Fase 6.4 - 7.3)
| # | Fase | Descripción | Estado |
|---|------|-------------|--------|
| 6.4 | Frontend marcas | Panel tabla de marcas resueltas | [#41](https://github.com/BENJAMINDTS/Harvist/issues/41) |
| 7.1 | Textos SEO | Meta title + meta description | [#42](https://github.com/BENJAMINDTS/Harvist/issues/42) |
| 7.2 | Traducción | Múltiples idiomas (EN, FR, DE, IT, PT) | [#43](https://github.com/BENJAMINDTS/Harvist/issues/43) |
| 7.3 | Revisión manual | Panel editable pre-exportación | [#44](https://github.com/BENJAMINDTS/Harvist/issues/44) |

### 📅 Próximo (Fase 8-10)
| # | Fase | Descripción | Módulos |
|---|------|-------------|---------|
| 8 | **Dolibarr** | Integración ERP | Productos, Categorías, Terceros, Pedidos, Facturas, Stock | [#45-#53](https://github.com/BENJAMINDTS/Harvist/issues?q=is%3Aissue+Fase+8) |
| 9 | **Odoo** | XML-RPC sync | Productos, Partners, Compras, Ventas, Inventario | [TBD](https://github.com/BENJAMINDTS/Harvist/issues) |
| 10 | **WordPress/WC** | REST API sync | Productos, Variantes, Categorías, Órdenes, Medios | [TBD](https://github.com/BENJAMINDTS/Harvist/issues) |

---

## 🤝 Contribuir

### Pasos

1. **Elige issue** de [Projects/Harvist Roadmap](https://github.com/BENJAMINDTS/Harvist/projects)
2. **Crea rama** basada en el issue:
   ```bash
   git checkout main && git pull
   git checkout -b feat/fase-7.1-seo-texts
   ```
3. **Commits atómicos** (Conventional Commits):
   ```bash
   git commit -m "feat: create seo_generator.py"
   git commit -m "feat: add endpoint GET /api/v1/files/{id}/seo"
   git commit -m "test: add unit tests"
   ```
4. **Push y PR**:
   ```bash
   git push -u origin feat/fase-7.1-seo-texts
   ```
5. **Body del PR menciona issue**:
   ```markdown
   Fixes #42
   
   ## Cambios
   - [x] Service creado
   - [x] Endpoint agregado
   - [x] Tests escritos
   ```
6. **Workflow automatiza**:
   - ✅ Vincula issue
   - ✅ Agrega label "phase:7.1"
   - ✅ Marca como "in-progress"
   - ✅ Comenta checklist

7. **Mergea y workflow**:
   - ✅ Cierra issue
   - ✅ Comenta confirmación
   - ✅ Actualiza proyecto

### Reglas de Código

- **Separación**: `api/` no importa `services/`
- **Logs**: `loguru`, nunca `print()`, sin datos sensibles
- **Env vars**: via `get_settings()` (Python) o env (TS)
- **Docstrings**: pydoc (Python) / JSDoc (TypeScript)
- **Tests**: lógica crítica debe tener tests
- **Commits**: uno por acción concreta, no `git add .`

### Documentación

- [CLAUDE.md](CLAUDE.md) — Especificaciones técnicas + reglas de desarrollo
- [ROADMAP_QUICK_START.md](ROADMAP_QUICK_START.md) — Guía práctica + ejemplos
- [.github/AUTOMATION.md](.github/AUTOMATION.md) — Detalles de workflows
- [.github/ROADMAP_SETUP.md](.github/ROADMAP_SETUP.md) — Pasos manuales

---

## 🔐 Seguridad

- Secretos en `.env` (nunca en git)
- CORS lista blanca (nunca `*`)
- Rate limiting en endpoints públicos
- Cabeceras HTTP de seguridad (helmet)
- Validación Pydantic en entrada
- Logging JSON sin datos sensibles
- HTTPS obligatorio en producción

---

## 📞 Equipo

- **Benjamin DTS** ([GitHub](https://github.com/BENJAMINDTS)) — Architetto, Backend, Scraping
- **Carlos Vico** ([GitHub](https://github.com/Carlitos6712)) — IA, Frontend, Integraciones

---

## 📄 Licencia

[Definir licencia]

---

## 🔗 Links

- **Issues**: https://github.com/BENJAMINDTS/Harvist/issues
- **Projects**: https://github.com/BENJAMINDTS/Harvist/projects
- **Swagger UI**: http://localhost:8000/api/docs (development only)
- **OpenAPI Spec**: `openapi.yaml`

---

**Última actualización:** 2026-04-28  
**Status:** Fases 1-6.3 ✅ | Fases 6.4-7.3 🔨 | Fases 8-10 📋
