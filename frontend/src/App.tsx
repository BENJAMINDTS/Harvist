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
import React, { useCallback, useEffect, useState, Suspense } from 'react'
import { CsvUploader } from '@/components/CsvUploader'
import { SearchConfig } from '@/components/SearchConfig'
import { JobProgress } from '@/components/JobProgress'
import { JobHistory } from '@/components/JobHistory'
import { HomeScreen } from '@/components/HomeScreen'
import { BrandsPanel } from '@/components/BrandsPanel'
import { ReviewPanel } from '@/components/ReviewPanel'
import BrandValidationPanel from '@/components/BrandValidationPanel'
import PhotoSelectionPanel from '@/components/PhotoSelectionPanel'
import { NsLogo } from '@/components/NsLogo'
import { apiClient, getBrands, getBrandsPending, resumeJob, downloadTranslationCsv } from '@/api/client'
import type { ApiError, BrandEntry, BrandPendingEntry, BrandValidationResult } from '@/api/client'
import type { SearchConfigValues, TipoJob } from '@/components/SearchConfig'

const DolibarrPanel = React.lazy(() => import('@/components/dolibarr/DolibarrPanel'))

/** Estados posibles de la pantalla principal */
type AppState = 'home' | 'configuring' | 'running' | 'done'
/** Pestañas de navegación para el historial */
type Tab = 'nuevo' | 'historial' | 'dolibarr'

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
  const [targetLanguages, setTargetLanguages] = useState<string[]>([])
  const [reviewPanelOpen, setReviewPanelOpen] = useState(true)
  const [descripcionesGeneradas, setDescripcionesGeneradas] = useState(0)
  const [pendingBrands, setPendingBrands] = useState<BrandPendingEntry[]>([])
  const [brandValidationDone, setBrandValidationDone] = useState(false)
  const [photoSelectionDone, setPhotoSelectionDone] = useState(false)
  const [selectPhotos, setSelectPhotos] = useState(false)

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
      config.targetLanguages.forEach((lang) =>
        formData.append('target_languages', lang)
      )
      formData.append('validate_brands', String(config.validateBrands))
      formData.append('select_photos', String(config.selectPhotos))

      const response = await apiClient.post<{
        success: boolean
        data: { job_id: string }
        message: string
      }>('/jobs', formData)

      setJobId(response.data.data.job_id)
      setTipoJob(config.tipoJob)
      setTargetLanguages(config.targetLanguages)
      setSelectPhotos(config.selectPhotos)
      setAppState('running')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al iniciar el trabajo.'
      setError(msg)
    }
  }

  /** Callback: el job completó (exitoso o fallido) */
  const handleJobFinished = useCallback(async (): Promise<void> => {
    if (!jobId) {
      setAppState('done')
      return
    }

    try {
      const response = await apiClient.get<{
        success: boolean
        data: { estado: string }
      }>(`/jobs/${jobId}`)

      const estado = response.data.data.estado

      // Detectar si está en estado de selección de fotos (Fase 7.5)
      if (estado === 'pendiente_seleccion_fotos') {
        // No avanzamos de estado, dejamos que el PhotoSelectionPanel se muestre
      } else if (estado === 'pendiente_validacion_marcas') {
        const brands = await getBrandsPending(jobId)
        setPendingBrands(brands)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al comprobar el estado del job.'
      setError(msg)
    }
    setAppState('done')
  }, [jobId])

  /** Callback: el usuario completó la validación de marcas */
  const handleValidationComplete = useCallback((_result: BrandValidationResult): void => {
    setPendingBrands([])
    setBrandValidationDone(true)
  }, [])

  /** Callback: el usuario completó la selección de fotos */
  const handlePhotoSelectionComplete = useCallback(async (): Promise<void> => {
    setPhotoSelectionDone(true)
    // Después de confirmar la selección, avanzar automáticamente
    // Si hay validación de marcas activada, ir al BrandValidationPanel
    // Si no, pasar a COMPLETADO
    if (jobId) {
      try {
        const response = await apiClient.get<{
          success: boolean
          data: { estado: string }
        }>(`/jobs/${jobId}`)

        if (response.data.data.estado === 'pendiente_validacion_marcas') {
          const brands = await getBrandsPending(jobId)
          setPendingBrands(brands)
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Error al comprobar el estado del job.'
        setError(msg)
      }
    }
  }, [jobId])

  // Cuando un job de descripciones completa, cargamos el contador para el ReviewPanel.
  useEffect(() => {
    if (appState !== 'done' || tipoJob !== 'descripciones' || !jobId) return
    apiClient
      .get<{ success: boolean; data: { descripciones_generadas: number } }>(
        `/jobs/${jobId}`
      )
      .then((res) => {
        const count = res.data.data.descripciones_generadas ?? 0
        setDescripcionesGeneradas(count)
        setReviewPanelOpen(count > 0)
      })
      .catch(() => {
        setDescripcionesGeneradas(0)
      })
  }, [appState, tipoJob, jobId])

  // Cuando el job de marcas completa (sin validación pendiente), cargamos los datos para el panel.
  useEffect(() => {
    if (appState !== 'done' || tipoJob !== 'marcas' || !jobId || pendingBrands.length > 0) return
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
  }, [appState, tipoJob, jobId, pendingBrands.length])

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
    setReviewPanelOpen(true)
    setDescripcionesGeneradas(0)
    setPendingBrands([])
    setBrandValidationDone(false)
    setPhotoSelectionDone(false)
    setSelectPhotos(false)
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

          {/* Acceso a otras secciones cuando no estamos en la home */}
          {appState !== 'home' && (
            <nav className="flex gap-2">
              <button
                type="button"
                onClick={() => setTab('nuevo')}
                className={`px-4 py-1.5 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                  tab === 'nuevo'
                    ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-400'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                Nuevo Job
              </button>
              <button
                type="button"
                onClick={() => setTab('historial')}
                className={`px-4 py-1.5 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                  tab === 'historial'
                    ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-400'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                Historial
              </button>
              <button
                type="button"
                onClick={() => setTab('dolibarr')}
                className={`px-4 py-1.5 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                  tab === 'dolibarr'
                    ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-400'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                Dolibarr
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

            {/* Traducciones disponibles — visible cuando job de descripciones termina con idiomas seleccionados */}
            {appState === 'done' &&
              tipoJob === 'descripciones' &&
              jobId !== null &&
              targetLanguages.length > 0 && (
                <section
                  className="w-full max-w-2xl mx-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4"
                  aria-label="Descargar traducciones"
                >
                  <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                    Traducciones generadas
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {(
                      [
                        { code: 'en', label: 'Inglés' },
                        { code: 'fr', label: 'Francés' },
                        { code: 'de', label: 'Alemán' },
                        { code: 'it', label: 'Italiano' },
                        { code: 'pt', label: 'Portugués' },
                      ] as const
                    )
                      .filter(({ code }) => targetLanguages.includes(code))
                      .map(({ code, label }) => (
                        <button
                          key={code}
                          type="button"
                          onClick={async () => {
                            try {
                              const blob = await downloadTranslationCsv(jobId, code)
                              const url = URL.createObjectURL(blob)
                              const a = document.createElement('a')
                              a.href = url
                              a.download = `descripciones_${code}_${jobId.slice(0, 8)}.csv`
                              a.click()
                              URL.revokeObjectURL(url)
                            } catch {
                              // Error silencioso — el botón simplemente no descarga
                            }
                          }}
                          className={
                            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors duration-150 " +
                            "bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700 " +
                            "text-green-700 dark:text-green-300 hover:bg-green-100 dark:hover:bg-green-900/40"
                          }
                          aria-label={`Descargar CSV en ${label}`}
                        >
                          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                            <path d="M8 12l-4.5-4.5 1.06-1.06L7 9.38V2h2v7.38l2.44-2.94 1.06 1.06L8 12zM2 14h12v-2H2v2z" />
                          </svg>
                          {label}
                        </button>
                      ))}
                  </div>
                </section>
              )}

            {/* Panel de revisión de descripciones — visible cuando job de descripciones termina */}
            {appState === 'done' &&
              tipoJob === 'descripciones' &&
              jobId !== null &&
              descripcionesGeneradas > 0 && (
                <section className="w-full max-w-2xl mx-auto">
                  <button
                    type="button"
                    onClick={() => setReviewPanelOpen((o) => !o)}
                    className="flex w-full items-center justify-between rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3 text-sm font-semibold text-gray-800 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2"
                    aria-expanded={reviewPanelOpen}
                  >
                    <span>Revisar descripciones generadas</span>
                    <svg
                      className={`h-4 w-4 text-gray-500 transition-transform duration-200 ${reviewPanelOpen ? 'rotate-180' : ''}`}
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {reviewPanelOpen && (
                    <div className="mt-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
                      <ReviewPanel jobId={jobId} onComplete={handleReset} />
                    </div>
                  )}
                </section>
              )}

            {/* Panel de selección de fotos — visible cuando el job espera selección de fotos (Fase 7.5) */}
            {appState === 'done' &&
              tipoJob === 'fotos' &&
              selectPhotos &&
              jobId !== null &&
              !photoSelectionDone && (
                <section className="w-full max-w-4xl mx-auto">
                  <div className="rounded-lg border border-cyan-200 dark:border-cyan-800 bg-white dark:bg-gray-900 p-4">
                    <h3 className="text-sm font-semibold text-cyan-900 dark:text-cyan-300 mb-4">
                      Seleccionar foto por producto
                    </h3>
                    <PhotoSelectionPanel
                      jobId={jobId}
                      onComplete={handlePhotoSelectionComplete}
                    />
                  </div>
                </section>
              )}

            {/* Panel de validación de marcas — visible cuando el job espera validación de marcas nuevas */}
            {appState === 'done' &&
              tipoJob === 'marcas' &&
              jobId !== null &&
              pendingBrands.length > 0 &&
              !brandValidationDone && (
                <section className="w-full max-w-2xl mx-auto">
                  <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-white dark:bg-gray-900 p-4">
                    <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-300 mb-4">
                      Validar marcas nuevas antes de guardar
                    </h3>
                    <BrandValidationPanel
                      jobId={jobId}
                      pendingBrands={pendingBrands}
                      onComplete={handleValidationComplete}
                    />
                  </div>
                </section>
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

        {/* Dolibarr */}
        {tab === 'dolibarr' && (
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
              </div>
            }
          >
            <DolibarrPanel />
          </Suspense>
        )}
      </main>
    </div>
  )
}

export default App
