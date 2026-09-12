import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Activity, AlertTriangle, BarChart3, Bot, CheckCircle2, Cpu, MapPin, Pencil, Plus, RefreshCw, Server, Table2, Trash2 } from 'lucide-react'
import { api } from './api/client'
import { DeviceForm, FaultForm } from './components/Forms'
import { AiDiagnosisCard, DashboardSummary, DeviceStatusChart, FaultTrendChart, RecentFaults } from './dashboard/DashboardSections'
import { buildDashboardData, type DashboardFault } from './dashboard/aggregation'
import { badgeLabel, formatDate, formatDateTime, localizedErrorMessage, riskLevelLabels } from './localization'
import type { Device, DeviceInput, DiagnosisResult, Fault, FaultInput, FaultStatus } from './types'

const Badge = ({ value }: { value: string }) => <span className={`badge badge-${value}`}>{badgeLabel(value)}</span>
const Spinner = ({ label }: { label: string }) => <div className="state-card" role="status"><span className="spinner" /><strong>{label}</strong><span>请稍候。</span></div>
const ErrorState = ({ message, retry }: { message: string; retry: () => void }) => <div className="state-card state-error" role="alert"><AlertTriangle /><strong>DevicePilot 加载失败</strong><span>{message}</span><button className="button button-secondary" onClick={retry}><RefreshCw size={16} /> 重试</button></div>

const dashboardNavItems = [
  { id: 'dashboard-overview', label: '设备总览', icon: Server },
  { id: 'fault-trend', label: '故障趋势', icon: BarChart3 },
  { id: 'recent-faults', label: '最近故障', icon: AlertTriangle },
  { id: 'ai-diagnosis', label: 'AI 智能诊断', icon: Bot },
  { id: 'device-list', label: '设备列表', icon: Table2 },
] as const
type DashboardSectionId = typeof dashboardNavItems[number]['id']
const isDashboardSectionId = (value: string): value is DashboardSectionId => dashboardNavItems.some((item) => item.id === value)

function Shell({ children, section = '设备总览', activeDashboardSection, onDashboardNavigate }: { children: ReactNode; section?: string; activeDashboardSection?: DashboardSectionId; onDashboardNavigate?: (id: DashboardSectionId) => void }) {
  const isDashboard = section === '设备总览'
  return <div className="app-shell"><aside className="sidebar"><a className="brand" href="/"><span className="brand-mark"><Activity /></span><span>Device<span>Pilot</span></span></a><div className="sidebar-content"><nav aria-label="主导航">{dashboardNavItems.map((item) => {
    const Icon = item.icon
    const active = isDashboard && activeDashboardSection === item.id
    return <a key={item.id} className={active ? 'active' : ''} aria-current={active ? 'location' : undefined} href={isDashboard ? `#${item.id}` : `/#${item.id}`} onClick={isDashboard ? (event) => { event.preventDefault(); onDashboardNavigate?.(item.id) } : undefined}><Icon />{item.label}</a>
  })}</nav><section className="sidebar-capabilities" aria-label="平台能力"><h2>平台能力</h2><ul><li><span>AI 诊断</span><strong>已集成</strong></li><li><span>知识库增强</span><strong>已集成</strong></li><li><span>MCP 接口</span><strong>只读</strong></li></ul></section></div><div className="sidebar-note"><span className="environment-icon"><Server /></span><span><strong>API 工作区</strong><small>本地环境</small></span></div></aside><div className="content-shell"><header className="topbar"><div><span className="eyebrow">运维控制台</span><strong>{section}</strong></div><span className="system-status"><CheckCircle2 /> 系统就绪</span></header>{children}</div></div>
}

