/**
 * Tests unitarios para WordPressBrands.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listWordPressBrands: vi.fn(),
  createWordPressBrand: vi.fn(),
  updateWordPressBrand: vi.fn(),
  deleteWordPressBrand: vi.fn(),
  getWordPressBrandAttribute: vi.fn(),
  listWordPressAllAttributes: vi.fn(),
  configureWordPressBrandAttribute: vi.fn(),
}))

import { listWordPressBrands, getWordPressBrandAttribute, listWordPressAllAttributes } from '@/api/client'
import WordPressBrands from '@/components/wordpress/WordPressBrands'

describe('WordPressBrands', () => {
  beforeEach(() => {
    vi.mocked(getWordPressBrandAttribute).mockResolvedValue({ mode: 'native' } as never)
    vi.mocked(listWordPressAllAttributes).mockResolvedValue([] as never)
    vi.mocked(listWordPressBrands).mockResolvedValue([
      { id: 1, name: 'Nike', slug: 'nike', count: 3 },
    ] as never)
  })

  it('renders without crashing', () => {
    render(<WordPressBrands />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows brands after loading', async () => {
    render(<WordPressBrands />)
    await waitFor(() => {
      expect(screen.getByText('Nike')).toBeInTheDocument()
    })
  })
})
