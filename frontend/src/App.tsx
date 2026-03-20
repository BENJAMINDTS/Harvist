/**
 * Componente raíz de la aplicación Harvist.
 *
 * Gestiona el estado global del job activo y orquesta el flujo:
 * 1. El usuario sube un CSV y configura la búsqueda (CsvUploader + SearchConfig)
 * 2. Se crea el job y se muestra el progreso en tiempo real (JobProgress)
 * 3. Al completar, se habilita la descarga del ZIP de imágenes
 * 4. Panel de historial de trabajos anteriores (JobHistory)
 *
 * @author BenjaminDTS | Carlos Vico
 */
import React, { useState } from 'react'
import { CsvUploader } from '@/components/CsvUploader'
import { SearchConfig } from '@/components/SearchConfig'
import { JobProgress } from '@/components/JobProgress'
import { JobHistory } from '@/components/JobHistory'
import { apiClient } from '@/api/client'
import type { SearchConfigValues } from '@/components/SearchConfig'

/** Estados posibles de la pantalla principal */
type AppState = 'idle' | 'configuring' | 'running' | 'done'
/** Pestañas de navegación principal */
type Tab = 'nuevo' | 'historial'

const App: React.FC = () => {
  const [tab, setTab] = useState<Tab>('nuevo')
  const [appState, setAppState] = useState<AppState>('idle')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [csvHeaders, setCsvHeaders] = useState<string[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  /** Callback: el usuario seleccionó un CSV válido — recibe el archivo y sus cabeceras */
  const handleFileSelected = (file: File, headers: string[]): void => {
    setSelectedFile(file)
    setCsvHeaders(headers)
    setError(null)
    setAppState('configuring')
  }

  /** Callback: el usuario confirmó la configuración y lanza el job */
  const handleLaunchJob = async (config: SearchConfigValues): Promise<void> => {
    if (!selectedFile) return

    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('modo', config.modo)
      formData.append('imagenes_por_producto', String(config.imagenesPorProducto))
      formData.append('generar_descripciones', String(config.generarDescripciones))
      formData.append('columna_codigo', config.columnMapping.columnaCodigo)
      formData.append('columna_ean', config.columnMapping.columnaEan)
      formData.append('columna_nombre', config.columnMapping.columnaNombre)
      formData.append('columna_marca', config.columnMapping.columnaMarca)

      const response = await apiClient.post<{
        success: boolean
        data: { job_id: string }
        message: string
      }>('/jobs', formData)

      setJobId(response.data.data.job_id)
      setAppState('running')
    } catch (err: unknown) {
      // El interceptor de apiClient rechaza con un objeto ApiError (no una instancia de Error),
      // por lo que instanceof Error sería false. Se extrae .message de ambas formas posibles.
      const msg =
        err instanceof Error
          ? err.message
          : (err as { message?: string })?.message ?? 'Error al iniciar el trabajo.'
      setError(msg)
    }
  }

  /** Callback: el job completó (exitoso o fallido) */
  const handleJobFinished = (): void => {
    setAppState('done')
  }

  /** Reinicia el flujo completo */
  const handleReset = (): void => {
    setAppState('idle')
    setSelectedFile(null)
    setCsvHeaders([])
    setJobId(null)
    setError(null)
  }

  /** Callback: desde el historial el usuario abre un job anterior */
  const handleSelectJobFromHistory = (selectedJobId: string): void => {
    setJobId(selectedJobId)
    setAppState('done')
    setTab('nuevo')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Harvist</h1>
            <p className="text-sm text-gray-500">Scraper masivo de imágenes de producto</p>
          </div>
          {/* Navegación principal */}
          <nav className="flex gap-1 bg-gray-100 p-1 rounded-lg">
            <button
              type="button"
              onClick={() => setTab('nuevo')}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
                tab === 'nuevo'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Nuevo trabajo
            </button>
            <button
              type="button"
              onClick={() => setTab('historial')}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
                tab === 'historial'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Historial
            </button>
          </nav>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-10 space-y-8">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        )}

        {tab === 'nuevo' && (
          <>
            {appState === 'idle' && (
              <CsvUploader onFileSelected={handleFileSelected} />
            )}

            {appState === 'configuring' && selectedFile && (
              <SearchConfig
                fileName={selectedFile.name}
                csvHeaders={csvHeaders}
                onLaunch={handleLaunchJob}
                onBack={handleReset}
              />
            )}

            {(appState === 'running' || appState === 'done') && jobId && (
              <JobProgress
                jobId={jobId}
                onFinished={handleJobFinished}
                onReset={handleReset}
              />
            )}
          </>
        )}

        {tab === 'historial' && (
          <JobHistory onSelectJob={handleSelectJobFromHistory} />
        )}
      </main>
    </div>
  )
}

export default App
