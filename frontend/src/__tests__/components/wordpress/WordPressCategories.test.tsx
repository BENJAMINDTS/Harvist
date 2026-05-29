/**
 * Tests unitarios para WordPressCategories.
 * listWordPressCategories returns WooCategory[] directly.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  getWordPressCategoryTree: vi.fn(),
  listWordPressCategories: vi.fn(),
  createWordPressCategory: vi.fn(),
  updateWordPressCategory: vi.fn(),
  deleteWordPressCategory: vi.fn(),
}))

import { getWordPressCategoryTree, listWordPressCategories } from '@/api/client'
import WordPressCategories from '@/components/wordpress/WordPressCategories'

describe('WordPressCategories', () => {
  beforeEach(() => {
    vi.mocked(listWordPressCategories).mockResolvedValue([
      { id: 1, name: 'Ropa', parent: 0, count: 5, children: [] },
    ] as never)
    vi.mocked(getWordPressCategoryTree).mockResolvedValue([
      { id: 1, name: 'Ropa', parent: 0, count: 5, children: [] },
    ] as never)
  })

  it('renders without crashing', () => {
    render(<WordPressCategories />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows categories after loading', async () => {
    render(<WordPressCategories />)
    await waitFor(() => {
      expect(screen.getByText('Ropa')).toBeInTheDocument()
    })
  })
})