function DiagnosisPanel({ deviceId }: { deviceId: number }) {
  const [description, setDescription] = useState('')
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult>()
  const [diagnosing, setDiagnosing] = useState(false)
  const [diagnosisError, setDiagnosisError] = useState('')
  const requestGeneration = useRef(0)

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = description.trim()
    if (!trimmed || diagnosing) return
    const generation = requestGeneration.current
    setDiagnosing(true); setDiagnosisError(''); setDiagnosis(undefined)
    try {
      const result = await api.diagnoseDevice(deviceId, { description: trimmed })
      if (requestGeneration.current === generation) setDiagnosis(result)
    } catch (error) {
      if (requestGeneration.current === generation) setDiagnosisError(localizedErrorMessage(error))
    } finally { setDiagnosing(false) }
  }

  return <article className="panel ai-panel">
    <span className="ai-icon"><Bot /></span>
    <span className="eyebrow">AI 智能维护</span>
    <h2>AI 故障诊断</h2>
    <p>描述设备当前出现的故障现象，AI 将分析风险并提供可能原因、检查步骤和处理建议。</p>
    <form className="diagnosis-form" onSubmit={(event) => void submit(event)}>
      <label htmlFor="diagnosis-description">故障现象</label>
      <textarea id="diagnosis-description" value={description} maxLength={2000} rows={4} onChange={(event) => { requestGeneration.current += 1; setDescription(event.target.value); setDiagnosis(undefined); setDiagnosisError('') }} placeholder="例如：设备外壳温度异常升高，运行时出现明显异响和振动。" />
      {diagnosisError && <div className="diagnosis-error" role="alert"><AlertTriangle /> {diagnosisError}</div>}
      <button className="button ai-button" type="submit" disabled={diagnosing || !description.trim()}><Bot /> {diagnosing ? '诊断中…' : '开始诊断'}</button>
    </form>
    {diagnosis && <section className="diagnosis-result" aria-live="polite">
      <div className="diagnosis-summary">
        <div><h3>风险等级</h3><span className={`diagnosis-risk risk-${diagnosis.risk_level.toLowerCase()}`}>{riskLevelLabels[diagnosis.risk_level]}</span></div>
        <div><h3>诊断摘要</h3><p>{diagnosis.summary}</p></div>
      </div>
      <div className="diagnosis-columns">
        <div><h3>可能原因</h3><ul>{diagnosis.possible_causes.map((item) => <li key={item}>{item}</li>)}</ul></div>
        <div><h3>建议检查</h3><ul>{diagnosis.recommended_checks.map((item) => <li key={item}>{item}</li>)}</ul></div>
        <div><h3>建议操作</h3><ul>{diagnosis.recommended_actions.map((item) => <li key={item}>{item}</li>)}</ul></div>
      </div>
      {diagnosis.sources && diagnosis.sources.length > 0 && <div className="diagnosis-sources">
        <h3>参考知识</h3>
        <ul>{diagnosis.sources.map((source) => <li key={source.document + ':' + source.chunk_index}>{source.document} · 片段 {source.chunk_index + 1}</li>)}</ul>
      </div>}
    </section>}
    <small className="ai-disclaimer">AI 分析结果仅供辅助排查，不能替代现场检查或专业维修人员的判断。</small>
  </article>
}

