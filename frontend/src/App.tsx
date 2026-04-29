/**
 * Componente raíz de la aplicación Harvist.
 *
 * Gestiona el estado global del job activo y orquesta el flujo:
 * 1. Pantalla de inicio con selección de modo (HomeScreen)
 * 2. El usuario sube un CSV y configura la búsqueda (CsvUploader + SearchConfig)
 * 3. Se crea el job y se muestra el progreso en tiempo real (JobProgress)
 * 4. Al completar, se habilita la descarga del resultado
 * 5. Panel de historial de trabajos anteriores (JobHistory)
 *
 * @author BenjaminDTS | Carlos Vico
 */
import React, { useEffect, useState } from 'react'
import { CsvUploader } from '@/components/CsvUploader'
import { SearchConfig } from '@/components/SearchConfig'
import { JobProgress } from '@/components/JobProgress'
import { JobHistory } from '@/components/JobHistory'
import { HomeScreen } from '@/components/HomeScreen'
import { BrandsPanel } from '@/components/BrandsPanel'
import { NsLogo } from '@/components/NsLogo'
import { apiClient, getBrands, resumeJob } from '@/api/client'
import type { ApiError, BrandEntry } from '@/api/client'
import type { SearchConfigValues, TipoJob } from '@/components/SearchConfig'

/** Estados posibles de la pantalla principal */
type AppState = 'home' | 'configuring' | 'running' | 'done'
/** Pestañas de navegación para el historial */
type Tab = 'nuevo' | 'historial'

