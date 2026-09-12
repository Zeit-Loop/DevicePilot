import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api/client'
import { devices } from './test/fixtures'

vi.mock('./api/client', async () => ({
  ...(await vi.importActual<typeof import('./api/client')>('./api/client')),
  api: Object.fromEntries(['listDevices','getDevice','createDevice','updateDevice','deleteDevice','listFaults','createFault','getFault'].map((name) => [name, vi.fn()])),
}))
const mockedApi = vi.mocked(api)

describe('Sidebar dashboard navigation', () => {
  const scrollIntoView = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/')
    Element.prototype.scrollIntoView = scrollIntoView
    mockedApi.listDevices.mockResolvedValue([])
    mockedApi.listFaults.mockResolvedValue([])
  })

  it.each([
    ['设备总览', 'dashboard-overview'],
    ['故障趋势', 'fault-trend'],
    ['最近故障', 'recent-faults'],
    ['AI 智能诊断', 'ai-diagnosis'],
    ['设备列表', 'device-list'],
  ])('scrolls %s to its existing dashboard section', async (label, sectionId) => {
    const user = userEvent.setup()
    render(<App />)
    const link = await screen.findByRole('link', { name: label })

    await user.click(link)

    const section = document.getElementById(sectionId)
    expect(section).not.toBeNull()
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    expect(link).toHaveClass('active')
  })

  it('returns from device detail to the requested dashboard section', async () => {
    window.history.replaceState({}, '', '/devices/1')
    mockedApi.getDevice.mockResolvedValue(devices[0])
    mockedApi.listFaults.mockResolvedValue([])
    render(<App />)

    const overviewLink = await screen.findByRole('link', { name: '设备总览' })
    const diagnosisLink = screen.getByRole('link', { name: 'AI 智能诊断' })
    expect(overviewLink).toHaveAttribute('href', '/#dashboard-overview')
    expect(diagnosisLink).toHaveAttribute('href', '/#ai-diagnosis')
  })

  it('scrolls to a dashboard hash after sections finish rendering', async () => {
    window.history.replaceState({}, '', '/#ai-diagnosis')
    render(<App />)

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' }))
    expect(screen.getByRole('link', { name: 'AI 智能诊断' })).toHaveClass('active')
  })

  it('renders platform capabilities as non-interactive information', async () => {
    render(<App />)
    const capabilities = await screen.findByRole('region', { name: '平台能力' })

    expect(within(capabilities).getByText('AI 诊断')).toBeInTheDocument()
    expect(within(capabilities).getByText('知识库增强')).toBeInTheDocument()
    expect(within(capabilities).getByText('MCP 接口')).toBeInTheDocument()
    expect(within(capabilities).getAllByText('已集成')).toHaveLength(2)
    expect(within(capabilities).getByText('只读')).toBeInTheDocument()
    expect(within(capabilities).queryByRole('link')).not.toBeInTheDocument()
    expect(within(capabilities).queryByRole('button')).not.toBeInTheDocument()
  })
})
