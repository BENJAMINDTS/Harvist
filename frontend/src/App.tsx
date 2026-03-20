/**
 * Componente raíz de la aplicación Harvist.
 *
 * Gestiona el estado global del job activo y orquesta el flujo:
 * 1. El usuario sube un CSV y configura la búsqueda (CsvUploader + SearchConfig)
 * 2. Se crea el job y se muestra el progreso en tiempo real (JobProgress)
 * 3. Al completar, se habilita la descarga del ZIP de imágenes
 *
 * @author BenjaminDTS | Carlos Vico
 */
import React, { useState } from 'react'
import { CsvUploader } from '@/components/CsvUploader'
import { SearchConfig } from '@/components/SearchConfig'
import { JobProgress } from '@/components/JobProgress'
import { apiClient } from '@/api/client'
import type { SearchConfigValues } from '@/components/SearchConfig'

/** Estados posibles de la pantalla principal */
type AppState = 'idle' | 'configuring' | 'running' | 'done'

const App: React.FC = () => {
  const [appState, setAppState] = useState<AppState>('idle')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  /** Callback: el usuario seleccionó un CSV válido */
  const handleFileSelected = (file: File): void => {
    setSelectedFile(file)
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

      const response = await apiClient.post<{
        success: boolean
        data: { job_id: string }
        message: string
      }>('/jobs', formData)

      setJobId(response.data.data.job_id)
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

  /** Reinicia el flujo completo */
  const handleReset = (): void => {
    setAppState('idle')
    setSelectedFile(null)
    setJobId(null)
    setError(null)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <h1 className="text-2xl font-bold text-gray-900">Harvist</h1>
        <p className="text-sm text-gray-500">Scraper masivo de imágenes de producto</p>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-10 space-y-8">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        )}

        {appState === 'idle' && (
          <CsvUploader onFileSelected={handleFileSelected} />
        )}

        {appState === 'configuring' && selectedFile && (
          <SearchConfig
            fileName={selectedFile.name}
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
      </main>
    </div>
  )
}

export default App
