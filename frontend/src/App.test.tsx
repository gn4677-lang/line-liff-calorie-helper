import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./AppContext', () => ({
  AppProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useApp: () => ({
    auth: { status: 'ready', message: '', headers: {} },
    activeTab: 'today',
    setActiveTab: vi.fn(),
  }),
}))

vi.mock('./pages/TodayPage', () => ({
  default: () => <div>today-page</div>,
}))

vi.mock('./pages/EatPage', () => ({
  default: () => <div>eat-page</div>,
}))

vi.mock('./pages/ProgressPage', () => ({
  default: () => <div>progress-page</div>,
}))

vi.mock('./admin/AdminApp', () => ({
  default: () => <div>admin-app</div>,
}))

describe('App', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/')
  })

  it('renders the main app shell on normal routes', () => {
    render(<App />)

    expect(screen.getByText('today-page')).toBeInTheDocument()
  })

  it('renders the admin app on admin routes', () => {
    window.history.replaceState({}, '', '/admin/observability')
    render(<App />)

    expect(screen.getByText('admin-app')).toBeInTheDocument()
  })
})
