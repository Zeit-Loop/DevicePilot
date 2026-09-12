import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

describe('Device management', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.listDevices.mockResolvedValue(devices)
    mockedApi.listFaults.mockResolvedValue([])
  })
  it('creates a valid device and updates the visible list', async () => {
    const user = userEvent.setup()
    mockedApi.createDevice.mockResolvedValue({ ...devices[0], id: 9, name: 'Flow Meter', serial_number: 'FLW-009' })
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '新建设备' }))
    await user.type(screen.getByLabelText('设备名称'), 'Flow Meter')
    await user.type(screen.getByLabelText('设备类型'), 'Meter')
    await user.type(screen.getByLabelText('序列号'), 'FLW-009')
    await user.type(screen.getByLabelText('位置'), 'Line C')
    await user.selectOptions(screen.getByLabelText('状态'), 'active')
    await user.click(screen.getByRole('button', { name: '创建设备' }))
    expect(mockedApi.createDevice).toHaveBeenCalledWith({ name: 'Flow Meter', device_type: 'Meter', serial_number: 'FLW-009', location: 'Line C', status: 'active' })
    expect(await screen.findByRole('link', { name: /Flow Meter/ })).toBeInTheDocument()
  })
  it('shows Chinese required-field validation', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click((await screen.findAllByRole('button', { name: '新建设备' }))[0])
    const name = screen.getByLabelText('设备名称') as HTMLInputElement
    fireEvent.invalid(name)
    expect(name.validationMessage).toBe('请填写设备名称。')
  })
  it('shows an actionable message for a duplicate serial number', async () => {
    const user = userEvent.setup()
    mockedApi.createDevice.mockRejectedValue(new Error('Serial number already exists'))
    render(<App />)
    await user.click((await screen.findAllByRole('button', { name: '新建设备' }))[0])
    await user.type(screen.getByLabelText('设备名称'), 'Flow Meter')
    await user.type(screen.getByLabelText('设备类型'), 'Meter')
    await user.type(screen.getByLabelText('序列号'), 'SNS-001')
    await user.click(screen.getByRole('button', { name: '创建设备' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('序列号已存在，请更换后重试')
  })
  it('edits an existing device and reflects the saved result', async () => {
    const user = userEvent.setup()
    mockedApi.updateDevice.mockResolvedValue({ ...devices[0], name: 'Assembly Sensor A' })
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '编辑 Assembly Sensor' }))
    const name = screen.getByLabelText('设备名称')
    await user.clear(name)
    await user.type(name, 'Assembly Sensor A')
    await user.click(screen.getByRole('button', { name: '保存修改' }))
    expect(mockedApi.updateDevice).toHaveBeenCalledWith(1, expect.objectContaining({ name: 'Assembly Sensor A' }))
    expect(await screen.findByRole('link', { name: /Assembly Sensor A/ })).toBeInTheDocument()
  })
  it('requires confirmation before deleting and removes the confirmed device', async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    mockedApi.listFaults.mockResolvedValue(faults)
    mockedApi.deleteDevice.mockResolvedValue()
    render(<App />)
    const deleteButton = await screen.findByRole('button', { name: '删除 Assembly Sensor' })
    expect(screen.getByTestId('stat-pending-faults')).toHaveTextContent(String(faults.length * devices.length))
    await user.click(deleteButton)
    expect(mockedApi.deleteDevice).not.toHaveBeenCalled()
    await user.click(deleteButton)
    expect(confirm).toHaveBeenCalledTimes(2)
    await waitFor(() => expect(mockedApi.deleteDevice).toHaveBeenCalledWith(1))
    expect(screen.queryByText('Assembly Sensor')).not.toBeInTheDocument()
    expect(screen.getByTestId('stat-pending-faults')).toHaveTextContent(String(faults.length * (devices.length - 1)))
  })
  it('shows a delete error and keeps the device when the API fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockedApi.deleteDevice.mockRejectedValue(new Error('Delete unavailable'))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '删除 Assembly Sensor' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('操作失败，请稍后重试。')
    expect(screen.getByRole('link', { name: /Assembly Sensor/ })).toBeInTheDocument()
  })
  it('prevents duplicate delete requests while deletion is pending', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockedApi.deleteDevice.mockReturnValue(new Promise(() => undefined))
    render(<App />)
    const deleteButton = await screen.findByRole('button', { name: '删除 Assembly Sensor' })
    await user.click(deleteButton)
    await waitFor(() => expect(deleteButton).toBeDisabled())
    await user.click(deleteButton)
    expect(mockedApi.deleteDevice).toHaveBeenCalledTimes(1)
  })
  it('edits a backend-valid device with a null location', async () => {
    const user = userEvent.setup()
    const deviceWithoutLocation = { ...devices[0], location: null }
    mockedApi.listDevices.mockResolvedValue([deviceWithoutLocation])
    mockedApi.updateDevice.mockResolvedValue({ ...deviceWithoutLocation, name: 'Assembly Sensor A' })
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '编辑 Assembly Sensor' }))
    expect(screen.getByLabelText('位置')).toHaveValue('')
    const name = screen.getByLabelText('设备名称')
    await user.clear(name)
    await user.type(name, 'Assembly Sensor A')
    await user.click(screen.getByRole('button', { name: '保存修改' }))
    expect(mockedApi.updateDevice).toHaveBeenCalledWith(1, expect.objectContaining({ location: null }))
  })
})
