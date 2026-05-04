/**
 * Componente breadcrumb/navegación.
 *
 * Muestra la ruta actual y permite volver al dashboard o módulo anterior.
 *
 * @author BenjaminDTS
 */

import React from 'react'

interface BreadcrumbProps {
  /** Módulo/sección actual */
  currentModule: string
  /** Label del módulo actual (ej: "Harvist", "Dolibarr") */
  currentLabel?: string
  /** Sub-sección actual (ej: "Nuevo Job", "Productos") */
  subSection?: string
  /** Callback para volver al dashboard */
  onBackToDashboard: () => void
}

const ChevronRightIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5L15.75 12l-7.5 7.5" />
  </svg>
)

export const Breadcrumb: React.FC<BreadcrumbProps> = ({
  currentModule,
  currentLabel = currentModule,
  subSection,
  onBackToDashboard,
}) => {
  return (
    <nav className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400" aria-label="breadcrumb">
      <button
        type="button"
        onClick={onBackToDashboard}
        className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium transition-colors"
      >
        Dashboard
      </button>

      {currentModule !== 'dashboard' && (
        <>
          <ChevronRightIcon className="w-4 h-4" />
          <span className="text-gray-700 dark:text-gray-300 font-medium">
            {currentLabel}
          </span>
        </>
      )}

      {subSection && (
        <>
          <ChevronRightIcon className="w-4 h-4" />
          <span className="text-gray-700 dark:text-gray-300">
            {subSection}
          </span>
        </>
      )}
    </nav>
  )
}
