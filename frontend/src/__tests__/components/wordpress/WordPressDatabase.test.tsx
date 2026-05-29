/**
 * Tests unitarios para WordPressDatabase.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listWordPressDBTables: vi.fn(),
  getWordPressSiteInfo: vi.fn(),
  queryWordPressDB: vi.fn(),
  getWordPressDBConfig: vi.fn(),
  saveWordPressDBConfig: vi.fn(),
}))

import { listWordPressDBTables, getWordPressSiteInfo, getWordPressDBConfig } from '@/api/client'
import WordPressDatabase from '@/components/wordpress/WordPressDatabase'

describe('WordPressDatabase', () => {
  beforeEach(() => {
    vi.mocked(listWordPressDBTables).mockResolvedValue([
      { name: 'wp_posts', rows: 100, size_mb: 0.5 },
      { name: 'wp_users', rows: 5, size_mb: 0.1 },
    ] as never)
    vi.mocked(getWordPressSiteInfo).mockResolvedValue({ name: 'Test Site', url: 'https://wp.test', version: '6.4' } as never)
    vi.mocked(getWordPressDBConfig).mockResolvedValue({ host: 'localhost', port: 3306, db_name: 'wordpress', user: 'root', prefix: 'wp_' } as never)
  })

  it('renders without crashing', () => {
    render(<WordPressDatabase />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows DB tables after loading', async () => {
    render(<WordPressDatabase />)
    await waitFor(() => {
      const body = document.body.textContent ?? ''
      expect(body.includes('wp_posts') || body.includes('wp_users')).toBe(true)
    })
  })
})
