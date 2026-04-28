# Harvist Roadmap — Quick Start Guide

## 🎯 Resumen Ejecutivo

Se han creado **32+ issues** en GitHub correspondientes a todas las fases de desarrollo pendientes (Fase 6.4 → Fase 10), con automación completa para:
- Vincular automáticamente PRs a issues
- Actualizar estado de issues cuando se mergea
- Auto-comentarios con checklists
- Integración con proyecto GitHub v2 (una vez configurado manualmente)

## 📋 Issues Creadas

### ✅ Fase 6.4 — Frontend Panel de Marcas
- **#41** Implementar tabla de marcas con filtros por source/confidence

### ✅ Fase 7 — Generación de Textos
- **#42** Textos SEO (meta_title + meta_description)
- **#43** Traducción automática a múltiples idiomas (EN, FR, DE, IT, PT)
- **#44** Panel de revisión manual pre-exportación

### ✅ Fase 8 — Integración Dolibarr (9 sub-issues)
```
#45 → 8.1 Cliente HTTP async (httpx)
#46 → 8.2 Módulo Productos
#47 → 8.3 Módulo Categorías
#48 → 8.4 Módulo Terceros (Clientes+Proveedores)
#49 → 8.5 Módulo Pedidos
#50 → 8.6 Módulo Facturas
#51 → 8.7 Módulo Stock
#52 → 8.8 Endpoints API
#53 → 8.9 Frontend sección Dolibarr
```

### 📌 Fase 9 — Integración Odoo (pendiente crear issues con body)
10 sub-issues (9.1 → 9.10)

### 📌 Fase 10 — Integración WordPress (pendiente crear issues con body)
11 sub-issues (10.1 → 10.11)

## 🚀 Cómo Empezar

### Opción 1: Contribuir una Fase Existente

```bash
# 1. Elige una issue (ej: #42 — Textos SEO)
# 2. Crea rama basada en el nombre
git checkout main && git pull
git checkout -b feat/fase-7.1-seo-texts

# 3. Haz commits atómicos (con Conventional Commits)
git commit -m "feat: create seo_generator.py service"
git commit -m "feat: add SEO text generation to SearchConfig"
git commit -m "test: add unit tests for seo_generator"

# 4. Push y crea PR mencionando la issue
git push -u origin feat/fase-7.1-seo-texts

# 5. En el UI de GitHub, crea PR con body:
```

**Plantilla PR:**
```markdown
# Descripción
[Describe qué hace este PR]

Fixes #42

## Cambios
- [ ] Service creado
- [ ] Endpoints agregados
- [ ] Frontend actualizado
- [ ] Tests escritos

## Testing
- [ ] Tests locales pasan
- [ ] Probado en http://localhost:8000/api/docs

## Docs
- [ ] Docstrings actualizado
- [ ] .env.example actualizado (si aplica)
```

### Opción 2: Crear Proyecto v2 (Administrador)

**Paso 1:** Ve a https://github.com/BENJAMINDTS/Harvist/projects
**Paso 2:** Click "New project" → Table → "Harvist Roadmap"
**Paso 3:** Agrega columnas:
- Status: Backlog, In Progress, In Review, Done
- Priority: High, Medium, Low
- Phase: 6.4, 7.x, 8.x, 9.x, 10.x

**Paso 4:** Agrega issues al proyecto (bulk add)
**Paso 5:** Crea labels (opcional, mejora UI):

```bash
gh label create "phase:6.4" --color "0366d6"
gh label create "phase:7" --color "0366d6"
gh label create "phase:8" --color "6f42c1"
gh label create "phase:9" --color "6f42c1"
gh label create "phase:10" --color "6f42c1"
gh label create "type:backend" --color "1f6feb"
gh label create "type:frontend" --color "fbca04"
gh label create "status:in-progress" --color "fbca04"
gh label create "status:done" --color "28a745"
```

## ✨ Automación en Acción

### Flujo Normal:

```
1. Abres PR con título "feat: Fase 7.1 - Textos SEO"
   ↓
2. Workflow detecta "Fase 7.1" → agrega label automáticamente
   ↓
3. PR menciona "Fixes #42" → vincula automáticamente
   ↓
4. Mergeas PR
   ↓
5. Workflow cierra issue #42, comenta, actualiza proyecto
```

### Lo que hace el Workflow:

```yaml
On PR open:
  ✅ Detect Fase X.Y
  ✅ Add label "phase:X.Y"
  ✅ Comment checklist
  ✅ Link to issues

On PR merge:
  ✅ Comment in linked issues
  ✅ Close issues (if Fixes #X)
  ✅ Add "status:done" label
  ✅ Update project status
```

## 📁 Archivos de Configuración

