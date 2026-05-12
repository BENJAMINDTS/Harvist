/**
 * Cliente HTTP Axios configurado para la API de Harvist.
 *
 * Base URL apunta a /api/v1 — en desarrollo el proxy de Vite reenvía
 * las peticiones al backend FastAPI en localhost:8000.
 * En producción el servidor inverso (nginx) maneja el routing.
 *
 * Todos los endpoints deben usar este cliente, nunca instanciar Axios
 * directamente en los componentes.
 *
 * @author BenjaminDTS | Carlos Vico
 */
import axios, { type AxiosInstance, type AxiosError } from 'axios'
import {
  type IntegrationStatus,
  type PaginatedResponse,
  type DolibarrProduct,
  type DolibarrThirdparty,
  type DolibarrOrder,
  type DolibarrInvoice,
  type DolibarrWarehouse,
  type SyncFromJobRequest,
  type ThirdpartyMode,
  type OrderType,
  type InvoiceType,
  type DolibarrFieldSchema,
  type DolibarrDBConfig,
  type DolibarrDBConfigCreate,
  type DolibarrExtraField,
  type DolibarrExtraFieldCreate,
  type CsvImportPreview,
  type DolibarrStats,
  type DolibarrCategory,
  type DolibarrCategoryTree,
  type DolibarrImportTask,
} from '@/types/dolibarr'
import {
  type OdooProduct,
  type OdooCategory,
  type OdooPartner,
  type OooPurchase,
  type OdooSale,
  type OdooInvoice,
  type OdooStockLine,
  type OdooLocation,
  type OdooConfigRequest,
  type OdooConfigResponse,
  type PartnerMode,
  type OdooInvoiceType,
  type OdooPropertyDefinition,
  type OdooPropertyValue,
} from '@/types/odoo'

/** Estructura estándar de respuesta de la API */
export interface ApiResponse<T = unknown> {
  success: boolean
  data: T
  message: string
}

/** Error normalizado devuelto al caller cuando la petición falla */
export interface ApiError {
  status: number
  message: string
  detail?: string
}

const BASE_URL = '/api/v1'

/**
 * Instancia Axios con configuración base compartida por toda la app.
 *
 * - timeout: 30s (las subidas de CSV pueden tardar en redes lentas)
 * - Content-Type por defecto: application/json
 *   (se sobreescribe a multipart/form-data en las llamadas con FormData)
 */
export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: {
    Accept: 'application/json',
  },
})

/**
 * Interceptor de respuesta: normaliza los errores HTTP en ApiError
 * para que los componentes no tengan que inspeccionar el objeto Axios.
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; message?: string }>) => {
    const apiError: ApiError = {
      status: error.response?.status ?? 0,
      message:
        error.response?.data?.detail ??
        error.response?.data?.message ??
        error.message ??
        'Error desconocido.',
    }
    return Promise.reject(apiError)
  },
)

/**
 * Construye la URL del WebSocket de progreso para un job dado.
 *
 * Usa el mismo host/port que la página actual para funcionar tanto
 * en desarrollo (con proxy Vite) como en producción.
 *
 * @param jobId - Identificador UUID del job.
 * @returns URL completa del WebSocket (ws:// o wss://).
 */
export function buildWsUrl(jobId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = window.location.host
  return `${protocol}://${host}/api/v1/jobs/${jobId}/ws`
}

/** Datos devueltos por el endpoint de reanudación de un job. */
export interface ResumeJobData {
  job_id: string
  estado: string
  ws_url: string
}

/**
 * Reanuda un job cancelado o fallido creando un nuevo job a partir del anterior.
 *
 * Llama a `POST /api/v1/jobs/{jobId}/resume` y devuelve el identificador
 * del nuevo job junto con su estado inicial y URL de WebSocket.
 *
 * @param jobId - UUID del job a reanudar.
 * @returns Datos del nuevo job creado.
 * @throws ApiError si la petición falla o el job no puede reanudarse.
 */
export async function resumeJob(jobId: string): Promise<ResumeJobData> {
  const response = await apiClient.post<ApiResponse<ResumeJobData>>(
    `/jobs/${jobId}/resume`,
  )
  return response.data.data
}

/** Fuentes posibles de resolución EAN→marca (valores del backend). */
export type BrandSource =
  | 'amazon'
  | 'cache_gs1'
  | 'open_data_api'
  | 'google_dorking'
  | 'bing_search'
  | 'not_found'
  | 'ean_invalido'

/** Entrada de marca resuelta para un producto. */
export interface BrandEntry {
  codigo: string
  ean: string
  brand_name: string | null
  manufacturer: string | null
  source: BrandSource
  confidence: 'high' | 'medium' | 'low'
}

/** Respuesta del endpoint GET /jobs/{jobId}/brands. */
export interface BrandsData {
  brands: BrandEntry[]
  brands_resolved: number
  brands_not_found: number
}

/**
 * Obtiene la lista de marcas resueltas para un job.
 *
 * @author BenjaminDTS
 * @param jobId - ID del job.
 * @returns Array de BrandEntry con todas las marcas procesadas.
 */
export async function getBrands(jobId: string): Promise<BrandEntry[]> {
  const response = await apiClient.get<ApiResponse<BrandsData>>(
    `/jobs/${jobId}/brands`,
  )
  return response.data.data.brands
}

/**
 * Descarga el CSV de marcas para un job como Blob.
 *
 * @author BenjaminDTS
 * @param jobId - ID del job.
 * @returns Blob con el contenido del CSV.
 */
export async function downloadBrandsCsv(jobId: string): Promise<Blob> {
  const response = await apiClient.get<Blob>(
    `/files/${jobId}/brands`,
    { responseType: 'blob' },
  )
  return response.data
}

/**
 * Descarga el CSV de traducciones para un idioma destino (Fase 7.2).
 *
 * @param jobId - Identificador UUID del job.
 * @param lang  - Código ISO 639-1 del idioma (ej: 'en', 'fr').
 * @returns Blob con el contenido del CSV de traducciones.
 */
export async function downloadTranslationCsv(jobId: string, lang: string): Promise<Blob> {
  const response = await apiClient.get<Blob>(
    `/files/${jobId}/translations/${lang}`,
    { responseType: 'blob' },
  )
  return response.data
}

// ─── Revisión de descripciones (Fase 7.3) ────────────────────────────────────

/** Acción de revisión aplicada a una descripción. */
export type ReviewAction = 'approve' | 'reject' | 'edit'

/** Estado de revisión de una descripción. */
export type ReviewStatus = 'pending' | 'approved' | 'rejected'

/** Body de la petición PATCH para revisar una descripción. */
export interface DescriptionReviewRequest {
  action: ReviewAction
  edited_text?: string
}

/** Estado de revisión devuelto por el endpoint PATCH. */
export interface DescriptionReviewState {
  codigo: string
  status: ReviewStatus
  edited_text: string | null
}

/** Entrada enriquecida devuelta por GET /jobs/{jobId}/descriptions/review. */
export interface DescriptionReviewEntry extends DescriptionReviewState {
  nombre: string
  descripcion_corta: string
  descripcion_larga: string
}

/** Respuesta paginada del endpoint GET /jobs/{jobId}/descriptions/review. */
export interface DescriptionReviewPage {
  items: DescriptionReviewEntry[]
  total: number
  limit: number
  offset: number
}

