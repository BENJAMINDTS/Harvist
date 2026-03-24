/**
 * Componente de logotipo de NS (Network Solutions / marca interna).
 *
 * Renderiza un SVG circular con anillo azul exterior y dos chevrones
 * verdes apuntando a la derecha en el interior, sobre fondo blanco.
 *
 * @module NsLogo
 * @author BenjaminDTS | Carlos Vico
 * @version 1.0.0
 */

import React from 'react'

/** Props del componente NsLogo. */
interface NsLogoProps {
  /**
   * Tamaño en píxeles del SVG (ancho y alto).
   *
   * @default 48
   */
  size?: number
}

/**
 * Logotipo SVG de NS con anillo azul y chevrones verdes.
 *
 * @param props - Ver {@link NsLogoProps}.
 */
export const NsLogo: React.FC<NsLogoProps> = ({ size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    xmlns="http://www.w3.org/2000/svg"
    aria-label="Logotipo NS"
    role="img"
  >
    {/* Fondo blanco */}
    <circle cx="50" cy="50" r="50" fill="#ffffff" />

    {/* Anillo azul exterior */}
    <circle
      cx="50"
      cy="50"
      r="46"
      fill="none"
      stroke="#1B5FAB"
      strokeWidth="8"
    />

    {/* Primer chevron verde (izquierda) */}
    <polyline
      points="28,30 44,50 28,70"
      fill="none"
      stroke="#85C341"
      strokeWidth="9"
      strokeLinecap="round"
      strokeLinejoin="round"
    />

    {/* Segundo chevron verde (derecha) */}
    <polyline
      points="46,30 62,50 46,70"
      fill="none"
      stroke="#85C341"
      strokeWidth="9"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)
