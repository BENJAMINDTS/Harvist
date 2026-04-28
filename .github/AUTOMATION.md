# Harvist GitHub Automation

Documentación completa de la automación GitHub para la hoja de ruta (Roadmap).

## 📋 Flujo Automatizado

### 1️⃣ Cuando abres un PR

**Acciones automáticas:**
```
PR creado
  ↓
[harvist-roadmap.yml] Workflow activa
  ├─ Extrae "Fase X.Y" del título
  ├─ Agrega label "phase:X.Y"
  ├─ Comenta checklist de verificación
  └─ Vincula a issues mencionadas (Fixes #123)

[update-project-status.yml] Workflow activa
  ├─ Busca issues mencionadas en el body
  ├─ Agrega label "status:in-progress" a esas issues
  └─ Comenta confirmación en las issues
```

**Ejemplo de PR con automación:**

```markdown
# Título
feat: Fase 6.4 - Frontend panel de marcas

# Body
Implementa tabla editable de marcas resueltas.

Fixes #41

## Cambios
- [ ] BrandsPanel.tsx
- [ ] Filtros por source/confidence
- [ ] Integración en App.tsx
```

**Resultado:**
- ✅ Label `phase:6.4` agregado automáticamente
- ✅ Comentario checklist en el PR
- ✅ Issue #41 vinculada
- ✅ Issue #41 marca como "in-progress"

### 2️⃣ Cuando mergeas un PR

**Acciones automáticas:**
```
PR merged (main branch)
  ↓
[update-project-status.yml] Workflow activa
  ├─ Busca issues mencionadas (Fixes #123)
  ├─ Cierra issues automáticamente
  ├─ Agrega label "status:done"
  ├─ Comenta confirmación en issues resueltas
  └─ Actualiza estado en el proyecto a "Done"
```

**Ejemplo de cierre automático:**

Después de mergear un PR que dice "Fixes #41":
- ✅ Issue #41 se cierra automáticamente
- ✅ Comentario automático: "✅ Done — Resuelto en PR #XXX"
- ✅ Label "status:done" agregado
- ✅ Proyecto actualiza a estado "Done"

### 3️⃣ Cuando reopres un PR

Si reopres un PR que estaba cerrado:
- ✅ Issues vinculadas se reabren automáticamente
- ✅ Label "status:in-progress" se reagrega
- ✅ Comentario de confirmación

## 🔧 Workflows Instalados

### `.github/workflows/harvist-roadmap.yml`

**Triggers:**
- PR abierto / synchronize / reopenido
- PR cerrado (merged)

**Acciones:**
1. `link-issues` — Vincula PR a issues mencionadas
2. `update-issue-on-merge` — Comenta en issues cuando PR se mergea
3. `add-to-project` — Agrega label de fase automáticamente
4. `welcome-pr` — Comenta checklist de verificación

### `.github/workflows/update-project-status.yml`

**Triggers:**
- PR abierto / cerrado / reabierto
- Issue abierta / cerrada / reabierta

**Acciones:**
1. `update-project` — Extrae info del evento
2. `mark-in-progress` — Marca issues como "in-progress"
3. Cierra issues automáticamente (si dice "Fixes #X")
4. Actualiza proyecto

## 📝 Referencia de Palabras Clave

Para vincular un PR a issues automáticamente, usa estas palabras clave en el body del PR:

```markdown
Fixes #123           # Cierra issue #123
Closes #123          # Cierra issue #123
Resolves #123        # Cierra issue #123
Related to #123      # Vincula sin cerrar
Implements #123      # Vincula sin cerrar
Refs #123            # Vincula sin cerrar
```

## ✅ Checklist de Configuración

- [x] `.github/workflows/harvist-roadmap.yml` creado
- [x] `.github/workflows/update-project-status.yml` creado
- [ ] Crear Proyecto v2 en GitHub (manual, ver ROADMAP_SETUP.md)
- [ ] Crear labels en GitHub (manual, ver ROADMAP_SETUP.md)
- [ ] Agregar issues existentes al proyecto (manual)
- [ ] Probar flujo con un PR de prueba

## 🧪 Prueba Rápida

### Paso 1: Crear rama de prueba
```bash
git checkout main
git pull origin main
git checkout -b test/automation-test
```

### Paso 2: Hacer cambio trivial
```bash
echo "# Test automation" >> TEST.md
git add TEST.md
git commit -m "test: automation test"
git push -u origin test/automation-test
```

### Paso 3: Crear PR mencionando una issue
En el UI de GitHub, crea un PR con:
```markdown
Title: test: Fase 6.4 - Test automation

Body:
Test de la automación de Harvist.

Refs #41
```

### Paso 4: Observar
- ✅ Workflow corre automáticamente
- ✅ Label `phase:6.4` se agrega
- ✅ Comentario checklist aparece
- ✅ Issue #41 se vincula

### Paso 5: Mergear y observar
- ✅ Workflow de merge activa
- ✅ Comentario en issue #41
- ✅ Proyecto se actualiza

### Paso 6: Limpiar
```bash
git checkout main
git pull origin main
git branch -d test/automation-test
```

## 🚀 Próximas Mejoras (Opcionales)

- [ ] Webhook para Slack notifications
- [ ] Auto-assign PRs a equipo basado en labels
- [ ] Auto-request reviews de equipos específicos
- [ ] Generate release notes automáticamente
- [ ] Cron job para audit de proyectos sin PRs hace X días

## 📊 Métricas de Seguimiento

Una vez configurado, puedes ver en el Proyecto v2:
- % de issues en "Done" por fase
- Tiempo promedio issue → PR → Done
- Issues "Backlog" vs "In Progress" vs "Done"
- Velocidad de desarrollo por fase

## 🔗 Documentación Relacionada

- [ROADMAP_SETUP.md](.github/ROADMAP_SETUP.md) — Pasos manuales de configuración
- [CLAUDE.md](../CLAUDE.md) — Especificaciones técnicas de fases
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [GitHub Projects Docs](https://docs.github.com/en/issues/planning-and-tracking-with-projects)

---

**Última actualización:** 2026-04-28  
**Estado:** ⚠️ Pendiente de crear proyecto v2 manualmente