/**
 * Envía acción de revisión para una descripción individual.
 *
 * Llama a `PATCH /api/v1/jobs/{jobId}/descriptions/{codigo}` con la acción
 * y, opcionalmente, el texto editado (requerido cuando action='edit').
 *
 * @author Carlitos6712
 * @param jobId   - UUID del job.
 * @param codigo  - Código del producto a revisar.
 * @param request - Acción y texto editado.
 * @returns Estado de revisión actualizado.
 */
export async function reviewDescription(
  jobId: string,
  codigo: string,
  request: DescriptionReviewRequest,
): Promise<DescriptionReviewState> {
  const response = await apiClient.patch<ApiResponse<DescriptionReviewState>>(
    `/jobs/${jobId}/descriptions/${encodeURIComponent(codigo)}`,
    request,
  )
  return response.data.data
}

/**
 * Obtiene estado de revisión de todas las descripciones de un job (paginado).
 *
 * Llama a `GET /api/v1/jobs/{jobId}/descriptions/review`.
 *
 * @author Carlitos6712
 * @param jobId  - UUID del job.
 * @param limit  - Máximo de registros por página (1-100, por defecto 25).
 * @param offset - Registros a saltar (por defecto 0).
 * @returns Página de DescriptionReviewEntry.
 */
export async function getReviewStatus(
  jobId: string,
  limit = 25,
  offset = 0,
): Promise<DescriptionReviewPage> {
  const response = await apiClient.get<ApiResponse<DescriptionReviewPage>>(
    `/jobs/${jobId}/descriptions/review`,
    { params: { limit, offset } },
  )
  return response.data.data
}

/**
 * Descarga CSV con solo las descripciones aprobadas (Fase 7.3).
 *
 * Llama a `GET /api/v1/files/{jobId}/csv?only_approved=true`.
 * Devuelve null si el backend responde 204 (sin aprobadas).
 *
 * @author Carlitos6712
 * @param jobId - UUID del job.
 * @returns Blob con el CSV filtrado, o null si no hay aprobadas.
 */
export async function downloadApprovedCsv(jobId: string): Promise<Blob | null> {
  const response = await apiClient.get<Blob>(
    `/files/${jobId}/csv`,
    { params: { only_approved: true }, responseType: 'blob' },
  )
  if (response.status === 204) return null
  return response.data
}

// ─── Validación de marcas (Fase 7.4) ─────────────────────────────────────────

/** Acción del usuario sobre una marca pendiente de validación. */
export type BrandValidationAction = 'accept' | 'reject' | 'edit'

/** Marca nueva pendiente de validación antes de persistirse en brand_cache.json. */
export interface BrandPendingEntry {
  /** Código EAN del producto. */
  ean: string
  /** Nombre de marca resuelto por el scraper. */
  brand_name: string
  /** Fuente que resolvió el EAN. */
  source: BrandSource
  /** Nivel de confianza del resultado. */
  confidence: 'high' | 'medium' | 'low'
  /** Primeros 7 dígitos del EAN (prefijo GS1). */
  prefijo: string
}

/** Item de validación enviado al backend. */
export interface BrandValidationItem {
  ean: string
  brand_name: string
  action: BrandValidationAction
  edited_name?: string
}

/** Body de POST /jobs/{jobId}/brands/validate. */
export interface BrandValidationRequest {
  items: BrandValidationItem[]
}

/** Respuesta del endpoint de validación. */
export interface BrandValidationResult {
  accepted: number
  rejected: number
  edited: number
}

/**
 * Obtiene las marcas pendientes de validación para un job.
 *
 * Llama a `GET /api/v1/jobs/{jobId}/brands/pending`.
 * Devuelve la lista de marcas nuevas en espera de aprobación.
 *
 * @author Carlitos6712
 * @param jobId - ID del job en PENDIENTE_VALIDACION_MARCAS.
 * @returns Lista de BrandPendingEntry.
 */
export async function getBrandsPending(jobId: string): Promise<BrandPendingEntry[]> {
  const response = await apiClient.get<ApiResponse<{ items: BrandPendingEntry[] }>>(
    `/jobs/${jobId}/brands/pending`,
  )
  return response.data.data.items
}

/**
 * Envía la validación de marcas nuevas para un job.
 *
 * Solo los items con action != 'reject' se escriben en brand_cache.json.
 * Llama a `POST /api/v1/jobs/{jobId}/brands/validate`.
 *
 * @author Carlitos6712
 * @param jobId   - ID del job en PENDIENTE_VALIDACION_MARCAS.
 * @param request - Lista de marcas con su decisión.
 * @returns Resumen de marcas aceptadas, rechazadas y editadas.
 */
export async function validateBrands(
  jobId: string,
  request: BrandValidationRequest,
): Promise<BrandValidationResult> {
  const response = await apiClient.post<ApiResponse<BrandValidationResult>>(
    `/jobs/${jobId}/brands/validate`,
    request,
  )
  return response.data.data
}

// ─── Selección de fotos (Fase 7.5) ────────────────────────────────────────

/** Información de una candidata de foto para un producto. */
export interface CandidateInfo {
  index: number
  url: string
  width: number
  height: number
  size_bytes: number
}

/** Datos de un producto con sus fotos candidatas. */
export interface ProductPhotos {
  codigo: string
  nombre: string
  n_candidates: number
  candidates: CandidateInfo[]
  selected_index: number | null
}

/** Item de selección de foto enviado al backend. */
export interface PhotoSelectionItem {
  codigo: string
  selected_index: number
}

/** Body de POST /jobs/{jobId}/photos/confirm. */
export interface PhotoConfirmRequest {
  selections: PhotoSelectionItem[]
}

/** Respuesta del endpoint de confirmación de fotos. */
export interface PhotoConfirmResult {
  confirmadas: number
  zip_listo: boolean
}

/**
 * Obtiene la lista de productos con sus candidatas disponibles.
 *
 * Llama a `GET /api/v1/jobs/{jobId}/photos` y devuelve los productos con las fotos
 * candidatas descargadas y disponibles para selección.
 *
 * @author BenjaminDTS
 * @param jobId - ID del job en PENDIENTE_SELECCION_FOTOS.
 * @param limit - Opcional. Máximo de productos a retornar (default: sin límite).
 * @param offset - Opcional. Productos a saltar para paginación (default: 0).
 * @returns Lista de ProductPhotos con todas las candidatas y selecciones actuales.
 */
export async function getJobPhotos(
  jobId: string,
  limit?: number,
  offset?: number,
): Promise<ProductPhotos[]> {
  const params: Record<string, unknown> = {}
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset

  const response = await apiClient.get<ApiResponse<ProductPhotos[]>>(
    `/jobs/${jobId}/photos`,
    { params },
  )
  return response.data.data
}

/**
 * Confirma la selección de fotos y genera el ZIP final.
 *
 * Llama a `POST /api/v1/jobs/{jobId}/photos/confirm` con el mapeo de productos
 * a índices de candidata seleccionados. Las candidatas no seleccionadas se eliminan
 * del disco, el ZIP se genera, y el job avanza de estado.
 *
 * @author BenjaminDTS
 * @param jobId - ID del job en PENDIENTE_SELECCION_FOTOS.
 * @param selections - Array de { codigo, selected_index } indicando la foto elegida por producto.
 * @returns Resumen con número de confirmadas y si el ZIP está listo.
 */
