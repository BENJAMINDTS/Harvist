# Manual de Usuario — Harvist

**Versión:** 1.0.0  
**Autores:** BenjaminDTS · Carlos Vico (Nubium Solutions)  
**Última actualización:** Mayo 2026

---

## Tabla de Contenidos

1. [Introducción](#1-introducción)
2. [Requisitos previos](#2-requisitos-previos)
3. [Acceso a la aplicación](#3-acceso-a-la-aplicación)
4. [Dashboard principal](#4-dashboard-principal)
5. [Módulo Harvist — Enriquecimiento de catálogos](#5-módulo-harvist--enriquecimiento-de-catálogos)
   - 5.1 [Preparar el CSV de inventario](#51-preparar-el-csv-de-inventario)
   - 5.2 [Subir el CSV](#52-subir-el-csv)
   - 5.3 [Configurar el job](#53-configurar-el-job)
   - 5.4 [Seguimiento en tiempo real](#54-seguimiento-en-tiempo-real)
   - 5.5 [Panel de marcas](#55-panel-de-marcas)
   - 5.6 [Revisión de descripciones](#56-revisión-de-descripciones)
   - 5.7 [Validación de marcas](#57-validación-de-marcas)
   - 5.8 [Selección de fotos](#58-selección-de-fotos)
   - 5.9 [Descargar resultados](#59-descargar-resultados)
   - 5.10 [Historial de jobs](#510-historial-de-jobs)
6. [Módulo Dolibarr](#6-módulo-dolibarr)
   - 6.1 [Configuración de conexión](#61-configuración-de-conexión)
   - 6.2 [Productos](#62-productos)
   - 6.3 [Categorías](#63-categorías)
   - 6.4 [Marcas](#64-marcas)
   - 6.5 [Proveedores y clientes](#65-proveedores-y-clientes)
   - 6.6 [Pedidos](#66-pedidos)
   - 6.7 [Facturas](#67-facturas)
   - 6.8 [Stock](#68-stock)
   - 6.9 [Campos extra](#69-campos-extra)
   - 6.10 [Sincronización Harvist → Dolibarr](#610-sincronización-harvist--dolibarr)
7. [Módulo Odoo](#7-módulo-odoo)
   - 7.1 [Configuración de conexión](#71-configuración-de-conexión)
   - 7.2 [Productos](#72-productos)
   - 7.3 [Categorías y eCommerce](#73-categorías-y-ecommerce)
   - 7.4 [Marcas](#74-marcas)
   - 7.5 [Partners](#75-partners)
   - 7.6 [Compras y ventas](#76-compras-y-ventas)
   - 7.7 [Inventario](#77-inventario)
   - 7.8 [Facturas](#78-facturas)
   - 7.9 [Campos extra y propiedades](#79-campos-extra-y-propiedades)
8. [Módulo WordPress / WooCommerce](#8-módulo-wordpress--woocommerce)
   - 8.1 [Configuración REST API](#81-configuración-rest-api)
   - 8.2 [Configuración base de datos](#82-configuración-base-de-datos)
   - 8.3 [Productos](#83-productos)
   - 8.4 [Categorías y marcas](#84-categorías-y-marcas)
   - 8.5 [Pedidos y clientes](#85-pedidos-y-clientes)
   - 8.6 [Media](#86-media)
   - 8.7 [Base de datos directa](#87-base-de-datos-directa)
   - 8.8 [Sincronización Harvist → WordPress](#88-sincronización-harvist--wordpress)
9. [Flujo de trabajo completo](#9-flujo-de-trabajo-completo)
10. [Preguntas frecuentes](#10-preguntas-frecuentes)

---

## 1. Introducción

**Harvist** es una plataforma web para **enriquecimiento masivo de catálogos de producto** y **gestión integrada de ERPs y CMS**.

Sus cuatro pilares son:

| Pilar | Qué hace |
|-------|----------|
| **Scraping** | Descarga imágenes de producto en masa desde un CSV, usando búsqueda visual en Bing/Google/DuckDuckGo |
| **IA** | Genera descripciones SEO y textos de producto con inteligencia artificial (Groq / Claude) |
| **Marcas** | Resuelve código EAN → marca comercial a través de una cascada de 8 fuentes de datos |
| **Integraciones** | Gestión completa de Dolibarr, Odoo y WordPress/WooCommerce vía API |

### Para qué sirve Harvist

Tienes un catálogo de miles de referencias en un fichero Excel/CSV. Necesitas:

- Imágenes de cada producto sin buscarlas una a una
- Descripciones en varios idiomas para tu tienda online
- Saber la marca de cada EAN
- Subir todo a Dolibarr, Odoo o WooCommerce

Harvist automatiza esos cuatro pasos desde una sola interfaz web.

---

## 2. Requisitos previos

### Para el usuario final

- Navegador moderno: Chrome, Firefox, Edge (versión reciente)
- Acceso a la URL de la aplicación (proporcionada por tu administrador)
- Fichero CSV con el inventario de productos

### Formato del CSV de inventario

El CSV debe contener columnas como mínimo con el nombre del producto. Las columnas estándar reconocidas son:

| Columna | Descripción | Obligatoria |
|---------|-------------|-------------|
| `codigo` | Código de referencia del producto | Sí |
| `nombre` | Nombre del producto | Sí (para búsqueda por nombre) |
| `ean` | Código de barras EAN-13 | Sí (para resolución de marcas) |
| `marca` | Marca comercial | No |
| `categoria` | Categoría del producto | No |

> **Nota:** Los nombres de columna son configurables en la pantalla de configuración del job. Si tu CSV usa nombres distintos (ej. `ref`, `descripcion`), puedes mapearlos sin modificar el fichero.

---

## 3. Acceso a la aplicación

Abre tu navegador y navega a la URL de Harvist. En desarrollo local:

```
http://localhost:5173
```

No se requiere autenticación en la versión actual (acceso por red local o VPN).

---

## 4. Dashboard principal

Al acceder a Harvist, verás el **dashboard principal** con cuatro módulos:

```
┌─────────────────────────────────────────────────────────────────┐
│                    HARVIST                                       │
│         Plataforma de enriquecimiento de catálogos              │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│   HARVIST    │   DOLIBARR   │    ODOO      │   WORDPRESS        │
│  Scraping +  │  ERP         │  ERP         │  WooCommerce       │
│  IA + Marcas │  Integration │  Integration │  Integration       │
└──────────────┴──────────────┴──────────────┴────────────────────┘
```

Haz clic en cualquier módulo para acceder a su panel. Cada panel tiene una **barra de navegación (breadcrumb)** en la parte superior para volver atrás.

---

## 5. Módulo Harvist — Enriquecimiento de catálogos

Este módulo es el núcleo de la plataforma. Ejecuta **jobs** (trabajos) que procesan tu CSV y generan imágenes, descripciones y marcas.

### 5.1 Preparar el CSV de inventario

Tu CSV debe:

1. Tener **cabecera** en la primera fila
2. Usar **punto y coma** (`;`) o **coma** (`,`) como separador
3. Estar en codificación **UTF-8**

Ejemplo mínimo:

```csv
codigo;nombre;ean;marca
REF001;Taladro percutor 700W;8410919001234;Bosch
REF002;Destornillador eléctrico;8410919005678;Makita
REF003;Sierra circular;8410919009012;DeWalt
```

### 5.2 Subir el CSV

1. En el módulo Harvist, haz clic en la zona de **subida de CSV** (zona de arrastrar y soltar)
2. Arrastra tu fichero CSV o haz clic para seleccionarlo
3. Harvist valida el formato automáticamente y muestra las columnas detectadas

### 5.3 Configurar el job

Tras subir el CSV aparece el formulario de configuración. Las opciones principales son:

#### Tipo de job

| Tipo | Qué genera |
|------|-----------|
| **FOTOS** | Solo descarga imágenes |
| **DESCRIPCIONES** | Solo genera textos con IA |
| **MARCAS** | Solo resuelve marcas por EAN |
| **Completo** | Los tres tipos combinados |

#### Modo de búsqueda de imágenes

| Modo | Descripción |
|------|-------------|
| **NOMBRE** | Busca por nombre del producto |
| **NOMBRE_MARCA** | Busca por nombre + marca (más preciso) |
| **EAN** | Busca directamente por código EAN |
| **PERSONALIZADO** | Define tu propia plantilla de búsqueda |

#### Número de imágenes por producto

Define cuántas imágenes descargar por referencia (1-10). Si activas **selección de fotos**, se descargan las candidatas y tú eliges la definitiva.

#### Proveedor de IA

- **Groq** (llama-3.3-70b): más rápido, requiere API key de Groq
- **Claude** (Anthropic): mayor calidad, requiere API key de Anthropic

Puedes introducir tu API key directamente en el formulario. También puedes dejar vacío si está configurada globalmente en el servidor.

#### Idiomas para traducción

Selecciona los idiomas a los que traducir las descripciones:
- Español (ES) — base
- Inglés (EN)
- Francés (FR)
- Alemán (DE)
- Italiano (IT)
- Portugués (PT)

#### Mapeo de columnas

Si tus columnas no tienen los nombres estándar, usa el mapeo:

| Campo | Tu columna |
|-------|-----------|
| Código | `referencia` (si no se llama `codigo`) |
| EAN | `barcode` (si no se llama `ean`) |
| Nombre | `descripcion` (si no se llama `nombre`) |
| Marca | `fabricante` (si no se llama `marca`) |

#### Opciones avanzadas

| Opción | Descripción |
|--------|-------------|
| **Validación de marcas** | Activa revisión manual antes de guardar nuevas marcas en caché |
| **Selección de fotos** | Descarga varias candidatas y permite elegir manualmente |

Una vez configurado, haz clic en **Iniciar job**.

### 5.4 Seguimiento en tiempo real

Tras lanzar el job, aparece el **panel de progreso** con:

- Barra de porcentaje
- Estado actual (Pendiente → En proceso → Completado)
- Métricas en tiempo real:
  - Productos procesados / Total
  - Imágenes descargadas
  - Imágenes fallidas
  - Descripciones generadas
  - Marcas procesadas

La actualización es **automática vía WebSocket** — no necesitas recargar la página.

#### Estados posibles de un job

| Estado | Significado |
|--------|------------|
| PENDIENTE | En cola, esperando trabajador disponible |
| EN_PROCESO | Ejecutándose activamente |
| COMPLETADO | Terminado con éxito |
| FALLIDO | Error durante el procesamiento |
| CANCELADO | Detenido por el usuario |
| PENDIENTE_VALIDACIÓN_MARCAS | Esperando revisión manual de marcas nuevas |
| PENDIENTE_SELECCIÓN_FOTOS | Esperando que el usuario elija las fotos definitivas |

#### Cancelar un job

Haz clic en **Cancelar** para detener un job en proceso. Puedes **reanudar** un job cancelado — el sistema retoma desde el último producto procesado.

### 5.5 Panel de marcas

Una vez completado (o en estado COMPLETADO), accede al **Panel de Marcas** para ver el resultado de la resolución EAN → marca:

La tabla muestra por cada producto:
- **Código** — referencia interna
- **EAN** — código de barras
- **Marca resuelta** — nombre de la marca encontrada
- **Fabricante** — fabricante si se encontró
- **Fuente** — de dónde se obtuvo la información (Amazon, OpenFoodFacts, GS1, etc.)
- **Confianza** — alta / media / baja

Puedes filtrar por fuente y por nivel de confianza. El botón **Descargar marcas.csv** exporta los resultados.

#### Cascada de resolución de marcas

Harvist intenta resolver la marca en este orden:

1. Validación de checksum GS1 (Módulo 10)
2. Caché local de prefijos GS1 conocidos
3. Amazon.es
4. Open Pet Food Facts
5. Open Food Facts
6. UPCItemDb
7. Google Dorking
8. Bing Search
9. No encontrado

### 5.6 Revisión de descripciones

Si el job incluía generación de descripciones y tienes activada la revisión manual:

El **Panel de Revisión** muestra cada producto con su descripción generada por IA. Para cada uno puedes:

- ✅ **Aprobar** — la descripción pasa tal cual al CSV de exportación
- ✏️ **Editar** — modifica el texto directamente en la tabla y aprueba
- ❌ **Rechazar** — la descripción se excluye del CSV de exportación

Puedes descargar solo las descripciones aprobadas usando el botón **Descargar CSV** (con filtro `Solo aprobadas`).

### 5.7 Validación de marcas

Si activaste **Validación de marcas** en la configuración, el job pasa a estado `PENDIENTE_VALIDACIÓN_MARCAS` tras resolver las marcas nuevas (no presentes en caché).

El **Panel de Validación de Marcas** muestra cada marca nueva para revisión:

- **EAN** — código de barras
- **Marca propuesta** — nombre encontrado por Harvist
- Acciones: **Aceptar** / **Rechazar** / **Editar nombre**

Las marcas aceptadas (y editadas) se escriben en el caché local de GS1 para futuros jobs. Las rechazadas se descartan sin guardar.

Haz clic en **Confirmar validación** para continuar el job.

### 5.8 Selección de fotos

Si activaste **Selección de fotos**, el job se detiene en `PENDIENTE_SELECCIÓN_FOTOS` tras descargar todas las candidatas.

El **Panel de Selección de Fotos** muestra una cuadrícula por producto con las imágenes candidatas:

```
Producto: Taladro percutor 700W  [REF001]
┌─────────┐  ┌─────────┐  ┌─────────┐
│  Foto 1 │  │  Foto 2 │  │  Foto 3 │
│  [✓]    │  │  [ ]    │  │  [ ]    │
└─────────┘  └─────────┘  └─────────┘
```

Selecciona la foto más adecuada para cada producto. Haz clic en **Confirmar selección** — el sistema elimina las candidatas no elegidas y genera el ZIP definitivo.

### 5.9 Descargar resultados

Una vez el job está en estado COMPLETADO, los botones de descarga están activos:

| Botón | Contenido |
|-------|-----------|
| **Descargar ZIP** | Todas las imágenes seleccionadas en un archivo .zip |
| **Descargar CSV descripciones** | Fichero CSV con todos los textos generados |
| **Descargar CSV SEO** | Meta-títulos y meta-descripciones (≤60 / ≤160 chars) |
| **Descargar marcas** | CSV con EAN, marca, fuente y confianza |
| **Descargar traducciones [idioma]** | CSV con textos en el idioma seleccionado |

Los ficheros tienen una **vigencia de 7 días** por defecto. Transcurrido ese tiempo, se eliminan del servidor.

### 5.10 Historial de jobs

El historial muestra todos los jobs ejecutados, con paginación. Puedes:

- Ver el estado de cada job
- Acceder a los resultados de jobs anteriores (mientras estén disponibles)
- Ver la fecha de creación y finalización
- Volver a descargar resultados de jobs completados

---

## 6. Módulo Dolibarr

### 6.1 Configuración de conexión

Antes de usar el módulo Dolibarr, configura las credenciales:

1. Ve a **Dolibarr → Configuración**
2. Introduce:
   - **URL de Dolibarr** — ej. `https://mi-dolibarr.empresa.com`
   - **API Key** — clave DOLAPIKEY de tu usuario Dolibarr
3. Haz clic en **Guardar y verificar conexión**

Si la conexión es correcta, verás un indicador verde con la versión de Dolibarr detectada.

### 6.2 Productos

El panel de productos permite:

- **Listar** todos los productos de Dolibarr (paginado)
- **Buscar** por nombre o referencia
- **Ver** detalle de cada producto
- **Crear** nuevos productos con formulario completo
- **Editar** referencia, nombre, precio, descripción, categoría, marca
- **Subir imagen** de producto
- **Eliminar** productos

### 6.3 Categorías

Visualiza y gestiona la jerarquía de categorías de Dolibarr:

- Vista de **árbol** con categorías padre/hijo
- **Crear** categoría (con padre opcional)
- **Editar** nombre y descripción
- **Asignar/quitar** productos a una categoría
- **Eliminar** categoría

### 6.4 Marcas

Gestión de marcas como entidad independiente en Dolibarr:

- Listar todas las marcas registradas
- Crear nueva marca
- Editar nombre
- Eliminar

### 6.5 Proveedores y clientes

Panel de terceros (thirdparties):

- Listar con filtros (tipo: proveedor / cliente / ambos)
- Crear nuevo tercero con datos fiscales completos
- Editar datos de contacto, dirección, NIF
- Eliminar tercero

### 6.6 Pedidos

Gestión de pedidos de compra:

- Listar pedidos con filtros de estado y fecha
- Ver detalle de cada pedido con sus líneas
- Crear nuevo pedido de compra
- Eliminar pedido

### 6.7 Facturas

Gestión completa del ciclo de facturación:

- Listar facturas con filtros de tipo y estado
- Ver detalle con líneas de factura
- Crear factura nueva
- Añadir líneas a factura existente
- **Validar** factura (marcar como emitida)
- **Enviar** por email al cliente
- **Registrar pago**
- Eliminar factura

### 6.8 Stock

Gestión de almacenes y movimientos:

- **Almacenes** — listar todos los almacenes, ver detalle
- **Stock por producto** — consultar nivel de stock en cada almacén
- **Movimientos** — historial de entradas y salidas
- **Crear movimiento** — ajuste manual de stock
- **Transferir** stock entre almacenes

### 6.9 Campos extra

Gestión de campos personalizados (extrafields) de productos:

- Ver todos los campos extra definidos en Dolibarr
- Ver valores actuales por producto
- Editar valores de campos extra

### 6.10 Sincronización Harvist → Dolibarr

Desde un job completado, puedes sincronizar directamente a Dolibarr:

1. Selecciona el job en el historial
2. Haz clic en **Exportar a Dolibarr**
3. Elige qué sincronizar: imágenes, descripciones, marcas, categorías
4. Confirma — Harvist crea/actualiza los productos en Dolibarr

La sincronización es **bidireccional**: también puedes importar productos de Dolibarr para enriquecerlos con Harvist.

---

## 7. Módulo Odoo

### 7.1 Configuración de conexión

1. Ve a **Odoo → Configuración**
2. Introduce:
   - **URL de Odoo** — ej. `https://mi-odoo.empresa.com`
   - **Base de datos** — nombre de la BD Odoo
   - **Usuario** — email de tu usuario Odoo
   - **Contraseña** — contraseña o API key
3. Haz clic en **Guardar y verificar**

### 7.2 Productos

Panel de productos Odoo:

- Listar con paginación y búsqueda
- Ver/editar producto por ID o por referencia interna (`default_code`)
- Crear producto con atributos y variantes
- Actualizar precio, descripción, imagen
- Eliminar producto

### 7.3 Categorías y eCommerce

**Categorías internas** (árbol de categorías de producto Odoo):
- Visualizar jerarquía
- Crear / editar / eliminar

**Categorías eCommerce** (`product.public.category`):
- Categorías para la tienda online de Odoo
- Crear / editar

### 7.4 Marcas

Gestión de marcas en Odoo:

- Listar marcas registradas
- Crear nueva marca
- Editar / eliminar

### 7.5 Partners

Gestión de clientes y proveedores:

- Listar con filtro por tipo (cliente / proveedor / empleado)
- Crear con datos fiscales completos
- Editar dirección, teléfono, email, NIF
- Eliminar

### 7.6 Compras y ventas

**Pedidos de compra:**
- Listar, ver detalle, crear
- Confirmar pedido → estado "Purchase Order"
- Cancelar pedido

**Pedidos de venta:**
- Listar, ver detalle, crear
- Confirmar venta → genera albarán
- Cancelar

### 7.7 Inventario

Consulta de stock:

- **Niveles de stock** — por producto y ubicación
- **Ubicaciones** — listar todos los almacenes y ubicaciones
- **Stock de un producto** — ver cantidades en todas las ubicaciones

### 7.8 Facturas

Ciclo completo de facturación:

- Facturas de cliente y facturas de proveedor (filtrar por tipo)
- Crear, ver detalle
- **Validar** → estado "Posted"
- **Cancelar** factura validada

### 7.9 Campos extra y propiedades

**Campos extra** (`ir.model.fields`):
- Ver campos personalizados definidos para productos
- Editar valores

**Propiedades de producto** (atributos dinámicos):
- Listar atributos y sus valores posibles
- Crear nuevos atributos
- Editar / eliminar

**Importación CSV:**
- Importar productos desde CSV directamente a Odoo sin pasar por un job de Harvist

---

## 8. Módulo WordPress / WooCommerce

### 8.1 Configuración REST API

1. Ve a **WordPress → Configuración**
2. Introduce credenciales REST de WooCommerce:
   - **URL de WordPress** — ej. `https://mi-tienda.com`
   - **Consumer Key** — clave WC de la API REST
   - **Consumer Secret** — secreto WC de la API REST
   - **Usuario de aplicación** — usuario de WordPress
   - **Contraseña de aplicación** — contraseña de aplicación (WordPress 5.6+)
3. Haz clic en **Guardar y verificar**

Para obtener las credenciales WooCommerce: WooCommerce → Ajustes → Avanzado → REST API → Agregar clave.

### 8.2 Configuración base de datos

Si necesitas acceso directo a la base de datos MySQL de WordPress:

1. Ve a **WordPress → Base de datos → Configuración MySQL**
2. Introduce:
   - Host, puerto, nombre de BD, usuario, contraseña
   - Prefijo de tablas (por defecto `wp_`)
3. Guarda la configuración

> **Nota:** Esta configuración es opcional. La mayoría de operaciones funcionan solo con la API REST.

### 8.3 Productos

Panel de productos WooCommerce:

- Listar con paginación, búsqueda y filtro por estado
- Ver detalle con imágenes, atributos, variantes, precio
- Crear producto simple o variable
- Editar nombre, descripción, precio, stock, categorías, imágenes
- Eliminar producto

### 8.4 Categorías y marcas

**Categorías:**
- Visualizar árbol de taxonomía de WooCommerce
- Crear / editar / eliminar categorías
- Ver productos de una categoría

**Marcas:**
- Gestión mediante atributo `pa_brand` de WooCommerce
- Crear, editar, eliminar marcas
- Asignar marcas a productos

### 8.5 Pedidos y clientes

**Pedidos:**
- Listar con filtro por estado (pendiente, procesando, completado, cancelado, etc.)
- Ver detalle completo con productos, dirección, totales
- Actualizar estado del pedido
- Añadir notas internas

**Clientes:**
- Listar cuentas de cliente registradas
- Ver perfil, historial de pedidos, direcciones
- Crear nuevo cliente
- Editar datos de contacto y dirección
- Eliminar cuenta

### 8.6 Media

Gestión de adjuntos de WordPress:

- Listar todos los adjuntos (imágenes, documentos)
- **Subir archivo** — sube imágenes de producto directamente a la biblioteca de medios
- Ver URL y metadatos de cada adjunto

### 8.7 Base de datos directa

Consultas directas a la base de datos MySQL de WordPress:

- **Tablas** — listar todas las tablas con su número de filas
- **Información del sitio** — versión WordPress, plugins activos, tema
- **Consulta SQL** — ejecutar SELECT personalizado (solo lectura)
- **Opciones** — leer cualquier opción de `wp_options` por nombre

> **Advertencia:** Las consultas directas son de solo lectura. No se pueden ejecutar INSERT, UPDATE ni DELETE desde este panel.

### 8.8 Sincronización Harvist → WordPress

Desde un job completado:

1. Selecciona el job en el historial
2. Haz clic en **Exportar a WordPress**
3. Harvist sube:
   - Imágenes → biblioteca de medios de WordPress
   - Asigna imágenes a los productos correspondientes
   - Actualiza descripciones y textos SEO
   - Crea/actualiza marcas como atributo `pa_brand`
   - Asigna categorías

La sincronización también es **bidireccional** con Dolibarr.

---

## 9. Flujo de trabajo completo

Este es el flujo recomendado para enriquecer un catálogo y publicarlo en WooCommerce:

```
1. PREPARAR CSV
   └── Exporta tu catálogo desde tu ERP o Excel
       Asegúrate de tener: codigo, nombre, ean, marca

2. SUBIR Y CONFIGURAR JOB en Harvist
   └── Tipo: Completo (fotos + descripciones + marcas)
   └── Modo: NOMBRE_MARCA (mejor precisión)
   └── Imágenes: 3 candidatas (si usas selección)
   └── IA: Groq o Claude
   └── Idiomas: ES + EN (si tienes tienda multilingüe)
   └── Activar: Validación de marcas + Selección de fotos

3. ESPERAR EL PROCESAMIENTO
   └── Harvist descarga imágenes, genera textos, resuelve marcas

4. VALIDAR MARCAS (si lo activaste)
   └── Revisar marcas nuevas, aceptar/editar/rechazar
   └── Confirmar validación

5. SELECCIONAR FOTOS (si lo activaste)
   └── Para cada producto, elegir la mejor imagen candidata
   └── Confirmar selección → se genera el ZIP definitivo

6. REVISAR DESCRIPCIONES (si tienes revisión activada)
   └── Aprobar, editar o rechazar textos por producto

7. DESCARGAR RESULTADOS
   └── ZIP de imágenes
   └── CSV de descripciones
   └── CSV de marcas

8. EXPORTAR A ERP/CMS
   └── Exportar a Dolibarr: productos + imágenes + categorías
   └── Exportar a WordPress: productos + imágenes + descripciones + marcas
   └── Exportar a Odoo: productos + atributos
```

---

## 10. Preguntas frecuentes

### ¿Por qué algunas imágenes no se descargan?

Las imágenes pueden no descargarse por:
- El motor de búsqueda no encontró resultados para ese producto
- La imagen descargada no cumple los requisitos mínimos de tamaño (configurable)
- El servidor de origen bloqueó la descarga

Revisa el panel de progreso — el campo "Imágenes fallidas" indica cuántos productos no se pudieron procesar.

### ¿Cuánto tarda un job?

Depende del número de productos y las opciones activadas:

| Productos | Solo fotos | Fotos + descripciones |
|-----------|-----------|----------------------|
| 100 | ~5-10 min | ~15-20 min |
| 500 | ~25-45 min | ~60-90 min |
| 1000 | ~50-90 min | ~2-3 horas |

Los tiempos son aproximados y dependen de la velocidad de internet y la carga del servidor.

### ¿Se puede pausar un job?

Sí. Haz clic en **Cancelar** y luego en **Reanudar**. El sistema retoma desde el último producto procesado, sin repetir trabajo ya hecho.

### ¿Los resultados se guardan para siempre?

No. Los ficheros de un job tienen una vigencia de **7 días** por defecto. Después se eliminan del servidor automáticamente. Descarga tus resultados antes de que expiren.

### ¿Qué pasa si la IA no genera una buena descripción?

Usa el **Panel de Revisión** para editar manualmente cualquier descripción antes de exportar. También puedes rechazar la descripción y escribir una propia.

### ¿Puedo usar mis propias API keys de IA?

Sí. En la configuración del job puedes introducir tu propia API key de Groq o Claude. Esto permite usar tu cuota personal y controlar el gasto.

### ¿El módulo Dolibarr/Odoo/WordPress es opcional?

Sí. Puedes usar Harvist únicamente para descargar imágenes y generar descripciones, sin conectar ningún ERP o CMS. Los módulos de integración son independientes y opcionales.

### ¿Qué significa "confianza baja" en las marcas?

Indica que la marca se obtuvo de una fuente menos fiable (ej. Google Dorking) o que el nombre encontrado no fue validado. Revisa esas marcas manualmente en el Panel de Validación de Marcas.

---

*Harvist — Nubium Solutions*  
*Para soporte técnico, contacta con el equipo en benjamin.pk02@gmail.com*
