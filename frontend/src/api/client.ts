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