export async function confirmPhotoSelection(
  jobId: string,
  selections: PhotoSelectionItem[],
): Promise<PhotoConfirmResult> {
  const response = await apiClient.post<ApiResponse<PhotoConfirmResult>>(
    `/jobs/${jobId}/photos/confirm`,
    { selections },
  )
  return response.data.data
}

// ────────────────────────────────────────────────────────────────
// DOLIBARR — Métodos de integración
// ────────────────────────────────────────────────────────────────

/**
 * Obtiene el estado de conexión a Dolibarr.
 *
 * @author BenjaminDTS
 * @returns Estado con plataforma, configuración y salud.
 */
export async function getDolibarrStatus(): Promise<IntegrationStatus> {
  const response = await apiClient.get<IntegrationStatus>('/dolibarr/status')
  return response.data
}

/**
 * Obtiene estadísticas resumidas de Dolibarr (terceros y facturas).
 *
 * @author BenjaminDTS | Carlos Vico
 * @returns DolibarrStats con conteos de terceros e invoices, o configured=false si no hay config.
 */
export async function getDolibarrStats(): Promise<DolibarrStats> {
  const response = await apiClient.get<ApiResponse<DolibarrStats>>('/dolibarr/stats')
  return response.data.data
}

/**
 * Obtiene el schema dinámico de campos para productos de esta instancia Dolibarr.
 * Incluye campos estándar y extra fields configurados.
 *
 * @author BenjaminDTS
 * @returns Lista de DolibarrFieldSchema con metadata de cada campo.
 */
export async function getDolibarrProductFields(): Promise<DolibarrFieldSchema[]> {
  const response = await apiClient.get<ApiResponse<DolibarrFieldSchema[]>>(
    '/dolibarr/products/fields',
  )
  return response.data.data
}

/**
 * Lista productos de Dolibarr con paginación.
 *
 * @author BenjaminDTS
 * @param limit - Máximo de productos a retornar.
 * @param offset - Productos a saltar para paginación.
 * @returns Respuesta paginada de productos.
 */
export async function listDolibarrProducts(
  limit?: number,
  offset?: number,
  search?: string,
): Promise<PaginatedResponse<DolibarrProduct>> {
  const params: Record<string, unknown> = {}
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (search) params.search = search

  const response = await apiClient.get<
    ApiResponse<PaginatedResponse<DolibarrProduct>>
  >('/dolibarr/products', { params })
  return response.data.data
}

/**
 * Obtiene un producto específico de Dolibarr por ID.
 *
 * @author BenjaminDTS
 * @param id - ID del producto.
 * @returns Datos del producto.
 */
export async function getDolibarrProduct(id: number): Promise<DolibarrProduct> {
  const response = await apiClient.get<ApiResponse<DolibarrProduct>>(
    `/dolibarr/products/${id}`,
  )
  return response.data.data
}

/**
 * Crea un nuevo producto en Dolibarr.
 *
 * @author BenjaminDTS
 * @param data - Datos parciales del producto.
 * @returns Producto creado.
 */
export async function createDolibarrProduct(
  data: Partial<DolibarrProduct>,
): Promise<DolibarrProduct> {
  const response = await apiClient.post<ApiResponse<DolibarrProduct>>(
    '/dolibarr/products',
    data,
  )
  return response.data.data
}

/**
 * Actualiza un producto existente en Dolibarr.
 *
 * @author BenjaminDTS
 * @param id - ID del producto.
 * @param data - Datos a actualizar.
 * @returns Producto actualizado.
 */
export async function updateDolibarrProduct(
  id: number,
  data: Partial<DolibarrProduct>,
): Promise<DolibarrProduct> {
  const response = await apiClient.put<ApiResponse<DolibarrProduct>>(
    `/dolibarr/products/${id}`,
    data,
  )
  return response.data.data
}

/**
 * Elimina un producto de Dolibarr.
 *
 * @author BenjaminDTS
 * @param id - ID del producto.
 */
export async function deleteDolibarrProduct(id: number): Promise<void> {
  await apiClient.delete(`/dolibarr/products/${id}`)
}

/**
 * Elimina múltiples productos de Dolibarr por sus IDs.
 *
 * @author Gemini Code Assist
 * @param ids - Array de IDs de productos a eliminar.
 */
export async function deleteDolibarrProducts(ids: number[]): Promise<void> {
  await apiClient.delete('/dolibarr/products', { data: ids })
}

/**
 * Sincroniza productos desde un job Harvist completado a Dolibarr.
 *
 * @author BenjaminDTS
 * @param request - Request con job_id, códigos y flag overwrite.
 * @returns Array de resultados por producto.
 */
export async function syncDolibarrFromJob(
  request: SyncFromJobRequest,
): Promise<
  Array<{
    codigo: string
    action: string
    dolibarr_id: number | null
    error: string | null
  }>
> {
  const response = await apiClient.post<
    ApiResponse<
      Array<{
        codigo: string
        action: string
        dolibarr_id: number | null
        error: string | null
      }>
    >
  >('/dolibarr/products/sync', request)
  return response.data.data
}

/**
 * Lista terceros (clientes/proveedores) de Dolibarr.
 *
 * @author BenjaminDTS
 * @param mode - 'all', 'customers' o 'suppliers'.
 * @param limit - Máximo a retornar.
 * @param offset - Terceros a saltar.
 * @returns Respuesta paginada de terceros.
 */
export async function listDolibarrThirdparties(
  mode?: ThirdpartyMode,
  limit?: number,
  offset?: number,
): Promise<PaginatedResponse<DolibarrThirdparty>> {
  const params: Record<string, unknown> = {}
  if (mode) params.mode = mode
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset

  const response = await apiClient.get<
    ApiResponse<PaginatedResponse<DolibarrThirdparty>>
  >('/dolibarr/thirdparties', { params })
  return response.data.data
}

/**
 * Busca terceros por nombre.
 *
 * @author BenjaminDTS
 * @param name - Nombre a buscar.
 * @returns Array de terceros coincidentes.
 */
export async function searchDolibarrThirdparties(
  name: string,
): Promise<DolibarrThirdparty[]> {
  const response = await apiClient.get<ApiResponse<DolibarrThirdparty[]>>(
    '/dolibarr/thirdparties/search',
    { params: { name } },
  )
  return response.data.data
}

/**
 * Crea un nuevo tercero en Dolibarr.
 *
 * @author BenjaminDTS
 * @param data - Datos del tercero.
 * @returns Tercero creado.
 */
export async function createDolibarrThirdparty(
  data: Partial<DolibarrThirdparty>,
): Promise<DolibarrThirdparty> {
  const response = await apiClient.post<ApiResponse<DolibarrThirdparty>>(
    '/dolibarr/thirdparties',
    data,
  )
  return response.data.data
}

/**
 * Actualiza un tercero existente.
 *
 * @author BenjaminDTS
 * @param id - ID del tercero.
 * @param data - Datos a actualizar.
 * @returns Tercero actualizado.
 */