function Dashboard() {
  const [devices, setDevices] = useState<Device[]>([])
  const devicesRef = useRef<Device[]>([])
  const loadGenerationRef = useRef(0)
  const [dashboardFaults, setDashboardFaults] = useState<DashboardFault[]>([])
  const [faultWarning, setFaultWarning] = useState('')
  const [loading, setLoading] = useState(true)
  const [faultsLoading, setFaultsLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [deletingId, setDeletingId] = useState<number>()
  const [formDevice, setFormDevice] = useState<Device | null | undefined>(undefined)
  const [activeDashboardSection, setActiveDashboardSection] = useState<DashboardSectionId>(() => {
    const initial = window.location.hash.slice(1)
    return isDashboardSectionId(initial) ? initial : 'dashboard-overview'
  })
  const navigateToDashboardSection = useCallback((id: DashboardSectionId) => {
    setActiveDashboardSection(id)
    window.history.replaceState(null, '', `#${id}`)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])
  const load = useCallback(async () => {
    const generation = ++loadGenerationRef.current
    setLoading(true); setFaultsLoading(true); setError(''); setFaultWarning(''); setDashboardFaults([])
    try {
      const next = await api.listDevices()
      if (generation !== loadGenerationRef.current) return
      devicesRef.current = next; setDevices(next); setLoading(false)
      const histories = await Promise.allSettled(next.map((device) => api.listFaults(device.id)))
      if (generation !== loadGenerationRef.current) return
      const currentDevices = new Map(devicesRef.current.map((device) => [device.id, device]))
      setDashboardFaults(histories.flatMap((history, index) => history.status === 'fulfilled'
        ? history.value.flatMap((fault) => {
          const device = currentDevices.get(next[index].id)
          return device ? [{ device, fault }] : []
        })
        : []))
      if (histories.some((history) => history.status === 'rejected')) setFaultWarning('部分故障数据暂时无法加载，已成功加载的数据仍会正常展示。')
    } catch (err) {
      if (generation === loadGenerationRef.current) { setError(localizedErrorMessage(err)); setLoading(false) }
    } finally {
      if (generation === loadGenerationRef.current) setFaultsLoading(false)
    }
  }, [])
  useEffect(() => {
    void load()
    const refresh = () => { void load() }
    window.addEventListener('focus', refresh)
    window.addEventListener('pageshow', refresh)
    return () => {
      window.removeEventListener('focus', refresh)
      window.removeEventListener('pageshow', refresh)
    }
  }, [load])
  useEffect(() => {
    if (loading || error) return
    const requestedSection = window.location.hash.slice(1)
    if (isDashboardSectionId(requestedSection)) navigateToDashboardSection(requestedSection)
  }, [error, loading, navigateToDashboardSection])
  const dashboard = useMemo(() => buildDashboardData(devices, dashboardFaults), [devices, dashboardFaults])
  const save = async (input: DeviceInput) => {
    if (formDevice) {
      const updated = await api.updateDevice(formDevice.id, input)
      devicesRef.current = devicesRef.current.map((item) => item.id === updated.id ? updated : item)
      setDevices(devicesRef.current)
      setDashboardFaults((current) => current.map((entry) => entry.device.id === updated.id ? { ...entry, device: updated } : entry))
    } else {
      const created = await api.createDevice(input)
      devicesRef.current = [...devicesRef.current, created]
      setDevices(devicesRef.current)
    }
    setFormDevice(undefined)
  }
  const remove = async (device: Device) => {
    if (deletingId !== undefined) return
    if (!window.confirm(`确定删除“${device.name}”吗？该设备的故障记录也会被删除。`)) return
    setDeletingId(device.id); setActionError('')
    try {
      await api.deleteDevice(device.id)
      devicesRef.current = devicesRef.current.filter((item) => item.id !== device.id)
      setDevices(devicesRef.current)
      setDashboardFaults((current) => current.filter((entry) => entry.device.id !== device.id))
    } catch (err) { setActionError(localizedErrorMessage(err)) } finally { setDeletingId(undefined) }
  }
  return <Shell activeDashboardSection={activeDashboardSection} onDashboardNavigate={navigateToDashboardSection}><main className="page"><section className="page-heading" id="dashboard-overview"><div><span className="eyebrow">设备概览</span><h1>设备运行状态一览</h1><p>AI 驱动的设备管理与故障诊断平台</p></div><button className="button button-primary" onClick={() => setFormDevice(null)}><Plus /> 新建设备</button></section>
    {loading ? <Spinner label="正在加载设备总览" /> : error ? <ErrorState message={error} retry={() => void load()} /> : <>{faultWarning && <div className="inline-warning" role="alert"><AlertTriangle /> {faultWarning}</div>}{actionError && <div className="inline-warning danger" role="alert"><AlertTriangle /> {actionError}</div>}
    <DashboardSummary summary={dashboard.summary} faultsLoading={faultsLoading} />
    <section className="dashboard-grid analytics-grid">
      <FaultTrendChart data={dashboard.trend} loading={faultsLoading} />
      <DeviceStatusChart data={dashboard.statusDistribution} total={dashboard.summary.total} />
    </section>
    <section className="dashboard-grid operations-grid">
      <RecentFaults faults={dashboardFaults} loading={faultsLoading} />
      <AiDiagnosisCard devices={devices} />
    </section>
    <section className="panel devices-panel" id="device-list"><div className="panel-header"><div><h2>设备列表</h2><p>管理已登记设备并查看故障记录。</p></div><span className="count-pill">{devices.length} 台设备</span></div>
      {devices.length === 0 ? <div className="empty-state"><span className="empty-icon"><Cpu /></span><h3>暂无设备</h3><p>新建第一台设备，开始监控设备运行状态。</p><button className="button button-primary" onClick={() => setFormDevice(null)}><Plus /> 新建设备</button></div> : <div className="table-wrap"><table><thead><tr><th>设备</th><th>类型</th><th>位置</th><th>状态</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{devices.map((device) => <tr key={device.id}><td><a className="device-name" href={`/devices/${device.id}`}><span className="device-avatar"><Cpu /></span><span><strong>{device.name}</strong><small>{device.serial_number}</small></span></a></td><td>{device.device_type}</td><td><span className="location"><MapPin />{device.location ?? '未设置'}</span></td><td><Badge value={device.status} /></td><td><div className="row-actions"><button className="icon-button" aria-label={`编辑 ${device.name}`} onClick={() => setFormDevice(device)}><Pencil /></button><button className="icon-button danger" aria-label={`删除 ${device.name}`} disabled={deletingId === device.id} onClick={() => void remove(device)}><Trash2 /></button></div></td></tr>)}</tbody></table></div>}
    </section></>}{formDevice !== undefined && <DeviceForm device={formDevice ?? undefined} onClose={() => setFormDevice(undefined)} onSave={save} />}</main></Shell>
}

function FaultHistoryCard({ fault, onUpdate, onDelete }: {
  fault: Fault; onUpdate: (fault: Fault) => void; onDelete: (id: number) => void
}) {
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const [error, setError] = useState('')
  const mutate = async (status?: FaultStatus) => {
    if (pending.current) return
    if (!status && !window.confirm(`确定删除“${fault.title}”吗？此操作仅用于清理错误记录，无法恢复。正常处理请标记已解决。`)) return
    pending.current = true; setBusy(true); setError('')
    try {
      if (status) onUpdate(await api.updateFaultStatus(fault.id, { status }))
      else { await api.deleteFault(fault.id); onDelete(fault.id) }
    } catch (err) { setError(localizedErrorMessage(err)) }
    finally { pending.current = false; setBusy(false) }
  }
  return <article className={`fault-card${fault.status === 'resolved' ? ' fault-resolved' : ''}`} aria-busy={busy}>
    <span className={`severity-marker ${fault.severity}`} /><div className="fault-copy">
      <div><h3>{fault.title}</h3><span>{formatDateTime(fault.created_at)}</span></div>
      <p>{fault.description}</p><div className="fault-badges"><Badge value={fault.severity} /><Badge value={fault.status} /></div>
      <div className="fault-actions">
        {fault.status === 'open' && <button className="button button-secondary" disabled={busy} onClick={() => void mutate('investigating')}>开始调查</button>}
        {fault.status !== 'resolved' && <button className="button button-secondary" disabled={busy} onClick={() => void mutate('resolved')}>标记已解决</button>}
        {fault.status === 'resolved' && <button className="button button-secondary" disabled={busy} onClick={() => void mutate('open')}>重新打开</button>}
        <button className="button button-ghost fault-delete" disabled={busy} onClick={() => void mutate()}>删除记录</button>
      </div>
      {error && <div className="inline-warning danger" role="alert"><AlertTriangle />{error}</div>}
    </div>
  </article>
}

function DeviceDetail({ id }: { id: number }) {
  const [device, setDevice] = useState<Device>()
  const [faults, setFaults] = useState<Fault[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const load = useCallback(async () => { setLoading(true); setError(''); try { const [d, f] = await Promise.all([api.getDevice(id), api.listFaults(id)]); setDevice(d); setFaults(f) } catch (err) { setError(localizedErrorMessage(err)) } finally { setLoading(false) } }, [id])
  useEffect(() => { void load() }, [load])
  const create = async (input: FaultInput) => { const fault = await api.createFault(id, input); setFaults((current) => [fault, ...current]); setShowForm(false) }
  return <Shell section="设备详情"><main className="page">{loading ? <Spinner label="正在加载设备详情" /> : error || !device ? <ErrorState message={error || '未找到该设备。'} retry={() => void load()} /> : <><a className="back-link" href="/">← 返回设备总览</a>
    <section className="device-hero"><div className="hero-title"><span className="device-avatar large"><Cpu /></span><div><div className="title-line"><h1>{device.name}</h1><Badge value={device.status} /></div><p>{device.device_type} · {device.serial_number}</p></div></div><button className="button button-primary" onClick={() => setShowForm(true)}><Plus /> 新增故障</button></section>
    <section className="detail-grid"><article className="panel info-panel"><div className="panel-header"><div><h2>设备信息</h2><p>设备登记与运行信息。</p></div></div><dl><div><dt>序列号</dt><dd>{device.serial_number}</dd></div><div><dt>设备类型</dt><dd>{device.device_type}</dd></div><div><dt>位置</dt><dd>{device.location ?? '未设置'}</dd></div><div><dt>最后更新</dt><dd>{formatDate(device.updated_at)}</dd></div></dl></article>
      <DiagnosisPanel deviceId={id} /></section>
    <section className="panel"><div className="panel-header"><div><h2>故障记录</h2><p>该设备已登记的故障事件。</p></div><span className="count-pill">{faults.length} 条记录</span></div>{faults.length === 0 ? <div className="empty-state compact"><AlertTriangle /><h3>暂无故障记录</h3><p>该设备目前没有已登记的故障。</p></div> : <div className="fault-list">{faults.map((fault) => <FaultHistoryCard key={fault.id} fault={fault} onUpdate={(updated) => setFaults((current) => current.map((item) => item.id === updated.id ? updated : item))} onDelete={(faultId) => setFaults((current) => current.filter((item) => item.id !== faultId))} />)}</div>}</section>
    {showForm && <FaultForm onClose={() => setShowForm(false)} onSave={create} />}</>}</main></Shell>
}

export default function Application() {
  const match = window.location.pathname.match(/^\/devices\/(\d+)\/?$/)
  return match ? <DeviceDetail id={Number(match[1])} /> : <Dashboard />
}
