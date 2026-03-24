/**
 * Componente de logotipo de la empresa.
 *
 * @module NsLogo
 * @author BenjaminDTS | Carlos Vico
 * @version 1.1.0
 */

import React from 'react'
import logoSrc from '@/assets/logo.png'

/** Props del componente NsLogo. */
interface NsLogoProps {
  /**
   * Tamaño en píxeles (ancho y alto).
   *
   * @default 48
   */
  size?: number
}

/**
 * Logotipo de la empresa cargado desde assets.
 *
 * @param props - Ver {@link NsLogoProps}.
 */
export const NsLogo: React.FC<NsLogoProps> = ({ size = 48 }) => (
  <img
    src={logoSrc}
    width={size}
    height={size}
    alt="Logotipo"
    style={{ objectFit: 'contain' }}
  />
)