export async function updateDolibarrThirdparty(
  id: number,
  data: Partial<DolibarrThirdparty>,
): Promise<DolibarrThirdparty> {
  const response = await apiClient.put<ApiResponse<DolibarrThirdparty>>(
    `/dolibarr/thirdparties/${id}`,
    data,
  )
  return response.data.data
}

/**
 * Elimina un tercero de Dolibarr.
 *
 * @author BenjaminDTS
 * @param id - ID del tercero.
 */
export async function deleteDolibarrThirdparty(id: number): Promise<void> {
  await apiClient.delete(`/dolibarr/thirdparties/${id}`)
}

/**
 * Lista pedidos de Dolibarr con filtros.
 *
 * @author BenjaminDTS
 * @param type - 'customer' o 'supplier'.
 * @param limit - Máximo a retornar.
 * @param offset - Pedidos a saltar.
 * @param status - Estado opcional a filtrar.
 * @param thirdpartyId - ID tercero opcional a filtrar.
 * @returns Respuesta paginada de pedidos.
 */
export async function listDolibarrOrders(
  type: OrderType,
  limit?: number,
  offset?: number,
  status?: number,
  thirdpartyId?: number,
): Promise<PaginatedResponse<DolibarrOrder>> {
  const params: Record<string, unknown> = { type }
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (status !== undefined) params.status = status
  if (thirdpartyId !== undefined) params.thirdparty_id = thirdpartyId

  const response = await apiClient.get<
    ApiResponse<PaginatedResponse<DolibarrOrder>>
  >('/dolibarr/orders', { params })
  return response.data.data
}

/**
 * Lista facturas de Dolibarr con filtros.
 *
 * @author BenjaminDTS
 * @param type - 'customer' o 'supplier'.
 * @param limit - Máximo a retornar.
 * @param offset - Facturas a saltar.
 * @param status - Estado opcional a filtrar.
 * @param thirdpartyId - ID tercero opcional a filtrar.
 * @returns Respuesta paginada de facturas.
 */
export async function listDolibarrInvoices(
  type: InvoiceType,
  limit?: number,
  offset?: number,
  status?: number,
  thirdpartyId?: number,
): Promise<PaginatedResponse<DolibarrInvoice>> {
  const params: Record<string, unknown> = { type }
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (status !== undefined) params.status = status
  if (thirdpartyId !== undefined) params.thirdparty_id = thirdpartyId

  const response = await apiClient.get<
    ApiResponse<PaginatedResponse<DolibarrInvoice>>
  >('/dolibarr/invoices', { params })
  return response.data.data
}

/**
 * Lista almacenes de Dolibarr.
 *
 * @author BenjaminDTS
 * @returns Respuesta paginada de almacenes.
 */
export async function listDolibarrWarehouses(): Promise<
  PaginatedResponse<DolibarrWarehouse>
> {
  const response = await apiClient.get<
    ApiResponse<PaginatedResponse<DolibarrWarehouse>>
  >('/dolibarr/stocks/warehouses')
  return response.data.data
}

/**
 * Obtiene el stock de un producto en todos los almacenes.
 *
 * @author BenjaminDTS
 * @param productId - ID del producto.
 * @returns Objeto con stock total y desglose por almacén.
 */
export async function getDolibarrProductStock(
  productId: number,
): Promise<{
  stock_total: number
  warehouses: Array<{ warehouse_id: number; warehouse_label: string; qty: number }>
}> {
  const response = await apiClient.get<
    ApiResponse<{
      stock_total: number
      warehouses: Array<{
        warehouse_id: number
        warehouse_label: string
        qty: number
      }>
    }>
  >(`/dolibarr/stocks/products/${productId}`)
  return response.data.data
}

/**
 * Lista los campos extra configurados en Dolibarr para un tipo de elemento.
 *
 * @author Carlitos6712
 * @param elementtype - Tipo de elemento (product, societe, etc.).
 * @returns Lista de campos extra con su definición.
 */
export async function listDolibarrExtraFields(
  elementtype = 'product',
): Promise<DolibarrExtraField[]> {
  const response = await apiClient.get<ApiResponse<DolibarrExtraField[]>>(
    '/dolibarr/extrafields',
    { params: { elementtype } },
  )
  return response.data.data
}

/**
 * Crea un nuevo campo extra en Dolibarr.
 *
 * @author Carlitos6712
 * @param data - Definición del nuevo campo extra.
 * @returns Campo extra creado.
 */
export async function createDolibarrExtraField(
  data: DolibarrExtraFieldCreate,
): Promise<DolibarrExtraField> {
  const response = await apiClient.post<ApiResponse<DolibarrExtraField>>(
    '/dolibarr/extrafields',
    data,
  )
  return response.data.data
}

/**
 * Elimina un campo extra de Dolibarr.
 *
 * @author Carlitos6712
 * @param attrname - Nombre interno del campo a eliminar.
 * @param elementtype - Tipo de elemento al que pertenece.
 */
export async function deleteDolibarrExtraField(
  attrname: string,
  elementtype = 'product',
): Promise<void> {
  await apiClient.delete(`/dolibarr/extrafields/${attrname}`, {
    params: { elementtype },
  })
}

/**
 * Obtiene la configuración de BD directa de Dolibarr guardada en Redis.
 *
 * @author Carlitos6712
 */
export async function getDolibarrDBConfig(): Promise<DolibarrDBConfig> {
  const response = await apiClient.get<DolibarrDBConfig>('/dolibarr/db-config')
  return response.data
}

/**
 * Guarda las credenciales de BD directa de Dolibarr en Redis.
 *
 * @author Carlitos6712
 * @param data - Credenciales de acceso a MySQL/MariaDB.
 */
export async function saveDolibarrDBConfig(data: DolibarrDBConfigCreate): Promise<DolibarrDBConfig> {
  const response = await apiClient.post<DolibarrDBConfig>('/dolibarr/db-config', data)
  return response.data
}

/**
 * Pre-analiza un CSV de productos: devuelve cabeceras, filas de muestra y total.
 *
 * @author BenjaminDTS | Carlos Vico
 * @param file - Archivo CSV seleccionado por el usuario.
 * @returns CsvImportPreview con headers, preview y total_rows.
 */
export async function previewDolibarrCsv(file: File): Promise<CsvImportPreview> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiClient.post<ApiResponse<CsvImportPreview>>(
    '/dolibarr/products/csv-preview',
    form,
  )
  return response.data.data
}

/**
 * Importa productos en masa a Dolibarr desde un CSV con mapeo de columnas.
 *
 * @author BenjaminDTS | Carlos Vico
 * @param file      - Archivo CSV.
 * @param mapping   - Mapeo columna_csv → campo_dolibarr.
 * @param overwrite - Si true, actualiza productos existentes.
 * @returns CsvImportResponse con contadores y resultados por fila.
 */
export async function importDolibarrCsv(
  file: File,
  mapping: Record<string, string>,
  overwrite: boolean,
  categoryColumn?: string,
): Promise<DolibarrImportTask> {
  const form = new FormData()
  form.append('file', file)
  form.append('mapping', JSON.stringify(mapping))
  form.append('overwrite', String(overwrite))
  if (categoryColumn) form.append('category_column', categoryColumn)
  const response = await apiClient.post<ApiResponse<DolibarrImportTask>>(
    '/dolibarr/products/import',
    form,
    { timeout: 30_000 },
  )
  return response.data.data
}

