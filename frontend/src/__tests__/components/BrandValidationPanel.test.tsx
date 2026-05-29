/**
 * Tests unitarios para BrandValidationPanel.
 *
 * BrandValidationPanel recibe pendingBrands como prop.
 * @author BenjaminDTS
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/api/client', () => ({
  validateBrands: vi.fn(),
}))

import BrandValidationPanel from '@/components/BrandValidationPanel'
import type { BrandPendingEntry } from '@/api/client'

const mockPendingBrands: BrandPendingEntry[] = [
  { ean: '8411000001', brand_name: 'Nike', source: 'amazon', confidence: 'high', prefijo: '8411000' },
  { ean: '8411000002', brand_name: 'Adidas', source: 'cache_gs1', confidence: 'medium', prefijo: '8411000' },
]

describe('BrandValidationPanel', () => {
  it('renders without crashing with pending brands', () => {
    render(
      <BrandValidationPanel
        jobId="job-1"
        pendingBrands={mockPendingBrands}
        onComplete={vi.fn()}
      />,
    )
    expect(document.body).toBeInTheDocument()
  })

  it('shows EAN codes for pending brands', () => {
    render(
      <BrandValidationPanel
        jobId="job-1"
        pendingBrands={mockPendingBrands}
        onComplete={vi.fn()}
      />,
    )
    expect(screen.getByText('8411000001')).toBeInTheDocument()
    expect(screen.getByText('8411000002')).toBeInTheDocument()
  })

  it('shows brand names via input values or text', () => {
    render(
      <BrandValidationPanel
        jobId="job-1"
        pendingBrands={mockPendingBrands}
        onComplete={vi.fn()}
      />,
    )
    // Brand name may be in input value or text node
    const nikeEl =
      document.querySelector('[value="Nike"]') ||
      screen.queryByText('Nike') ||
      screen.queryByDisplayValue('Nike')
    expect(nikeEl).not.toBeNull()
  })

  it('renders empty brands gracefully', () => {
    render(
      <BrandValidationPanel
        jobId="job-1"
        pendingBrands={[]}
        onComplete={vi.fn()}
      />,
    )
    expect(document.body).toBeInTheDocument()
  })
})
