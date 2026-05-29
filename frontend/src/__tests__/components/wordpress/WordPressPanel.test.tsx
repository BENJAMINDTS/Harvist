/**
 * Tests unitarios para WordPressPanel.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/components/wordpress/WordPressProducts', () => ({ default: () => <div>MockWPProducts</div> }))
vi.mock('@/components/wordpress/WordPressCategories', () => ({ default: () => <div>MockWPCategories</div> }))
vi.mock('@/components/wordpress/WordPressBrands', () => ({ default: () => <div>MockWPBrands</div> }))
vi.mock('@/components/wordpress/WordPressOrders', () => ({ default: () => <div>MockWPOrders</div> }))
vi.mock('@/components/wordpress/WordPressCustomers', () => ({ default: () => <div>MockWPCustomers</div> }))
vi.mock('@/components/wordpress/WordPressMedia', () => ({ default: () => <div>MockWPMedia</div> }))
vi.mock('@/components/wordpress/WordPressConfig', () => ({ default: () => <div>MockWPConfig</div> }))
vi.mock('@/api/client', () => ({
  getWordPressStatus: vi.fn(),
}))

import { getWordPressStatus } from '@/api/client'
import WordPressPanel from '@/components/wordpress/WordPressPanel'

describe('WordPressPanel', () => {
  beforeEach(() => {
    vi.mocked(getWordPressStatus).mockResolvedValue({ configured: true, healthy: true } as Parameters<typeof vi.mocked<typeof getWordPressStatus>>[0] extends object ? never : Awaited<ReturnType<typeof getWordPressStatus>>)
  })

  it('shows loading spinner initially', () => {
    vi.mocked(getWordPressStatus).mockImplementation(() => new Promise(() => {}))
    render(<WordPressPanel />)
    const spinner = document.querySelector('.animate-spin')
    expect(spinner).toBeInTheDocument()
  })

  it('shows products tab when configured', async () => {
    vi.mocked(getWordPressStatus).mockResolvedValue({ configured: true, healthy: true } as never)
    render(<WordPressPanel />)
    await waitFor(() => {
      expect(screen.getByText('MockWPProducts')).toBeInTheDocument()
    })
  })

  it('switches to config tab when not configured', async () => {
    vi.mocked(getWordPressStatus).mockResolvedValue({ configured: false, healthy: false } as never)
    render(<WordPressPanel />)
    await waitFor(() => {
      expect(screen.getByText('MockWPConfig')).toBeInTheDocument()
    })
  })
})