/**
 * Consulta el estado de una tarea de importación CSV de Dolibarr.
 *
 * @author BenjaminDTS
 * @param taskId - UUID de la tarea devuelto por importDolibarrCsv.
 */
export async function getDolibarrImportStatus(taskId: string): Promise<DolibarrImportTask> {
  const response = await apiClient.get<ApiResponse<DolibarrImportTask>>(
    `/dolibarr/products/import/${taskId}/status`,
  )
  return response.data.data
}

// ── Categorías Dolibarr ──────────────────────────────────────────

/**
 * Lista categorías Dolibarr con paginación.
 *
 * @author BenjaminDTS
 * @param type   - Tipo de categoría (product, customer, supplier, member).
 * @param limit  - Máximo de resultados.
 * @param offset - Desplazamiento.
 */
export async function listDolibarrCategories(
  type = 'product',
  limit = 50,
  offset = 0,
): Promise<PaginatedResponse<DolibarrCategory>> {
  const response = await apiClient.get<ApiResponse<PaginatedResponse<DolibarrCategory>>>(
    '/dolibarr/categories',
    { params: { type, limit, offset } },
  )
  return response.data.data
}

/**
 * Obtiene el árbol jerárquico completo de categorías.
 *
 * @author BenjaminDTS
 * @param type - Tipo de categoría.
 */
export async function getDolibarrCategoryTree(type = 'product'): Promise<DolibarrCategoryTree[]> {
  const response = await apiClient.get<ApiResponse<DolibarrCategoryTree[]>>(
    '/dolibarr/categories/tree',
    { params: { type } },
  )
  return response.data.data
}

/**
 * Crea una categoría en Dolibarr.
 *
 * @author BenjaminDTS
 * @param label       - Nombre de la categoría.
 * @param type        - Tipo de categoría.
 * @param parent_id   - ID de la categoría padre (opcional).
 * @param description - Descripción (opcional).
 */
export async function createDolibarrCategory(
  label: string,
  type = 'product',
  parent_id?: number | string | null,
  description = '',
): Promise<DolibarrCategory> {
  const params: Record<string, string | number> = { label, type, description }
  if (parent_id != null) params.parent_id = Number(parent_id)
  const response = await apiClient.post<ApiResponse<DolibarrCategory>>(
    '/dolibarr/categories',
    null,
    { params },
  )
  return response.data.data
}

/**
 * Actualiza una categoría existente.
 *
 * @author BenjaminDTS
 * @param id   - ID de la categoría.
 * @param data - Campos a actualizar.
 */
export async function updateDolibarrCategory(
  id: number | string,
  data: Partial<Pick<DolibarrCategory, 'label' | 'description'>>,
): Promise<DolibarrCategory> {
  const response = await apiClient.put<ApiResponse<DolibarrCategory>>(
    `/dolibarr/categories/${id}`,
    data,
  )
  return response.data.data
}

/**
 * Elimina una categoría de Dolibarr.
 *
 * @author BenjaminDTS
 * @param id - ID de la categoría a eliminar.
 */
export async function deleteDolibarrCategory(id: number | string): Promise<void> {
  await apiClient.delete(`/dolibarr/categories/${id}`)
}

/**
 * Asigna un producto a una categoría existente en Dolibarr.
 *
 * @author BenjaminDTS
 * @param categoryId - ID de la categoría.
 * @param productId  - ID del producto a asignar.
 */
export async function assignDolibarrProductToCategory(
  categoryId: number | string,
  productId: number | string,
): Promise<void> {
  await apiClient.post(`/dolibarr/categories/${categoryId}/products/${productId}`)
}

// ────────────────────────────────────────────────────────────────
// ODOO — Métodos de integración
// ────────────────────────────────────────────────────────────────

/**
 * Obtiene el estado de conexión a Odoo.
 *
 * @author Carlitos6712
 */
export async function getOdooStatus(): Promise<IntegrationStatus> {
  const response = await apiClient.get<IntegrationStatus>('/odoo/status')
  return response.data
}

/**
 * Guarda credenciales de Odoo en Redis.
 *
 * @author Carlitos6712
 * @param data - url, db, user y password de Odoo.
 */
export async function saveOdooConfig(data: OdooConfigRequest): Promise<void> {
  await apiClient.post('/odoo/config', data)
}

/**
 * Obtiene la configuración actual de Odoo.
 *
 * @author Carlitos6712
 */
export async function getOdooConfig(): Promise<OdooConfigResponse> {
  const response = await apiClient.get<OdooConfigResponse>('/odoo/config')
  return response.data
}

/**
 * Lista productos Odoo con paginación.
 *
 * @author Carlitos6712
 */
export async function listOdooProducts(
  limit?: number,
  offset?: number,
  search?: string,
): Promise<PaginatedResponse<OdooProduct>> {
  const params: Record<string, unknown> = {}
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (search) params.search = search
  const response = await apiClient.get<ApiResponse<PaginatedResponse<OdooProduct>>>(
    '/odoo/products',
    { params },
  )
  return response.data.data
}

/**
 * Crea un producto en Odoo.
 *
 * @author Carlitos6712
 */
export async function createOdooProduct(data: Partial<OdooProduct>): Promise<OdooProduct> {
  const response = await apiClient.post<ApiResponse<OdooProduct>>('/odoo/products', data)
  return response.data.data
}

/**
 * Actualiza un producto Odoo por ID.
 *
 * @author Carlitos6712
 */
export async function updateOdooProduct(
  id: number,
  data: Partial<OdooProduct>,
): Promise<OdooProduct> {
  const response = await apiClient.put<ApiResponse<OdooProduct>>(`/odoo/products/${id}`, data)
  return response.data.data
}

/**
 * Sube un CSV a Odoo y devuelve cabeceras, previsualización y campos disponibles.
 *
 * @author BenjaminDTS
 * @param file - Archivo CSV (cualquier delimitador).
 */
export async function previewOdooCsv(file: File): Promise<{
  headers: string[]
  preview: Record<string, string>[]
  row_count: number
  odoo_fields: string[]
}> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiClient.post<ApiResponse<{
    headers: string[]
    preview: Record<string, string>[]
    row_count: number
    odoo_fields: string[]
  }>>('/odoo/products/csv/preview', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data.data
}

/**
 * Importa productos en Odoo desde CSV con upsert por referencia interna.
 *
 * @author BenjaminDTS
 * @param file      - Archivo CSV (cualquier delimitador).
 * @param mapping   - Mapa {columna_csv: campo_odoo}. Vacío = ignorar.
 * @param overwrite - Si true, actualiza productos existentes; si false, los omite.
 */
export async function importOdooCsv(
  file: File,
  mapping: Record<string, string>,
  overwrite: boolean = false,
): Promise<{
  created: number
  updated: number
  skipped: number
  failed: number
  errors: Array<{ row: number; error: string }>
}> {
  const form = new FormData()
  form.append('file', file)
  form.append('mapping', JSON.stringify(mapping))
  form.append('overwrite', String(overwrite))
  const response = await apiClient.post<ApiResponse<{
    created: number
    updated: number
    skipped: number
    failed: number
    errors: Array<{ row: number; error: string }>
  }>>('/odoo/products/csv/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 7_200_000,
  })
  return response.data.data
}

