/**
 * Tests unitarios para WordPressConfig.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  getWordPressConfig: vi.fn(),
  saveWordPressConfig: vi.fn(),
  getWordPressDBConfig: vi.fn(),
  saveWordPressDBConfig: vi.fn(),
}))

import { getWordPressConfig, getWordPressDBConfig } from '@/api/client'
import WordPressConfig from '@/components/wordpress/WordPressConfig'

describe('WordPressConfig', () => {
  beforeEach(() => {
    vi.mocked(getWordPressConfig).mockResolvedValue({
      wordpress_url: 'https://wp.test',
      wordpress_consumer_key: 'ck_xxx',
      wordpress_consumer_secret: 'cs_xxx',
    } as never)
    vi.mocked(getWordPressDBConfig).mockResolvedValue({
      host: 'localhost', port: 3306, db_name: 'wordpress', user: 'root', prefix: 'wp_',
    } as never)
  })

  it('renders without crashing', () => {
    render(<WordPressConfig onSaved={vi.fn()} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows form inputs', async () => {
    render(<WordPressConfig onSaved={vi.fn()} />)
    await waitFor(() => {
      const inputs = document.querySelectorAll('input')
      expect(inputs.length).toBeGreaterThan(0)
    })
  })
})
