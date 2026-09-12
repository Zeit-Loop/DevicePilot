import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api/client'
import { devices, faults } from './test/fixtures'

vi.mock('./api/client', async () => ({
  ...(await vi.importActual<typeof import('./api/client')>('./api/client')),
  api: Object.fromEntries(['listDevices','getDevice','createDevice','updateDevice','deleteDevice','listFaults','createFault','getFault'].map((name) => [name, vi.fn()])),
}))
const mockedApi = vi.mocked(api)

describe('Dashboard', () => {
  beforeEach(() => vi.clearAllMocks())
  it('shows an accessible loading state while devices are loading', () => {
    mockedApi.listDevices.mockReturnValue(new Promise(() => undefined))
    render(<App />)
    expect(screen.getByRole('status')).toHaveTextContent('正在加载设备总览')
  })
  it('shows an actionable API error state', async () => {
    mockedApi.listDevices.mockRejectedValue(new Error('Backend unavailable'))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('操作失败，请稍后重试。')
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
  })
  it('shows a useful empty state when no devices exist', async () => {
    mockedApi.listDevices.mockResolvedValue([])
    render(<App />)
    expect(await screen.findByText('暂无设备')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '新建设备' })).toHaveLength(2)
    expect(screen.getByText('AI 驱动的设备管理与故障诊断平台')).toBeInTheDocument()
    expect(screen.getByText('暂无故障记录')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择设备开始诊断' })).toBeDisabled()
  })
  it('aggregates real per-device fault histories into dashboard statistics', async () => {
    mockedApi.listDevices.mockResolvedValue(devices)
    mockedApi.listFaults.mockImplementation(async (id) => id === 1 ? faults : id === 2 ? [{ ...faults[0], id: 12, device_id: 2 }] : [])
    render(<App />)
    await waitFor(() => expect(mockedApi.listFaults).toHaveBeenCalledTimes(3))
    expect(within(screen.getByTestId('stat-total-devices')).getByText('3')).toBeInTheDocument()
    expect(within(screen.getByTestId('stat-active')).getByText('1')).toBeInTheDocument()
    expect(within(screen.getByTestId('stat-unavailable')).getByText('2')).toBeInTheDocument()
    expect(within(screen.getByTestId('stat-pending-faults')).getByText('2')).toBeInTheDocument()
    expect(screen.getByText('运行中', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText('已停用', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText('维护中', { selector: '.badge' })).toBeInTheDocument()
    expect(within(screen.getByLabelText('设备状态分布')).getByText('运行中')).toBeInTheDocument()
    expect(within(screen.getByLabelText('设备状态分布')).getByText('已停用')).toBeInTheDocument()
    expect(within(screen.getByLabelText('设备状态分布')).getByText('维护中')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '近期故障趋势' })).toBeInTheDocument()
  })
  it('keeps successful fault data and device management available when one history fails', async () => {
    mockedApi.listDevices.mockResolvedValue(devices)
    mockedApi.listFaults.mockImplementation(async (id) => {
      if (id === 1) throw new Error('Fault history unavailable')
      if (id === 2) return [{ ...faults[0], id: 12, device_id: 2, title: 'Cooling pressure alarm' }]
      return []
    })
    render(<App />)
    expect(await screen.findByRole('link', { name: /Assembly Sensor/ })).toBeInTheDocument()
    expect(screen.getByTestId('stat-total-devices')).toHaveTextContent('3')
    expect(screen.getByTestId('stat-pending-faults')).toHaveTextContent('1')
    expect(screen.getByRole('alert')).toHaveTextContent('部分故障数据暂时无法加载')
    expect(screen.getByText('Cooling pressure alarm')).toBeInTheDocument()
  })

  it('does not restore faults for a device deleted while histories are still loading', async () => {
    const user = userEvent.setup()
    let resolveFirstHistory!: (value: typeof faults) => void
    const firstHistory = new Promise<typeof faults>((resolve) => { resolveFirstHistory = resolve })
    mockedApi.listDevices.mockResolvedValue(devices)
    mockedApi.listFaults.mockImplementation(async (id) => id === 1 ? firstHistory : [])
    mockedApi.deleteDevice.mockResolvedValue()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '删除 Assembly Sensor' }))
    await waitFor(() => expect(mockedApi.deleteDevice).toHaveBeenCalledWith(1))
    resolveFirstHistory([{ ...faults[0], title: 'Ghost fault', status: 'open' }])

    await waitFor(() => expect(screen.getByTestId('stat-pending-faults')).toHaveTextContent('0'))
    expect(screen.queryByText('Ghost fault')).not.toBeInTheDocument()
  })

  it('sorts recent faults newest first and shows device, severity, status, and time', async () => {
    mockedApi.listDevices.mockResolvedValue(devices)
    mockedApi.listFaults.mockImplementation(async (id) => id === 1 ? [
      { ...faults[0], id: 11, title: 'Older fault', created_at: '2026-09-06T10:00:00' },
      { ...faults[0], id: 12, title: 'Newest fault', severity: 'critical', created_at: '2026-09-07T10:00:00' },
    ] : [])
    render(<App />)

    const list = await screen.findByLabelText('最近故障列表')
    const items = within(list).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Newest fault')
    expect(items[0]).toHaveTextContent('Assembly Sensor')
    expect(items[0]).toHaveTextContent('严重')
    expect(items[0]).toHaveTextContent('待处理')
    expect(items[1]).toHaveTextContent('Older fault')
  })

  it('requires an explicit device selection before exposing the existing diagnosis route', async () => {
    const user = userEvent.setup()
    mockedApi.listDevices.mockResolvedValue(devices)
    mockedApi.listFaults.mockResolvedValue([])
    render(<App />)

    const select = await screen.findByRole('combobox', { name: '选择诊断设备' })
    expect(select).toHaveValue('')
    expect(screen.getByRole('button', { name: '选择设备开始诊断' })).toBeDisabled()

    await user.selectOptions(select, '2')

    expect(screen.getByRole('link', { name: '进入 AI 诊断' })).toHaveAttribute('href', '/devices/2')
  })
})