/**
 * Elimina un producto Odoo por ID.
 *
 * @author Carlitos6712
 */
export async function deleteOdooProduct(id: number): Promise<void> {
  await apiClient.delete(`/odoo/products/${id}`)
}

/**
 * Elimina múltiples productos Odoo por sus IDs.
 *
 * @author Gemini Code Assist
 * @param ids - Array de IDs de productos a eliminar.
 */
export async function deleteOdooProducts(ids: number[]): Promise<void> {
  await apiClient.delete('/odoo/products', { data: ids, timeout: 7_200_000 })
}

/**
 * Lista categorías Odoo con paginación.
 *
 * @author Carlitos6712
 */
export async function listOdooCategories(
  limit?: number,
  offset?: number,
): Promise<PaginatedResponse<OdooCategory>> {
  const params: Record<string, unknown> = {}
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  const response = await apiClient.get<ApiResponse<PaginatedResponse<OdooCategory>>>(
    '/odoo/categories',
    { params },
  )
  return response.data.data
}

/**
 * Lista partners Odoo (clientes / proveedores / todos).
 *
 * @author Carlitos6712
 * @param mode - 'customer', 'supplier' o 'all'.
 */
export async function listOdooPartners(
  mode: PartnerMode = 'all',
  limit?: number,
  offset?: number,
  search?: string,
): Promise<PaginatedResponse<OdooPartner>> {
  const params: Record<string, unknown> = { mode }
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (search) params.search = search
  const response = await apiClient.get<ApiResponse<PaginatedResponse<OdooPartner>>>(
    '/odoo/partners',
    { params },
  )
  return response.data.data
}

/**
 * Lista pedidos de compra Odoo.
 *
 * @author Carlitos6712
 */
export async function listOooPurchases(
  limit?: number,
  offset?: number,
  state?: string,
): Promise<PaginatedResponse<OooPurchase>> {
  const params: Record<string, unknown> = {}
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (state) params.state = state
  const response = await apiClient.get<ApiResponse<PaginatedResponse<OooPurchase>>>(
    '/odoo/purchases',
    { params },
  )
  return response.data.data
}

/**
 * Lista pedidos de venta Odoo.
 *
 * @author Carlitos6712
 */
export async function listOdooSales(
  limit?: number,
  offset?: number,
  state?: string,
): Promise<PaginatedResponse<OdooSale>> {
  const params: Record<string, unknown> = {}
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (state) params.state = state
  const response = await apiClient.get<ApiResponse<PaginatedResponse<OdooSale>>>(
    '/odoo/sales',
    { params },
  )
  return response.data.data
}

/**
 * Lista facturas Odoo (cliente o proveedor).
 *
 * @author Carlitos6712
 * @param type - 'customer' o 'supplier'.
 */
export async function listOdooInvoices(
  type: OdooInvoiceType = 'customer',
  limit?: number,
  offset?: number,
  state?: string,
): Promise<PaginatedResponse<OdooInvoice>> {
  const params: Record<string, unknown> = { type }
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (state) params.state = state
  const response = await apiClient.get<ApiResponse<PaginatedResponse<OdooInvoice>>>(
    '/odoo/invoices',
    { params },
  )
  return response.data.data
}

/**
 * Lista stock Odoo.
 *
 * @author Carlitos6712
 */
export async function listOdooStock(
  limit?: number,
  offset?: number,
  productId?: number,
  locationId?: number,
): Promise<PaginatedResponse<OdooStockLine>> {
  const params: Record<string, unknown> = {}
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  if (productId !== undefined) params.product_id = productId
  if (locationId !== undefined) params.location_id = locationId
  const response = await apiClient.get<ApiResponse<PaginatedResponse<OdooStockLine>>>(
    '/odoo/inventory',
    { params },
  )
  return response.data.data
}

/**
 * Lista ubicaciones de stock Odoo.
 *
 * @author Carlitos6712
 */
export async function listOdooLocations(): Promise<OdooLocation[]> {
  const response = await apiClient.get<ApiResponse<{ items: OdooLocation[] }>>(
    '/odoo/inventory/locations',
  )
  return response.data.data.items
}

/**
 * Actualiza un partner Odoo por ID.
 *
 * @author Carlitos6712
 */
export async function updateOdooPartner(
  id: number,
  data: Partial<OdooPartner>,
): Promise<OdooPartner> {
  const response = await apiClient.put<ApiResponse<OdooPartner>>(`/odoo/partners/${id}`, data)
  return response.data.data
}

/**
 * Elimina un partner Odoo por ID.
 *
 * @author Carlitos6712
 */
export async function deleteOdooPartner(id: number): Promise<void> {
  await apiClient.delete(`/odoo/partners/${id}`)
}

/**
 * Confirma un pedido de compra Odoo.
 *
 * @author Carlitos6712
 */
export async function confirmOooPurchase(id: number): Promise<void> {
  await apiClient.post(`/odoo/purchases/${id}/confirm`)
}

/**
 * Cancela un pedido de compra Odoo.
 *
 * @author Carlitos6712
 */
export async function cancelOooPurchase(id: number): Promise<void> {
  await apiClient.post(`/odoo/purchases/${id}/cancel`)
}

/**
 * Confirma un pedido de venta Odoo.
 *
 * @author Carlitos6712
 */
export async function confirmOdooSale(id: number): Promise<void> {
  await apiClient.post(`/odoo/sales/${id}/confirm`)
}

/**
 * Cancela un pedido de venta Odoo.
 *
 * @author Carlitos6712
 */
export async function cancelOdooSale(id: number): Promise<void> {
  await apiClient.post(`/odoo/sales/${id}/cancel`)
}

/**
 * Valida (publica) una factura Odoo en borrador.
 *
 * @author Carlitos6712
 */
export async function validateOdooInvoice(id: number): Promise<void> {
  await apiClient.post(`/odoo/invoices/${id}/validate`)
}

/**
 * Cancela una factura Odoo.
 *
 * @author Carlitos6712
 */
export async function cancelOdooInvoice(id: number): Promise<void> {
  await apiClient.post(`/odoo/invoices/${id}/cancel`)
}

/**
 * Ajusta la cantidad inventariada de un quant de stock Odoo (legacy helper).
 *
 * @author Carlitos6712
 */
export async function adjustOdooStock(quantId: number, inventoryQuantity: number): Promise<void> {
  await apiClient.post(`/odoo/inventory/${quantId}/adjust`, { inventory_quantity: inventoryQuantity })
}

/**
 * Actualiza campos de un stock.quant. Si incluye inventory_quantity aplica el ajuste.
 *
 * @author Carlitos6712
 */
export async function updateOdooStockQuant(
  id: number,
  data: Partial<OdooStockLine>,
): Promise<void> {
  await apiClient.put(`/odoo/inventory/${id}`, data)
}

/**
 * Elimina un stock.quant de Odoo.
 *
 * @author Carlitos6712
 */
export async function deleteOdooStockQuant(id: number): Promise<void> {
  await apiClient.delete(`/odoo/inventory/${id}`)
}

// ── Properties (campos extra) ──────────────────────────────────────────────

/**
 * Obtiene las definiciones de campos extra de una categoría de productos.
 *
 * @author Carlitos6712
 * @param categoryId - ID de product.category.
 */
