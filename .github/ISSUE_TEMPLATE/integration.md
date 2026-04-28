---
name: Integración ERP/CMS
about: Nueva integración con plataforma externa (Dolibarr, Odoo, WordPress)
title: "Fase X: [Plataforma] - [Módulo]"
labels: ["type:integration", "status:pending"]
---

## Plataforma
- [ ] Dolibarr (REST API)
- [ ] Odoo (XML-RPC)
- [ ] WordPress/WooCommerce (REST API)

## Módulo
<!-- Qué módulo se implementa (Productos, Pedidos, etc) -->

## Descripción
<!-- Qué se integra y por qué -->

## Especificaciones Técnicas

### Autenticación
<!-- Cómo autenticar con la API externa -->
```bash
# Variables de entorno
PLATAFORMA_URL=...
PLATAFORMA_API_KEY=...
```

### Endpoints / Métodos
<!-- Qué endpoints/métodos de la API se usan -->

### Cliente HTTP
- [ ] httpx async (Dolibarr, WordPress)
- [ ] odoorpc (Odoo)
- [ ] Retry exponencial
- [ ] Paginación automática

### Servicio
`services/integrations/[plataforma]/[modulo].py`
- [ ] CRUD completo (create, read, update, delete)
- [ ] Validación entrada
- [ ] Manejo errores HTTP
- [ ] Logging estructurado

### API Endpoints
`api/v1/endpoints/[plataforma]/[modulo].py`
```
GET    /api/v1/[plataforma]/[modulo]
GET    /api/v1/[plataforma]/[modulo]/{id}
POST   /api/v1/[plataforma]/[modulo]
PATCH  /api/v1/[plataforma]/[modulo]/{id}
DELETE /api/v1/[plataforma]/[modulo]/{id}
```

### Frontend
`frontend/src/components/[Plataforma]Panel.tsx`
- [ ] Tabla de listado
- [ ] Formulario create/edit
- [ ] Botón "Enviar a [Plataforma]" desde resultado job
- [ ] Indicadores de sincronización

## Tareas
- [ ] Cliente HTTP creado y testeado
- [ ] Servicio implementado (CRUD + errores)
- [ ] Endpoints API agregados
- [ ] Documentación OpenAPI actualizada
- [ ] Frontend componente creado
- [ ] Tests integración escritos
- [ ] Docs en CLAUDE.md actualizadas

## Testing
### Local
- [ ] Tests unitarios: `pytest tests/services/integrations/...`
- [ ] Tests integración: `pytest tests/integration/...`
- [ ] Sandbox account / API keys preparadas

### Manual
- [ ] Endpoint GET lista: ✓
- [ ] Endpoint GET por ID: ✓
- [ ] Endpoint POST crear: ✓
- [ ] Endpoint PATCH actualizar: ✓
- [ ] Endpoint DELETE eliminar: ✓
- [ ] Frontend upload y sincronización: ✓

## Dependencias
<!-- Módulos o fases que bloqueadas/bloquean -->
- Bloquea: (si aplica)
- Bloqueada por: (si aplica)

## Referencias
<!-- Links a docs de la plataforma -->
- [Dolibarr API](https://wiki.dolibarr.org/index.php/API_Documentation)
- [Odoo RPC](https://www.odoo.com/documentation/17.0/developer/reference/external_api.html)
- [WooCommerce REST API](https://woocommerce.com/document/woocommerce-rest-api/)

## Notas
<!-- Consideraciones especiales, limites de la API, etc -->

---
**Harvist Roadmap** — Fase X: Integración [Plataforma]
