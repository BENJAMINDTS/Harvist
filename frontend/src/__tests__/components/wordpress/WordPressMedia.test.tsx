/**
 * Tests unitarios para WordPressMedia.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listWordPressMedia: vi.fn(),
  uploadWordPressMedia: vi.fn(),
}))

import { listWordPressMedia } from '@/api/client'
import WordPressMedia from '@/components/wordpress/WordPressMedia'

describe('WordPressMedia', () => {
  beforeEach(() => {
    vi.mocked(listWordPressMedia).mockResolvedValue([
      { id: 1, title: { rendered: 'producto-001.jpg' }, source_url: 'https://wp.test/media/1.jpg', mime_type: 'image/jpeg' },
    ] as never)
  })

  it('renders without crashing', () => {
    render(<WordPressMedia />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows media items after loading', async () => {
    render(<WordPressMedia />)
    await waitFor(() => {
      const body = document.body.textContent ?? ''
      expect(body.includes('producto-001') || body.includes('.jpg')).toBe(true)
    })
  })
})