```
.github/
├── workflows/
│   ├── harvist-roadmap.yml           ← Main automation
│   └── update-project-status.yml     ← Project updates
├── AUTOMATION.md                      ← Detalles técnicos
└── ROADMAP_SETUP.md                   ← Pasos manuales

ROADMAP_QUICK_START.md                ← Este archivo
CLAUDE.md                              ← Especificaciones técnicas
```

## 📊 Estado Actual

| Fase | Descripción | Issues | Estado |
|------|-------------|--------|--------|
| 6.4 | Frontend marcas | #41 | 📋 Pendiente |
| 7.1 | Textos SEO | #42 | 📋 Pendiente |
| 7.2 | Traducción | #43 | 📋 Pendiente |
| 7.3 | Revisión manual | #44 | 📋 Pendiente |
| 8.x | Dolibarr | #45-#53 (9 sub) | 📋 Pendiente |
| 9.x | Odoo | (crear issues) | 🔨 TODO |
| 10.x | WordPress | (crear issues) | 🔨 TODO |

## 🎓 Ejemplos

### Ejemplo 1: PR que implementa Fase 6.4

```markdown
# Title
feat: Fase 6.4 - Componente BrandsPanel con tabla de resultados

# Body
Implementa el componente React para mostrar marcas resueltas.

Fixes #41

## Cambios
- [x] Crear `frontend/src/components/BrandsPanel.tsx`
- [x] Tabla con código, ean, brand_name, manufacturer, source, confidence
- [x] Filtros por source (amazon, cache_gs1, not_found)
- [x] Filtros por confidence (high/medium/low)
- [x] Indicadores visuales (colores por confianza)
- [x] Integración en App.tsx bajo pestaña "Marcas"
- [x] Responsive mobile-first
- [x] Tests unitarios
- [x] JSDoc en componente

## Testing
- [x] `npm run type-check` pasa
- [x] `npm run build` pasa sin errores
- [x] Probado en http://localhost:5173
- [x] Filtra correctamente por source
- [x] Filtra correctamente por confidence
- [x] Responsive en mobile/tablet/desktop
```

**Resultado automático:**
- ✅ Issue #41 vinculada
- ✅ Label "phase:6.4" agregado
- ✅ Comentario checklist
- ✅ Al mergear: cierra #41, comenta confirmación

### Ejemplo 2: PR que implementa múltiples Fases

```markdown
# Title
feat: Fase 7.1 + 7.2 - SEO texts + translation

# Body
Implementa generación de textos SEO y traducción automática.

Fixes #42 #43

## Cambios
- Crear `services/ai/seo_generator.py`
- Crear `services/ai/translation_service.py`
- Endpoints `/api/v1/files/{job_id}/seo` y `/translations`
- Frontend toggles en SearchConfig
- Exportación a CSV adicional
```

**Resultado automático:**
- ✅ Issues #42 y #43 vinculadas
- ✅ Labels "phase:7.1" y "phase:7.2" agregados
- ✅ Al mergear: cierra ambas issues, comenta en ambas

## 🔗 Links Rápidos

- **Issues**: https://github.com/BENJAMINDTS/Harvist/issues
- **Projects**: https://github.com/BENJAMINDTS/Harvist/projects
- **Pulls**: https://github.com/BENJAMINDTS/Harvist/pulls
- **Automation Docs**: `.github/AUTOMATION.md`
- **Setup Manual**: `.github/ROADMAP_SETUP.md`
- **Specs Técnicas**: `CLAUDE.md`

## ❓ Preguntas Frecuentes

**P: ¿Cómo sé cuál issue trabajar?**
A: Elige cualquiera de la lista anterior. Las de Fase 6.4-7.3 son más cortas y buenas para empezar. Las de Fase 8-10 son integraciones mayores.

**P: ¿Qué pasa si mi PR cierra múltiples issues?**
A: Menciona todas en el body ("Fixes #42 #43 #44") y workflow cierra todas automáticamente.

**P: ¿El workflow requiere configuración adicional?**
A: Solo el proyecto v2 (manual). Workflows funcionan out-of-the-box una vez pusheados.

**P: ¿Cómo veo el proyecto actualizado?**
A: Una vez creado en GitHub, ve a `/projects` y verás las issues organizadas por status.

**P: ¿Puedo mergear sin PR?**
A: Sí, pero entonces los workflows no cierran issues automáticamente. Mejor siempre usar PR.

## 🎁 Bonus: Estadísticas

Después de crear el proyecto v2, puedes ver:
- % de compleción por fase
- Tiempo promedio issue → closed
- Velocidad de merges por semana
- Bottlenecks de revisión

---

**Status:** ⚠️ Workflows listos, proyecto v2 pendiente (crear manualmente)  
**Última actualización:** 2026-04-28  
**Creado por:** Claude Code (Caveman Mode)

---

👉 **Próximo paso:** Crear Proyecto v2 (ver `.github/ROADMAP_SETUP.md`)