const App: React.FC = () => {
  const [tab, setTab] = useState<Tab>('nuevo')
  const [appState, setAppState] = useState<AppState>('home')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [csvHeaders, setCsvHeaders] = useState<string[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [tipoJob, setTipoJob] = useState<TipoJob>('fotos')
  const [tipoJobSeleccionado, setTipoJobSeleccionado] = useState<TipoJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resumeLoading, setResumeLoading] = useState(false)
  const [brandsData, setBrandsData] = useState<BrandEntry[] | null>(null)
  const [brandsPanelOpen, setBrandsPanelOpen] = useState(true)
  const [brandsLoadError, setBrandsLoadError] = useState<string | null>(null)

  // ── Handlers de HomeScreen ───────────────────────────────────────────────

  /** El usuario elige el modo "Fotos" en la pantalla de inicio */
  const handleSelectFotos = (): void => {
    setTipoJobSeleccionado('fotos')
    setAppState('configuring')
    setError(null)
  }

  /** El usuario elige el modo "Descripciones" en la pantalla de inicio */
  const handleSelectDescripciones = (): void => {
    setTipoJobSeleccionado('descripciones')
    setAppState('configuring')
    setError(null)
  }

  /** El usuario elige el modo "Fichas de Marca" en la pantalla de inicio */
  const handleSelectMarcas = (): void => {
    setTipoJobSeleccionado('marcas')
    setAppState('configuring')
    setError(null)
  }

  /** El usuario abre el historial desde la pantalla de inicio */
  const handleSelectHistorial = (): void => {
    setTab('historial')
  }

  // ── Handlers del flujo principal ────────────────────────────────────────

  /** Callback: el usuario seleccionó un CSV válido — recibe el archivo y sus cabeceras */
  const handleFileSelected = (file: File, headers: string[]): void => {
    setSelectedFile(file)
    setCsvHeaders(headers)
    setError(null)
  }

  /** Callback: el usuario confirmó la configuración y lanza el job */
  const handleLaunchJob = async (config: SearchConfigValues): Promise<void> => {
    if (!selectedFile) return

    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('tipo_job', config.tipoJob)
      formData.append('modo', config.modo)
      formData.append('imagenes_por_producto', String(config.imagenesPorProducto))
      formData.append('query_personalizada', config.queryPersonalizada)
      formData.append('columna_codigo', config.columnMapping.columnaCodigo)
      formData.append('columna_ean', config.columnMapping.columnaEan)
      formData.append('columna_nombre', config.columnMapping.columnaNombre)
      formData.append('columna_marca', config.columnMapping.columnaMarca)
      formData.append('columna_categoria', config.columnMapping.columnaCategoria)
      formData.append('columna_nombre_foto', config.columnMapping.columnaNombreFoto)
      formData.append('groq_api_key_usuario', config.groqApiKey)
      formData.append('store_type_usuario', config.storeType)

      const response = await apiClient.post<{
        success: boolean
        data: { job_id: string }
        message: string
      }>('/jobs', formData)

      setJobId(response.data.data.job_id)
      setTipoJob(config.tipoJob)
      setAppState('running')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al iniciar el trabajo.'
      setError(msg)
    }
  }

  /** Callback: el job completó (exitoso o fallido) */
  const handleJobFinished = (): void => {
    setAppState('done')
  }

  // Cuando el job de marcas completa, cargamos los datos para el panel.
  useEffect(() => {
    if (appState !== 'done' || tipoJob !== 'marcas' || !jobId) return
    setBrandsLoadError(null)
    getBrands(jobId)
      .then((data) => {
        setBrandsData(data)
        setBrandsPanelOpen(data.some((b) => b.source !== 'not_found' && b.source !== 'ean_invalido'))
      })
      .catch((err: unknown) => {
        setBrandsData(null)
        const msg = (err as ApiError).message ?? 'No se pudieron cargar las marcas.'
        setBrandsLoadError(msg)
      })
  }, [appState, tipoJob, jobId])

  /** Reinicia el flujo completo a la pantalla de inicio */
  const handleReset = (): void => {
    setAppState('home')
    setSelectedFile(null)
    setCsvHeaders([])
    setJobId(null)
    setTipoJob('fotos')
    setTipoJobSeleccionado(null)
    setError(null)
    setTab('nuevo')
    setBrandsData(null)
    setBrandsPanelOpen(true)
    setBrandsLoadError(null)
  }

  /** Callback: desde el historial el usuario abre un job anterior */
  const handleSelectJobFromHistory = (selectedJobId: string): void => {
    setJobId(selectedJobId)
    setAppState('done')
    setTab('nuevo')
  }

  /** Reanuda el job actual llamando al endpoint de reanudación */
  const handleResume = async (): Promise<void> => {
    if (!jobId) return
    setResumeLoading(true)
    setError(null)
    try {
      const data = await resumeJob(jobId)
      setJobId(data.job_id)
      setAppState('running')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'No se pudo reanudar el trabajo.'
      setError(msg)
    } finally {
      setResumeLoading(false)
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* ── Cabecera ── */}
      <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-6 py-3">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <button
            type="button"
            onClick={handleReset}
            className="flex items-center gap-3 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 rounded-lg p-1"
            aria-label="Volver a la pantalla de inicio"
          >
            <NsLogo size={36} />
            <div className="text-left">
              <span className="block text-xl font-bold leading-tight" style={{ color: '#1B5FAB' }}>
                Harvist
              </span>
              <span className="block text-xs text-gray-400 dark:text-gray-500 leading-tight">
                by Nubium Solutions
              </span>
            </div>
          </button>

          {/* Acceso al historial cuando no estamos en la home */}
          {appState !== 'home' && (
            <nav>
              <button
                type="button"
                onClick={() => setTab(tab === 'historial' ? 'nuevo' : 'historial')}
                className={`px-4 py-1.5 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                  tab === 'historial'
                    ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-400'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                Historial
              </button>
            </nav>
          )}
        </div>
      </header>

      {/* ── Contenido principal ── */}
      <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {error && (
          <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm" role="alert">
            {error}
          </div>
        )}

        {/* Pantalla de inicio */}
        {appState === 'home' && tab === 'nuevo' && (
          <HomeScreen
            onSelectFotos={handleSelectFotos}
            onSelectDescripciones={handleSelectDescripciones}
            onSelectMarcas={handleSelectMarcas}
            onSelectHistorial={handleSelectHistorial}
          />
        )}

        {/* Flujo de configuración y ejecución */}
        {tab === 'nuevo' && appState !== 'home' && (
          <>
            {appState === 'configuring' && (
              <>
                {selectedFile === null ? (
                  <CsvUploader onFileSelected={handleFileSelected} />
                ) : (
                  <SearchConfig
                    fileName={selectedFile.name}
                    csvHeaders={csvHeaders}
                    onLaunch={handleLaunchJob}
                    onBack={handleReset}
                    tipoJobForzado={tipoJobSeleccionado ?? undefined}
                  />
                )}
              </>
            )}

            {(appState === 'running' || appState === 'done') && jobId && (
              <JobProgress
                key={jobId}
                jobId={jobId}
                tipoJob={tipoJob}
                onFinished={handleJobFinished}
                onReset={handleReset}
                onResume={resumeLoading ? undefined : handleResume}
              />
            )}

            {/* Error al cargar marcas */}
            {appState === 'done' && tipoJob === 'marcas' && brandsLoadError !== null && (
              <div className="w-full max-w-2xl mx-auto rounded-lg border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-950 px-4 py-3 text-sm text-yellow-700 dark:text-yellow-400" role="alert">
                No se pudo cargar el panel de marcas: {brandsLoadError}
              </div>
            )}

            {/* Panel de marcas — visible cuando el job de marcas termina y hay datos */}
            {appState === 'done' &&
              tipoJob === 'marcas' &&
              jobId !== null &&
              brandsData !== null &&
              (brandsData.length > 0) && (
                <section className="w-full max-w-2xl mx-auto">
                  <button
                    type="button"
                    onClick={() => setBrandsPanelOpen((o) => !o)}
                    className="flex w-full items-center justify-between rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3 text-sm font-semibold text-gray-800 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2"
                    aria-expanded={brandsPanelOpen}
                  >
                    <span>Resultados de marcas</span>
                    <svg
                      className={`h-4 w-4 text-gray-500 transition-transform duration-200 ${brandsPanelOpen ? 'rotate-180' : ''}`}
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {brandsPanelOpen && (
                    <div className="mt-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
                      <BrandsPanel jobId={jobId} brandsData={brandsData} />
                    </div>
                  )}
                </section>
              )
            }
          </>
        )}

        {/* Historial */}
        {tab === 'historial' && (
          <JobHistory onSelectJob={handleSelectJobFromHistory} />
        )}
      </main>
    </div>
  )
}

export default App
