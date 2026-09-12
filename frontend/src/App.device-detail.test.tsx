import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api/client'
import { devices, faults } from './test/fixtures'

vi.mock('./api/client', async () => ({
  ...(await vi.importActual<typeof import('./api/client')>('./api/client')),
  api: Object.fromEntries(['listDevices','getDevice','createDevice','updateDevice','deleteDevice','listFaults','createFault','getFault','diagnoseDevice'].map((name) => [name, vi.fn()])),
}))
const mockedApi = vi.mocked(api)

describe('Device detail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.pushState({}, '', '/devices/1')
    mockedApi.getDevice.mockResolvedValue(devices[0])
    mockedApi.listFaults.mockResolvedValue(faults)
  })
  it('renders device information, fault history, and the diagnosis form', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Assembly Sensor' })).toBeInTheDocument()
    expect(screen.getByText('SNS-001')).toBeInTheDocument()
    expect(await screen.findByText('Temperature spike')).toBeInTheDocument()
    expect(screen.getByLabelText('故障现象')).toHaveValue('')
    expect(screen.getByRole('button', { name: '开始诊断' })).toBeDisabled()
    expect(screen.getByText('AI 分析结果仅供辅助排查，不能替代现场检查或专业维修人员的判断。')).toBeInTheDocument()
    expect(screen.getByText('运行中', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText('高', { selector: '.badge' })).toBeInTheDocument()
  })

  it('keeps diagnosis disabled for whitespace-only descriptions', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.type(await screen.findByLabelText('故障现象'), '   ')
    expect(screen.getByRole('button', { name: '开始诊断' })).toBeDisabled()
    expect(mockedApi.diagnoseDevice).not.toHaveBeenCalled()
  })

  it('submits once while loading and renders every structured diagnosis field', async () => {
    const user = userEvent.setup()
    let resolveDiagnosis!: (value: Awaited<ReturnType<typeof api.diagnoseDevice>>) => void
    mockedApi.diagnoseDevice.mockImplementation(() => new Promise((resolve) => { resolveDiagnosis = resolve }))
    render(<App />)
    const description = await screen.findByLabelText('故障现象')
    await user.type(description, 'Motor casing is hot and makes a grinding noise.')
    const submit = screen.getByRole('button', { name: '开始诊断' })
    await user.click(submit)
    expect(mockedApi.diagnoseDevice).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: '诊断中…' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '诊断中…' }))
    expect(mockedApi.diagnoseDevice).toHaveBeenCalledTimes(1)

    resolveDiagnosis({
      risk_level: 'HIGH',
      summary: '设备可能存在较严重的机械故障。',
      possible_causes: ['轴承磨损', '润滑不足'],
      recommended_checks: ['切断电源', '检查轴承组件'],
      recommended_actions: ['保持设备停机', '安排专业人员检查'],
    })

    expect(await screen.findByText('高', { selector: '.diagnosis-risk' })).toBeInTheDocument()
    expect(screen.getByText('风险等级')).toBeInTheDocument()
    expect(screen.getByText('诊断摘要')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '建议操作' })).toBeInTheDocument()
    expect(screen.getByText('设备可能存在较严重的机械故障。')).toBeInTheDocument()
    expect(screen.getByText('轴承磨损')).toBeInTheDocument()
    expect(screen.getByText('切断电源')).toBeInTheDocument()
    expect(screen.getByText('安排专业人员检查')).toBeInTheDocument()
  })

  it('renders Chinese knowledge sources below a successful diagnosis', async () => {
    const user = userEvent.setup()
    mockedApi.diagnoseDevice.mockResolvedValue({
      risk_level: 'MEDIUM',
      summary: '需要进一步检查。',
      possible_causes: ['轴承磨损'],
      recommended_checks: ['检查轴承温度'],
      recommended_actions: ['保持停机'],
      sources: [
        { document: 'industrial-motor.md', chunk_index: 0 },
        { document: 'motor-safety.txt', chunk_index: 2 },
      ],
    })
    render(<App />)
    const description = await screen.findByLabelText('故障现象')
    await user.type(description, '电机发出研磨声')
    await user.click(screen.getByRole('button', { name: '开始诊断' }))

    expect(await screen.findByRole('heading', { name: '参考知识' })).toBeInTheDocument()
    expect(screen.getByText('industrial-motor.md · 片段 1')).toBeInTheDocument()
    expect(screen.getByText('motor-safety.txt · 片段 3')).toBeInTheDocument()
  })

  it('shows provider errors, retains the description, and allows retry', async () => {
    const user = userEvent.setup()
    mockedApi.diagnoseDevice
      .mockRejectedValueOnce(new Error('AI diagnosis is not configured'))
      .mockResolvedValueOnce({
        risk_level: 'LOW', summary: 'No immediate hazard identified.',
        possible_causes: ['Loose cover'], recommended_checks: ['Inspect cover'],
        recommended_actions: ['Tighten if safe'],
      })
    render(<App />)
    const description = await screen.findByLabelText('故障现象')
    await user.type(description, 'Intermittent rattling')
    await user.click(screen.getByRole('button', { name: '开始诊断' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('AI 诊断尚未配置，请联系管理员。')
    expect(description).toHaveValue('Intermittent rattling')
    await user.click(screen.getByRole('button', { name: '开始诊断' }))
    expect(await screen.findByText('No immediate hazard identified.')).toBeInTheDocument()
    expect(mockedApi.diagnoseDevice).toHaveBeenCalledTimes(2)
  })

  it('shows a Chinese message when the diagnosis rate limit is exceeded', async () => {
    const user = userEvent.setup()
    mockedApi.diagnoseDevice.mockRejectedValue(
      new Error('AI diagnosis rate limit exceeded'),
    )
    render(<App />)
    const description = await screen.findByLabelText('故障现象')
    await user.type(description, '设备持续振动')
    await user.click(screen.getByRole('button', { name: '开始诊断' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'AI 诊断请求过于频繁，请稍后重试。',
    )
  })

  it('shows a Chinese message for an incompatible configured provider', async () => {
    const user = userEvent.setup()
    mockedApi.diagnoseDevice.mockRejectedValue(
      new Error('Configured AI provider is not compatible with structured diagnosis'),
    )
    render(<App />)
    const description = await screen.findByLabelText('故障现象')
    await user.type(description, '设备发出异常噪音')
    await user.click(screen.getByRole('button', { name: '开始诊断' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '当前 AI 模型无法返回兼容的结构化诊断，请联系管理员。',
    )
  })

  it('clears a successful diagnosis when the fault description changes', async () => {
    const user = userEvent.setup()
    mockedApi.diagnoseDevice.mockResolvedValue({
      risk_level: 'MEDIUM', summary: 'Inspect the device before continued use.',
      possible_causes: ['Loose mounting'], recommended_checks: ['Check mounting bolts'],
      recommended_actions: ['Schedule maintenance'],
    })
    render(<App />)
    const description = await screen.findByLabelText('故障现象')
    await user.type(description, 'The device vibrates under load.')
    await user.click(screen.getByRole('button', { name: '开始诊断' }))
    expect(await screen.findByText('Inspect the device before continued use.')).toBeInTheDocument()

    await user.type(description, ' The sound is now louder.')

    expect(screen.queryByText('Inspect the device before continued use.')).not.toBeInTheDocument()
  })

  it('discards a pending diagnosis when the symptoms change', async () => {
    const user = userEvent.setup()
    let resolveDiagnosis!: (value: Awaited<ReturnType<typeof api.diagnoseDevice>>) => void
    mockedApi.diagnoseDevice.mockImplementation(() => new Promise((resolve) => { resolveDiagnosis = resolve }))
    render(<App />)
    const description = await screen.findByLabelText('故障现象')
    await user.type(description, 'Symptoms A')
    await user.click(screen.getByRole('button', { name: '开始诊断' }))
    await user.clear(description)
    await user.type(description, 'Symptoms B')
    resolveDiagnosis({ risk_level: 'HIGH', summary: 'Diagnosis for symptoms A',
      possible_causes: ['Cause A'], recommended_checks: ['Check A'], recommended_actions: ['Action A'] })
    await waitFor(() => expect(screen.getByRole('button', { name: '开始诊断' })).toBeEnabled())
    expect(description).toHaveValue('Symptoms B')
    expect(screen.queryByText('Diagnosis for symptoms A')).not.toBeInTheDocument()
  })

  it('creates a fault from validated form data and appends it to history', async () => {
    const user = userEvent.setup()
    mockedApi.createFault.mockResolvedValue({ ...faults[0], id: 14, title: 'Signal loss', description: 'No reading for ten minutes.', severity: 'critical' })
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '新增故障' }))
    await user.type(screen.getByLabelText('故障标题'), 'Signal loss')
    await user.type(screen.getByLabelText('故障描述'), 'No reading for ten minutes.')
    await user.selectOptions(screen.getByLabelText('严重程度'), 'critical')
    await user.selectOptions(screen.getByLabelText('故障状态'), 'open')
    await user.click(screen.getByRole('button', { name: '保存故障' }))
    expect(mockedApi.createFault).toHaveBeenCalledWith(1, { title: 'Signal loss', description: 'No reading for ten minutes.', severity: 'critical', status: 'open' })
    expect(await screen.findByText('Signal loss')).toBeInTheDocument()
  })
})
