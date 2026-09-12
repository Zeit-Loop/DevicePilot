import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api/client'
import { devices, faults } from './test/fixtures'
import type { Fault, FaultStatus } from './types'

vi.mock('./api/client', async () => ({
  ...(await vi.importActual<typeof import('./api/client')>('./api/client')),
  api: Object.fromEntries(['listDevices', 'getDevice', 'listFaults', 'updateFaultStatus', 'deleteFault'].map(name => [name, vi.fn()])),
}))
const mock = vi.mocked(api)
beforeEach(() => {
  vi.resetAllMocks()
  window.history.pushState({}, '', '/devices/1')
  mock.getDevice.mockResolvedValue(devices[0])
  mock.listDevices.mockResolvedValue([devices[0]])
  mock.listFaults.mockResolvedValue([faults[0]])
})

describe('Fault lifecycle', () => {
  it.each<[FaultStatus, string, FaultStatus, string]>([
    ['open', '开始调查', 'investigating', '调查中'],
    ['open', '标记已解决', 'resolved', '已解决'],
    ['investigating', '标记已解决', 'resolved', '已解决'],
    ['resolved', '重新打开', 'open', '待处理'],
  ])('%s via %s becomes %s without losing history', async (status, action, next, label) => {
    mock.listFaults.mockResolvedValue([{ ...faults[0], status }])
    mock.updateFaultStatus.mockResolvedValue({ ...faults[0], status: next })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: action }))
    expect(mock.updateFaultStatus).toHaveBeenCalledWith(faults[0].id, { status: next })
    expect(await screen.findByText(label, { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText(faults[0].title)).toBeInTheDocument()
    expect(mock.listFaults).toHaveBeenCalledTimes(1)
    if (next === 'resolved') expect(screen.getByText(faults[0].title).closest('article')).toHaveClass('fault-resolved')
  })
  it('disables fault actions while updating, retains history and shows errors on failure', async () => {
    let reject!: (error: Error) => void
    mock.updateFaultStatus.mockReturnValue(new Promise((_, fail) => { reject = fail }))
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: '开始调查' }))
    for (const name of ['开始调查', '标记已解决', '删除记录']) expect(screen.getByRole('button', { name })).toBeDisabled()
    await act(async () => reject(new Error('Failed to fetch')))
    expect(await screen.findByRole('alert')).toHaveTextContent('无法连接后端服务')
    expect(screen.getByRole('button', { name: '开始调查' })).toBeEnabled()
    expect(screen.getByText(faults[0].title)).toBeInTheDocument()
  })
  it('cancels deletion before calling the API', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: '删除记录' }))
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining(faults[0].title))
    expect(mock.deleteFault).not.toHaveBeenCalled()
    expect(screen.getByText(faults[0].title)).toBeInTheDocument()
  })
  it('confirms deletion, disables actions, removes only the target history', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    let resolve!: () => void
    mock.deleteFault.mockReturnValue(new Promise(done => { resolve = done }))
    mock.listFaults.mockResolvedValue([faults[0], { ...faults[0], id: 999, title: 'Keep history' }])
    render(<App />)
    const card = (await screen.findByText(faults[0].title)).closest('article')!
    await userEvent.click(within(card).getByRole('button', { name: '删除记录' }))
    expect(within(card).getByRole('button', { name: '删除记录' })).toBeDisabled()
    await act(async () => resolve())
    expect(mock.deleteFault).toHaveBeenCalledWith(faults[0].id)
    expect(screen.queryByText(faults[0].title)).not.toBeInTheDocument()
    expect(screen.getByText('Keep history')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: devices[0].name })).toBeInTheDocument()
  })
  it('keeps the fault when deletion fails', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mock.deleteFault.mockRejectedValue(new Error('Failed to fetch'))
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: '删除记录' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('无法连接后端服务')
    expect(screen.getByText(faults[0].title)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除记录' })).toBeEnabled()
  })
})

describe('Dashboard lifecycle consistency', () => {
  it.each(['focus', 'pageshow'])('refreshes KPI and pending/history on %s after resolution and reopening', async event => {
    window.history.pushState({}, '', '/')
    let history: Fault[] = [{ ...faults[0], status: 'open' }]
    mock.listFaults.mockImplementation(async () => history)
    render(<App />)
    expect(await screen.findByText(faults[0].title)).toBeInTheDocument()
    expect(screen.getByTestId('stat-pending-faults').querySelector('strong')).toHaveTextContent('1')
    history = [{ ...faults[0], status: 'resolved' }]
    act(() => window.dispatchEvent(new Event(event)))
    await waitFor(() => expect(screen.getByTestId('stat-pending-faults').querySelector('strong')).toHaveTextContent('0'))
    expect(screen.queryByText(faults[0].title)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '全部' }))
    expect(screen.getByText(faults[0].title)).toBeInTheDocument()
    expect(screen.getByText('已解决', { selector: '.badge' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '待处理' }))
    history = [{ ...faults[0], status: 'open' }]
    act(() => window.dispatchEvent(new Event(event)))
    expect(await screen.findByText(faults[0].title)).toBeInTheDocument()
    expect(screen.getByTestId('stat-pending-faults').querySelector('strong')).toHaveTextContent('1')
  })
  it('filters before taking the five most recent faults', async () => {
    window.history.pushState({}, '', '/')
    mock.listFaults.mockResolvedValue([
      ...Array.from({ length: 6 }, (_, i) => ({ ...faults[0], id: i + 50, status: 'resolved' as const, title: `Resolved ${i}`, created_at: '2026-09-09T10:00:00Z' })),
      { ...faults[0], title: 'Older pending', status: 'investigating', created_at: '2026-09-01T10:00:00Z' },
    ])
    render(<App />)
    expect(await screen.findByText('Older pending')).toBeInTheDocument()
    expect(screen.queryByText('Resolved 5')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '全部' }))
    expect(within(screen.getByLabelText('最近故障列表')).getAllByRole('listitem')).toHaveLength(5)
    expect(screen.getByText('Resolved 5')).toBeInTheDocument()
  })
})