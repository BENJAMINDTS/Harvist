/**
 * Pantalla de inicio de Harvist.
 *
 * Muestra el logotipo de NS, el nombre de la aplicación y dos tarjetas
 * de selección de modo de trabajo: descarga de imágenes o generación de
 * descripciones con IA. También expone un acceso rápido al historial.
 *
 * @module HomeScreen
 * @author BenjaminDTS | Carlos Vico
 * @version 1.0.0
 */

import React from 'react'
import { NsLogo } from '@/components/NsLogo'

// ─── Tipos ────────────────────────────────────────────────────────────────────

/**
 * Props del componente HomeScreen.
 */
interface HomeScreenProps {
  /** Callback invocado cuando el usuario elige el modo de descarga de fotos. */
  onSelectFotos: () => void
  /** Callback invocado cuando el usuario elige el modo de generación de descripciones. */
  onSelectDescripciones: () => void
  /** Callback invocado cuando el usuario quiere ver el historial de trabajos. */
  onSelectHistorial: () => void
}

// ─── Iconos SVG inline ────────────────────────────────────────────────────────

interface IconProps {
  className?: string
  style?: React.CSSProperties
}

/**
 * Icono de cámara/imagen (outline).
 */
const CameraIcon: React.FC<IconProps> = ({ className, style }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    style={style}
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM18.75 10.5h.008v.008h-.008V10.5Z"
    />
  </svg>
)

/**
 * Icono de destellos/IA (sparkles, outline).
 */
const SparklesIcon: React.FC<IconProps> = ({ className, style }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    style={style}
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z"
    />
  </svg>
)

/**
 * Icono de historial/reloj (outline).
 */
const ClockIcon: React.FC<IconProps> = ({ className }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
    />
  </svg>
)

// ─── Componente ───────────────────────────────────────────────────────────────

/**
 * Pantalla de bienvenida con selección de modo de trabajo.
 *
 * Muestra el logo y título de la aplicación, dos tarjetas principales
 * para elegir entre descarga de imágenes o generación de descripciones,
 * y un acceso secundario al historial de trabajos anteriores.
 *
 * @author BenjaminDTS | Carlos Vico
 * @param props - Ver {@link HomeScreenProps}.
 */
export const HomeScreen: React.FC<HomeScreenProps> = ({
  onSelectFotos,
  onSelectDescripciones,
  onSelectHistorial,
}) => {
  return (
    <div className="flex flex-col items-center w-full max-w-3xl mx-auto px-4 py-12 gap-10">

      {/* ── Cabecera con logo y título ── */}
      <div className="flex flex-col items-center gap-4 text-center">
        <NsLogo size={72} />
        <div>
          <h1 className="text-4xl font-bold tracking-tight" style={{ color: '#1B5FAB' }}>
            Harvist
          </h1>
          <p className="mt-2 text-base text-gray-500 dark:text-gray-400">
            Automatización inteligente de contenido para e-commerce
          </p>
        </div>
      </div>

      {/* ── Tarjetas de selección de modo ── */}
      <div className="grid grid-cols-1 gap-5 w-full sm:grid-cols-2">

        {/* Tarjeta: Búsqueda de imágenes */}
        <button
          type="button"
          onClick={onSelectFotos}
          className="group flex flex-col gap-5 rounded-2xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 text-left shadow-sm transition-all duration-200 hover:border-blue-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          aria-label="Seleccionar modo de búsqueda de imágenes"
        >
          <div
            className="flex h-12 w-12 items-center justify-center rounded-xl transition-colors duration-200 group-hover:bg-blue-100"
            style={{ backgroundColor: '#EFF6FF' }}
          >
            <CameraIcon className="h-7 w-7 transition-colors duration-200 group-hover:text-blue-600" style={{ color: '#1B5FAB' }} />
          </div>

          <div className="flex flex-col gap-2 flex-1">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 group-hover:text-blue-700 transition-colors duration-200">
              Búsqueda de Imágenes
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">
              Descarga masiva de imágenes de producto a partir de un CSV de inventario.
            </p>
          </div>

          <div
            className="inline-flex w-full items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-colors duration-200"
            style={{ backgroundColor: '#1B5FAB' }}
            aria-hidden="true"
          >
            Comenzar
          </div>
        </button>

        {/* Tarjeta: Descripciones con IA */}
        <button
          type="button"
          onClick={onSelectDescripciones}
          className="group flex flex-col gap-5 rounded-2xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 text-left shadow-sm transition-all duration-200 hover:border-green-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
          aria-label="Seleccionar modo de generación de descripciones con IA"
        >
          <div
            className="flex h-12 w-12 items-center justify-center rounded-xl transition-colors duration-200 group-hover:bg-green-100"
            style={{ backgroundColor: '#F0FDF4' }}
          >
            <SparklesIcon className="h-7 w-7 transition-colors duration-200 group-hover:text-green-600" style={{ color: '#85C341' }} />
          </div>

          <div className="flex flex-col gap-2 flex-1">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 group-hover:text-green-700 transition-colors duration-200">
              Descripciones con IA
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">
              Genera descripciones SEO optimizadas para tus productos usando inteligencia artificial.
            </p>
          </div>

          <div
            className="inline-flex w-full items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-colors duration-200"
            style={{ backgroundColor: '#85C341' }}
            aria-hidden="true"
          >
            Comenzar
          </div>
        </button>
      </div>

      {/* ── Acceso al historial ── */}
      <button
        type="button"
        onClick={onSelectHistorial}
        className="flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-5 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-400 shadow-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        aria-label="Ver historial de trabajos anteriores"
      >
        <ClockIcon className="h-4 w-4" />
        Ver historial de trabajos
      </button>
    </div>
  )
}
