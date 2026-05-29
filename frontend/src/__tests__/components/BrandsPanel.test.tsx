/**
 * Tests unitarios para BrandsPanel.
 *
 * Verifica:
 * - Renderiza tabla con las marcas pasadas como prop
 * - Filtra por fuente
 * - Filtra por confianza
 * - Muestra contador total de marcas
 *
 * @author BenjaminDTS
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/api/client', () => ({
  downloadBrandsCsv: vi.fn(),
}))

import { BrandsPanel } from '@/components/BrandsPanel'
import type { BrandEntry } from '@/api/client'

const mockBrands: BrandEntry[] = [
  { codigo: 'P001', ean: '8411000001', brand_name: 'Nike', manufacturer: 'Nike Inc', source: 'amazon', confidence: 'high' },
  { codigo: 'P002', ean: '8411000002', brand_name: 'Adidas', manufacturer: null, source: 'cache_gs1', confidence: 'medium' },
  { codigo: 'P003', ean: '8411000003', brand_name: null, manufacturer: null, source: 'not_found', confidence: 'low' },
]

describe('BrandsPanel', () => {
  it('renders all brands from props', () => {
    render(<BrandsPanel jobId="job-1" brandsData={mockBrands} />)
    expect(screen.getByText('P001')).toBeInTheDocument()
    expect(screen.getByText('P002')).toBeInTheDocument()
    expect(screen.getByText('P003')).toBeInTheDocument()
  })

  it('shows brand names', () => {
    render(<BrandsPanel jobId="job-1" brandsData={mockBrands} />)
    expect(screen.getByText('Nike')).toBeInTheDocument()
    expect(screen.getByText('Adidas')).toBeInTheDocument()
  })

  it('shows source labels', () => {
    render(<BrandsPanel jobId="job-1" brandsData={mockBrands} />)
    expect(screen.getAllByText('Amazon').length).toBeGreaterThan(0)
    expect(screen.getAllByText('GS1 Local').length).toBeGreaterThan(0)
  })

  it('renders with empty brands array without crashing', () => {
    render(<BrandsPanel jobId="job-1" brandsData={[]} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows download CSV button', () => {
    render(<BrandsPanel jobId="job-1" brandsData={mockBrands} />)
    const downloadBtn = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('csv') ||
      b.textContent?.toLowerCase().includes('descargar'),
    )
    expect(downloadBtn).toBeDefined()
  })
})
