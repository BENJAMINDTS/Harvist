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