export async function getOdooCategoryProperties(
  categoryId: number,
): Promise<OdooPropertyDefinition[]> {
  const response = await apiClient.get<ApiResponse<{ definitions: OdooPropertyDefinition[] }>>(
    `/odoo/categories/${categoryId}/properties`,
  )
  return response.data.data.definitions
}

/**
 * Añade un campo extra a una categoría de productos.
 *
 * @author Carlitos6712
 * @param categoryId - ID de product.category.
 * @param def        - type, string, default y view_in_cards.
 */
export async function addOdooCategoryProperty(
  categoryId: number,
  def: Omit<OdooPropertyDefinition, 'name'>,
): Promise<OdooPropertyDefinition> {
  const response = await apiClient.post<ApiResponse<OdooPropertyDefinition>>(
    `/odoo/categories/${categoryId}/properties`,
    def,
  )
  return response.data.data
}

/**
 * Actualiza un campo extra de categoría (string, default o view_in_cards).
 *
 * @author Carlitos6712
 * @param categoryId - ID de product.category.
 * @param propName   - Identificador hex de 16 chars de la propiedad.
 * @param updates    - Campos a actualizar.
 */
export async function updateOdooCategoryProperty(
  categoryId: number,
  propName: string,
  updates: Partial<Pick<OdooPropertyDefinition, 'string' | 'default' | 'view_in_cards'>>,
): Promise<OdooPropertyDefinition> {
  const response = await apiClient.put<ApiResponse<OdooPropertyDefinition>>(
    `/odoo/categories/${categoryId}/properties/${propName}`,
    updates,
  )
  return response.data.data
}

/**
 * Elimina un campo extra de una categoría de productos.
 *
 * @author Carlitos6712
 * @param categoryId - ID de product.category.
 * @param propName   - Identificador hex de 16 chars.
 */
export async function deleteOdooCategoryProperty(
  categoryId: number,
  propName: string,
): Promise<void> {
  await apiClient.delete(`/odoo/categories/${categoryId}/properties/${propName}`)
}

/**
 * Obtiene los valores de campos extra de un producto.
 *
 * @author Carlitos6712
 * @param productId  - ID de product.template.
 * @param categoryId - ID de product.category (opcional, para merge con definiciones).
 */
export async function getOdooProductProperties(
  productId: number,
  categoryId?: number,
): Promise<OdooPropertyValue[]> {
  const params = categoryId !== undefined ? { category_id: categoryId } : {}
  const response = await apiClient.get<ApiResponse<{ properties: OdooPropertyValue[] }>>(
    `/odoo/products/${productId}/properties`,
    { params },
  )
  return response.data.data.properties
}

/**
 * Guarda múltiples valores de campos extra en un producto.
 *
 * @author Carlitos6712
 * @param productId - ID de product.template.
 * @param props     - Lista de {name, type, string, value}.
 */
export async function setOdooProductProperties(
  productId: number,
  props: OdooPropertyValue[],
): Promise<OdooPropertyValue[]> {
  const response = await apiClient.put<ApiResponse<{ properties: OdooPropertyValue[] }>>(
    `/odoo/products/${productId}/properties`,
    props,
  )
  return response.data.data.properties
}

/**
 * Elimina el valor de un campo extra en un producto.
 *
 * @author Carlitos6712
 * @param productId - ID de product.template.
 * @param propName  - Identificador hex de 16 chars.
 */
export async function deleteOdooProductProperty(
  productId: number,
  propName: string,
): Promise<void> {
  await apiClient.delete(`/odoo/products/${productId}/properties/${propName}`)
}

// ─── WordPress / WooCommerce ─────────────────────────────────────────────────

import type {
  WooProduct,
  WooCategory,
  WooOrder,
  WooCustomer,
  WooMedia,
  WordPressConfigRequest,
  WordPressConfigResponse,
  WordPressDBConfigRequest,
  WordPressDBConfigResponse,
  DBTable,
  WPSiteInfo,
} from '@/types/wordpress'

// ── Status & Config ──────────────────────────────────────────────────────────

/**
 * Obtiene el estado de configuración y salud de la integración WordPress.
 *
 * @author Carlos Vico
 * @returns IntegrationStatus con platform, configured, healthy y message.
 */
export async function getWordPressStatus(): Promise<IntegrationStatus> {
  const r = await apiClient.get<IntegrationStatus>('/wordpress/status')
  return r.data
}

/**
 * Lee la configuración actual de WordPress (credenciales enmascaradas).
 *
 * @author Carlos Vico
 * @returns WordPressConfigResponse con las credenciales actuales.
 */
export async function getWordPressConfig(): Promise<WordPressConfigResponse> {
  const r = await apiClient.get<WordPressConfigResponse>('/wordpress/config')
  return r.data
}

/**
 * Guarda las credenciales de WordPress en el servidor.
 *
 * @author Carlos Vico
 * @param config - URL y API Key de WooCommerce.
 */
export async function saveWordPressConfig(config: WordPressConfigRequest): Promise<void> {
  await apiClient.post('/wordpress/config', config)
}

/**
 * Lee la configuración de BD MySQL de WordPress.
 *
 * @author Carlos Vico
 * @returns WordPressDBConfigResponse con las credenciales de BD.
 */
export async function getWordPressDBConfig(): Promise<WordPressDBConfigResponse> {
  const r = await apiClient.get<WordPressDBConfigResponse>('/wordpress/db/config')
  return r.data
}

/**
 * Guarda las credenciales de BD MySQL de WordPress.
 *
 * @author Carlos Vico
 * @param config - host, port, db_name, user, password, prefix.
 */
export async function saveWordPressDBConfig(config: WordPressDBConfigRequest): Promise<void> {
  await apiClient.post('/wordpress/db/config', config)
}

// ── Products ─────────────────────────────────────────────────────────────────

/**
 * Lista productos WooCommerce con paginación.
 *
 * @author Carlos Vico
 * @param limit  - Elementos por página.
 * @param offset - Desplazamiento.
 * @param status - Filtro de estado.
 * @returns Lista de WooProduct.
 */
export async function listWordPressProducts(
  limit = 50,
  offset = 0,
  status = 'any',
): Promise<WooProduct[]> {
  const r = await apiClient.get<ApiResponse<{ items: WooProduct[] }>>(
    '/wordpress/products',
    { params: { limit, offset, status } },
  )
  return r.data.data.items
}

/**
 * Obtiene un producto WooCommerce por ID.
 *
 * @author Carlos Vico
 * @param id - ID del producto.
 * @returns WooProduct.
 */
export async function getWordPressProduct(id: number): Promise<WooProduct> {
  const r = await apiClient.get<ApiResponse<WooProduct>>(`/wordpress/products/${id}`)
  return r.data.data
}

/**
 * Crea un producto en WooCommerce.
 *
 * @author Carlos Vico
 * @param data - Campos del producto.
 * @returns WooProduct creado.
 */
export async function createWordPressProduct(data: Partial<WooProduct>): Promise<WooProduct> {
  const r = await apiClient.post<ApiResponse<WooProduct>>('/wordpress/products', data)
  return r.data.data
}

/**
 * Actualiza un producto en WooCommerce.
 *
 * @author Carlos Vico
 * @param id   - ID del producto.
 * @param data - Campos a actualizar.
 * @returns WooProduct actualizado.
 */
