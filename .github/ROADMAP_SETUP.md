# Harvist Roadmap Setup

Este archivo documenta cómo se ha configurado la automatización de la hoja de ruta en GitHub.

## ✅ Estado Actual

### Issues Creadas
- **Fase 6.4**: Frontend panel de marcas (#41)
- **Fase 7.1**: Textos SEO (#42)
- **Fase 7.2**: Traducción automática (#43)
- **Fase 7.3**: Panel de revisión manual (#44)
- **Fase 8.1-8.9**: Integración Dolibarr (#45-#53)

### Workflows Activos
1. `.github/workflows/harvist-roadmap.yml` — Auto-comentarios, linking, labels

## 📋 Pasos Siguientes (Manuales)

### 1. Crear Proyecto v2 en GitHub

**Opción A: Via UI**
1. Ve a `https://github.com/BENJAMINDTS/Harvist/projects`
2. Click "New project"
3. Nombre: `Harvist Roadmap`
4. Template: `Table` (o `Kanban`)
5. Campos:
   - Title (built-in)
   - Status: `Backlog`, `In Progress`, `In Review`, `Done`
   - Priority: `High`, `Medium`, `Low`
   - Phase: `6.4`, `7.1`, `7.2`, `7.3`, `8.x`, `9.x`, `10.x`

**Opción B: Via gh CLI (requiere auth refresh)**
```bash
gh auth refresh -h github.com -s repo,project
gh project create --title "Harvist Roadmap" --owner BENJAMINDTS --format json
```

### 2. Agregar Issues al Proyecto

Una vez creado el proyecto, agregar las issues mediante:

```bash
# Manual: Click en cada issue → Add to project → Harvist Roadmap

# O via API (requiere project token):
gh api graphql -f query='mutation {addProjectsV2ItemById(input:{projectId:"PVT_...",contentId:"I_..."}) {item{id}}}'
```

### 3. Crear Labels Opcionales

Para mejor organización visual, crear estos labels:

```bash
gh label create "phase:6.4" --color "0366d6" --description "Fase 6.4: Frontend marcas"
gh label create "phase:7.1" --color "0366d6" --description "Fase 7.1: Textos SEO"
gh label create "phase:7.2" --color "0366d6" --description "Fase 7.2: Traducción"
gh label create "phase:7.3" --color "0366d6" --description "Fase 7.3: Revisión manual"
gh label create "phase:8" --color "6f42c1" --description "Fase 8: Dolibarr"
gh label create "phase:9" --color "6f42c1" --description "Fase 9: Odoo"
gh label create "phase:10" --color "6f42c1" --description "Fase 10: WordPress"
gh label create "type:backend" --color "1f6feb"
gh label create "type:frontend" --color "fbca04"
gh label create "status:pending" --color "d73a49"
gh label create "status:in-progress" --color "fbca04"
gh label create "status:done" --color "28a745"
```

## 🔄 Flujo Automatizado (Una vez configurado)

### Cuando se abre un PR:
1. ✅ Workflow detecta "Fase X.Y" en el título
2. ✅ Agrega label `phase:X.Y` automáticamente
3. ✅ Comenta un checklist de pre-merge
4. ✅ Vincula a issues mencionadas (Fixes #123)

### Cuando se mergea un PR:
1. ✅ Workflow comenta en issues resueltas
2. ✅ Actualiza estado en el proyecto (de "In Progress" a "Done")
3. ✅ Cierra issues relacionadas (si está en el body del PR)

### Ejemplo de PR que cierra issues:

```markdown
# Descripción
Implementa el panel frontend de marcas.

Fixes #41

## Cambios
- [ ] BrandsPanel.tsx creado
- [ ] Filtros por source + confidence
- [ ] Integración en App.tsx

## Testing
- [ ] Tests unitarios agregados
- [ ] Probado en http://localhost:5173
```

**Resultado automático:**
- Issue #41 se vincula al PR
- Cuando se mergea, la issue se cierra automáticamente
- Proyecto actualiza a "Done"
- Comentario automático en #41

## 📊 Estructura del Proyecto (Recomendado)

```
Harvist Roadmap
├── Backlog
│   ├── Fase 8: Dolibarr
│   ├── Fase 9: Odoo
│   └── Fase 10: WordPress
├── In Progress
│   ├── Fase 6.4: Frontend marcas
│   ├── Fase 7.1: Textos SEO
│   └── Fase 7.3: Revisión manual
├── In Review
│   └── [PRs abiertos de fases activas]
└── Done
    ├── Fase 6.1-6.3 (completadas)
    └── [Issues resueltas]
```

## 🔗 Referencias

- GitHub Workflows: `.github/workflows/harvist-roadmap.yml`
- CLAUDE.md: Especificaciones técnicas de cada fase
- Issue #41+: Descripciones detalladas de tareas

## 🚀 Próximos Pasos

1. Crear proyecto v2 en GitHub
2. Ejecutar `gh label create ...` para los labels
3. Agregar issues al proyecto
4. Comenzar a crear PRs que referencien issues
5. Workflow actualiza automáticamente proyecto + issues

---

**Última actualización:** 2026-04-28  
**Creado por:** Claude Code (Caveman Mode)
