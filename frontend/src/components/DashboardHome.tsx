/**
 * Dashboard de inicio con acceso a 4 módulos principales.
 *
 * Pantalla principal que permite seleccionar entre:
 * - Harvist: enriquecimiento de productos via CSV
 * - Dolibarr: sincronización de inventario
 * - Odoo: sincronización de productos
 * - WordPress: sincronización de tienda online
 *
 * @author BenjaminDTS | Carlos Vico
 */

import React from 'react'
import { NsLogo } from '@/components/NsLogo'

interface DashboardHomeProps {
  onSelectHarvist: () => void
  onSelectDolibarr: () => void
  onSelectOdoo: () => void
  onSelectWordpress: () => void
}

interface IconProps {
  className?: string
}

const ImageDownloadIcon: React.FC<IconProps> = ({ className }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33A3 3 0 0116.5 19.5H6.75z" />
  </svg>
)

const CubeIcon: React.FC<IconProps> = ({ className }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M21 7.5l-9-5.25L3 7.5m0 0l9-5.25m0 0l9 5.25m-18 0l9 5.25m0 0l9-5.25m-9 5.25v10.5m0 0l-9-5.25m0 0V19.5m0 0l9 5.25m0 0h.008v.008H12m0 0h.008v.008H12" />
  </svg>
)


const GlobalIcon: React.FC<IconProps> = ({ className }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21c2.485 0 4.845-.889 6.604-2.472M12 21c-2.485 0-4.845-.889-6.604-2.472m0 0A8.966 8.966 0 012.25 12c0-4.556 3.232-8.414 7.466-9.176m6.615 5.486a11.955 11.955 0 01-2.025 4.117m-6.615-4.589a8.966 8.966 0 00-5.66 7.752m0 0a8.966 8.966 0 007.921 4.24m0 0A8.966 8.966 0 0012 2.25" />
  </svg>
)

const ModuleCard: React.FC<{
  title: string
  description: string
  icon: React.ReactNode
  iconBg: string
  iconColor: string
  buttonColor: string
  onClick: () => void
}> = ({ title, description, icon, iconBg, iconColor, buttonColor, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="group flex flex-col gap-3 rounded-2xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 text-left shadow-sm transition-all duration-200 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-offset-2"
    style={{
      '--tw-ring-color': buttonColor,
    } as React.CSSProperties}
  >
    <div
      className="flex h-10 w-10 items-center justify-center rounded-xl transition-colors duration-200"
      style={{ backgroundColor: iconBg }}
    >
      <div style={{ color: iconColor }}>
        {icon}
      </div>
    </div>

    <div className="flex flex-col gap-2 flex-1">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 group-hover:text-blue-700 transition-colors duration-200">
        {title}
      </h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">
        {description}
      </p>
    </div>

    <div
      className="inline-flex w-full items-center justify-center rounded-lg px-4 py-2 text-sm font-semibold text-white transition-colors duration-200"
      style={{ backgroundColor: buttonColor }}
      aria-hidden="true"
    >
      Acceder
    </div>
  </button>
)

export const DashboardHome: React.FC<DashboardHomeProps> = ({
  onSelectHarvist,
  onSelectDolibarr,
  onSelectOdoo,
  onSelectWordpress,
}) => {
  return (
    <div className="flex flex-col items-center w-full max-w-4xl mx-auto px-4 py-4 gap-6">
      <div className="flex flex-col items-center gap-2 text-center">
        <NsLogo size={52} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight" style={{ color: '#1B5FAB' }}>
            Harvist
          </h1>
          <p className="mt-2 text-base text-gray-500 dark:text-gray-400">
            Plataforma integrada de enriquecimiento y sincronización de catálogos
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 w-full sm:grid-cols-2">
        <ModuleCard
          title="Harvist"
          description="Enriquecimiento masivo de productos: imágenes, descripciones SEO y resolución de marcas desde CSV"
          icon={<ImageDownloadIcon className="h-6 w-6" />}
          iconBg="#EFF6FF"
          iconColor="#1B5FAB"
          buttonColor="#1B5FAB"
          onClick={onSelectHarvist}
        />

        <ModuleCard
          title="Dolibarr"
          description="Sincronización de productos, categorías, proveedores, pedidos, facturas e inventario con tu ERP Dolibarr"
          icon={<CubeIcon className="h-6 w-6" />}
          iconBg="#FEF3C7"
          iconColor="#D97706"
          buttonColor="#D97706"
          onClick={onSelectDolibarr}
        />

        <ModuleCard
          title="Odoo"
          description="Gestión integrada de productos, variantes, partners, compras, ventas e inventario en Odoo"
          icon={<CubeIcon className="h-6 w-6" />}
          iconBg="#DDD6FE"
          iconColor="#6366F1"
          buttonColor="#6366F1"
          onClick={onSelectOdoo}
        />

        <ModuleCard
          title="WordPress/WooCommerce"
          description="Publicación de productos, variantes, categorías, atributos, pedidos y clientes en tu tienda online"
          icon={<GlobalIcon className="h-6 w-6" />}
          iconBg="#F0FDF4"
          iconColor="#16A34A"
          buttonColor="#16A34A"
          onClick={onSelectWordpress}
        />
      </div>

    </div>
  )
}