export async function updateWordPressProduct(
  id: number,
  data: Partial<WooProduct>,
): Promise<WooProduct> {
  const r = await apiClient.put<ApiResponse<WooProduct>>(`/wordpress/products/${id}`, data)
  return r.data.data
}

/**
 * Elimina un producto de WooCommerce.
 *
 * @author Carlos Vico
 * @param id - ID del producto.
 */
export async function deleteWordPressProduct(id: number): Promise<void> {
  await apiClient.delete(`/wordpress/products/${id}`)
}

/**
 * Sincroniza productos de un job Harvist a WooCommerce.
 *
 * @author Carlos Vico
 * @param jobId        - UUID del job.
 * @param productCodes - Códigos de producto a sincronizar.
 * @param overwrite    - Si True, sobreescribe productos existentes.
 */
export async function syncWordPressFromJob(
  jobId: string,
  productCodes: string[],
  overwrite = false,
): Promise<Record<string, unknown>> {
  const r = await apiClient.post<ApiResponse<Record<string, unknown>>>(
    '/wordpress/products/sync',
    { job_id: jobId, product_codes: productCodes, overwrite },
  )
  return r.data.data
}

// ── Categories ────────────────────────────────────────────────────────────────

/**
 * Lista categorías WooCommerce.
 *
 * @author Carlos Vico
 * @returns Lista de WooCategory.
 */
export async function listWordPressCategories(): Promise<WooCategory[]> {
  const r = await apiClient.get<ApiResponse<WooCategory[]>>('/wordpress/categories')
  return r.data.data
}

/**
 * Obtiene el árbol jerárquico de categorías WooCommerce.
 *
 * @author Carlos Vico
 * @returns Lista de categorías raíz con campo "children".
 */
export async function getWordPressCategoriesTree(): Promise<WooCategory[]> {
  const r = await apiClient.get<ApiResponse<WooCategory[]>>('/wordpress/categories/tree')
  return r.data.data
}

/**
 * Crea una categoría en WooCommerce.
 *
 * @author Carlos Vico
 * @param data - Campos de la categoría.
 * @returns WooCategory creada.
 */
export async function createWordPressCategory(
  data: Partial<WooCategory>,
): Promise<WooCategory> {
  const r = await apiClient.post<ApiResponse<WooCategory>>('/wordpress/categories', data)
  return r.data.data
}

/**
 * Elimina una categoría de WooCommerce.
 *
 * @author Carlos Vico
 * @param id - ID de la categoría.
 */
export async function deleteWordPressCategory(id: number): Promise<void> {
  await apiClient.delete(`/wordpress/categories/${id}`)
}

// ── Orders ────────────────────────────────────────────────────────────────────

/**
 * Lista pedidos WooCommerce.
 *
 * @author Carlos Vico
 * @param limit  - Elementos por página.
 * @param offset - Desplazamiento.
 * @param status - Filtro de estado.
 * @returns Lista de WooOrder.
 */
export async function listWordPressOrders(
  limit = 50,
  offset = 0,
  status = 'any',
): Promise<WooOrder[]> {
  const r = await apiClient.get<ApiResponse<{ items: WooOrder[] }>>(
    '/wordpress/orders',
    { params: { limit, offset, status } },
  )
  return r.data.data.items
}

/**
 * Cambia el estado de un pedido WooCommerce.
 *
 * @author Carlos Vico
 * @param id        - ID del pedido.
 * @param newStatus - Nuevo estado.
 * @param note      - Nota interna opcional.
 * @returns WooOrder actualizado.
 */
export async function updateWordPressOrderStatus(
  id: number,
  newStatus: string,
  note = '',
): Promise<WooOrder> {
  const r = await apiClient.put<ApiResponse<WooOrder>>(
    `/wordpress/orders/${id}/status`,
    { status: newStatus, note },
  )
  return r.data.data
}

// ── Customers ─────────────────────────────────────────────────────────────────

/**
 * Lista clientes WooCommerce.
 *
 * @author Carlos Vico
 * @param limit  - Elementos por página.
 * @param offset - Desplazamiento.
 * @param search - Término de búsqueda.
 * @returns Lista de WooCustomer.
 */
export async function listWordPressCustomers(
  limit = 50,
  offset = 0,
  search = '',
): Promise<WooCustomer[]> {
  const r = await apiClient.get<ApiResponse<{ items: WooCustomer[] }>>(
    '/wordpress/customers',
    { params: { limit, offset, search } },
  )
  return r.data.data.items
}

/**
 * Elimina un cliente de WooCommerce.
 *
 * @author Carlos Vico
 * @param id - ID del cliente.
 */
export async function deleteWordPressCustomer(id: number): Promise<void> {
  await apiClient.delete(`/wordpress/customers/${id}`)
}

// ── Media ─────────────────────────────────────────────────────────────────────

/**
 * Lista archivos del Media Library de WordPress.
 *
 * @author Carlos Vico
 * @param limit  - Elementos por página.
 * @param offset - Desplazamiento.
 * @returns Lista de WooMedia.
 */
export async function listWordPressMedia(limit = 50, offset = 0): Promise<WooMedia[]> {
  const r = await apiClient.get<ApiResponse<{ items: WooMedia[] }>>(
    '/wordpress/media',
    { params: { limit, offset } },
  )
  return r.data.data.items
}

/**
 * Sube un archivo al Media Library de WordPress.
 *
 * @author Carlos Vico
 * @param file - Archivo a subir (image/jpeg, image/png, image/webp).
 * @returns WooMedia creado.
 */
export async function uploadWordPressMedia(file: File): Promise<WooMedia> {
  const form = new FormData()
  form.append('file', file)
  const r = await apiClient.post<ApiResponse<WooMedia>>('/wordpress/media', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return r.data.data
}

// ── Database (phpMyAdmin) ─────────────────────────────────────────────────────

/**
 * Lista las tablas de la BD MySQL de WordPress.
 *
 * @author Carlos Vico
 * @returns Lista de DBTable con nombre, filas, tamaño y motor.
 */
export async function listWordPressDBTables(): Promise<DBTable[]> {
  const r = await apiClient.get<ApiResponse<DBTable[]>>('/wordpress/db/tables')
  return r.data.data
}

/**
 * Obtiene información básica del sitio WordPress desde wp_options.
 *
 * @author Carlos Vico
 * @returns WPSiteInfo con siteurl, blogname, etc.
 */
export async function getWordPressSiteInfo(): Promise<WPSiteInfo> {
  const r = await apiClient.get<ApiResponse<WPSiteInfo>>('/wordpress/db/site-info')
  return r.data.data
}

/**
 * Ejecuta una consulta SQL SELECT contra la BD MySQL de WordPress.
 *
 * @author Carlos Vico
 * @param sql    - Consulta SELECT.
 * @param params - Parámetros parametrizados.
 * @returns Filas resultantes.
 */
export async function queryWordPressDB(
  sql: string,
  params: unknown[] = [],
): Promise<{ rows: Record<string, unknown>[]; count: number }> {
  const r = await apiClient.post<ApiResponse<{ rows: Record<string, unknown>[]; count: number }>>(
    '/wordpress/db/query',
    { sql, params },
  )
  return r.data.data
}
