import { useState } from 'react'
import { Activity, AlertTriangle, Bot, BrainCircuit, Cpu, Database, Server, Wrench } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { badgeLabel, parseApiDateTime } from '../localization'
import type { Device } from '../types'
import { sortRecentFaults, type DashboardFault, type StatusDatum, type TrendDatum } from './aggregation'

type Summary = { total: number; active: number; unavailable: number; pendingFaults: number }
const statusColors = { active: '#18a874', inactive: '#718096', maintenance: '#e99a1e' }

export function DashboardSummary({ summary, faultsLoading }: { summary: Summary; faultsLoading: boolean }) {
  return <section className="stats-grid" aria-label="设备统计">
    <article className="stat-card" data-testid="stat-total-devices"><span className="stat-icon blue"><Cpu /></span><div><span>设备总数</span><strong>{summary.total}</strong><small>已登记设备</small></div></article>
    <article className="stat-card" data-testid="stat-active"><span className="stat-icon green"><Activity /></span><div><span>运行中</span><strong>{summary.active}</strong><small>当前正常运行</small></div></article>
    <article className="stat-card" data-testid="stat-unavailable"><span className="stat-icon slate"><Server /></span><div><span>停用 / 维护</span><strong>{summary.unavailable}</strong><small>需关注设备状态</small></div></article>
    <article className="stat-card" data-testid="stat-pending-faults"><span className="stat-icon amber"><AlertTriangle /></span><div><span>待处理故障</span><strong>{faultsLoading ? '—' : summary.pendingFaults}</strong><small>{faultsLoading ? '正在汇总故障' : '待处理与调查中'}</small></div></article>
  </section>
}

export function FaultTrendChart({ data, loading }: { data: TrendDatum[]; loading: boolean }) {
  const total = data.reduce((sum, item) => sum + item.count, 0)
  return <article className="panel dashboard-card trend-card" id="fault-trend" aria-labelledby="fault-trend-title">
    <div className="panel-header"><div><h2 id="fault-trend-title">近期故障趋势</h2><p>按本地自然日统计最近 7 天故障记录。</p></div></div>
    {loading ? <div className="chart-state" role="status"><span className="spinner" /><span>正在加载故障趋势</span></div> : total === 0 ? <div className="chart-state"><span className="empty-chart-icon"><AlertTriangle /></span><strong>最近 7 天暂无故障记录</strong><span>新增的真实故障会显示在这里。</span></div> : <div className="chart-body">
      <p className="sr-only">过去 7 天故障数量：{data.map((item) => `${item.label} ${item.count} 条`).join('，')}</p>
      <ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 8, right: 20, left: -22, bottom: 0 }}><CartesianGrid stroke="#edf0f5" strokeDasharray="4 4" vertical={false} /><XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#7b8799', fontSize: 11 }} /><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: '#7b8799', fontSize: 11 }} /><Tooltip cursor={{ fill: '#f2f6fc' }} formatter={(value) => [`${value} 条`, '故障']} /><Bar dataKey="count" fill="#2e6cf6" radius={[5, 5, 0, 0]} maxBarSize={36} /></BarChart></ResponsiveContainer>
    </div>}
  </article>
}

export function DeviceStatusChart({ data, total }: { data: StatusDatum[]; total: number }) {
  return <article className="panel dashboard-card status-card" aria-labelledby="device-status-title" aria-label="设备状态分布">
    <div className="panel-header"><div><h2 id="device-status-title">设备状态分布</h2><p>当前设备运行状态构成。</p></div></div>
    <div className="status-chart-content">
      {total === 0 ? <div className="chart-state"><span className="empty-chart-icon"><Cpu /></span><strong>暂无设备状态数据</strong></div> : <div className="donut-wrap" aria-hidden="true"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} dataKey="count" nameKey="label" innerRadius={54} outerRadius={72} paddingAngle={3} stroke="none">{data.map((item) => <Cell key={item.status} fill={statusColors[item.status]} />)}</Pie></PieChart></ResponsiveContainer><div className="donut-center"><strong>{total}</strong><span>设备总数</span></div></div>}
      <ul className="status-legend">{data.map((item) => <li key={item.status}><span className="legend-label"><i style={{ background: statusColors[item.status] }} />{item.label}</span><strong>{item.count}</strong></li>)}</ul>
    </div>
  </article>
}

const compactDateTime = new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })

export function RecentFaults({ faults, loading }: { faults: DashboardFault[]; loading: boolean }) {
  const [showAll, setShowAll] = useState(false)
  const visible = sortRecentFaults(showAll ? faults : faults.filter(({ fault }) => fault.status === 'open' || fault.status === 'investigating'))
  return <article className="panel dashboard-card recent-faults-card" id="recent-faults" aria-labelledby="recent-faults-title">
    <div className="panel-header"><div><h2 id="recent-faults-title">最近故障</h2><p>默认关注待处理问题，全部视图包含已解决历史。</p></div><div className="fault-filter" role="group" aria-label="最近故障筛选"><button className="button button-ghost" aria-pressed={!showAll} onClick={() => setShowAll(false)}>待处理</button><button className="button button-ghost" aria-pressed={showAll} onClick={() => setShowAll(true)}>全部</button><span className="count-pill">最多 5 条</span></div></div>
    {loading ? <div className="faults-state" role="status"><span className="spinner" /><span>正在加载最近故障</span></div> : visible.length === 0 ? <div className="faults-state"><span className="empty-chart-icon"><AlertTriangle /></span><strong>{showAll || faults.length === 0 ? '暂无故障记录' : '暂无待处理故障'}</strong><span>{showAll ? '当前没有已加载的故障。' : '已解决记录可在全部视图查看。'}</span></div> : <ul className="recent-fault-list" aria-label="最近故障列表">{visible.map(({ device, fault }) => <li className={fault.status === 'resolved' ? 'fault-resolved' : undefined} key={`${device.id}-${fault.id}`}><span className={`severity-marker ${fault.severity}`} /><div className="recent-fault-copy"><div><a href={`/devices/${device.id}`}>{fault.title}</a><span>{compactDateTime.format(parseApiDateTime(fault.created_at))}</span></div><p>{device.name}</p><div className="fault-badges"><span className={`badge badge-${fault.severity}`}>{badgeLabel(fault.severity)}</span><span className={`badge badge-${fault.status}`}>{badgeLabel(fault.status)}</span></div></div></li>)}</ul>}
  </article>
}

export function AiDiagnosisCard({ devices }: { devices: Device[] }) {
  const [selectedDeviceId, setSelectedDeviceId] = useState('')
  return <article className="panel dashboard-card dashboard-ai-card" id="ai-diagnosis" aria-labelledby="dashboard-ai-title">
    <span className="ai-icon"><Bot /></span><span className="eyebrow">DevicePilot Intelligence</span><h2 id="dashboard-ai-title">AI 智能诊断</h2><p>结合设备状态、历史故障与知识库，提供结构化故障分析。</p>
    <ul className="capability-list"><li><Bot /><span>AI 诊断</span><strong>已集成</strong></li><li><Database /><span>知识库增强</span><strong>已集成</strong></li><li><BrainCircuit /><span>历史上下文</span><strong>已支持</strong></li></ul>
    <label className="diagnosis-device-select">选择诊断设备<select aria-label="选择诊断设备" value={selectedDeviceId} onChange={(event) => setSelectedDeviceId(event.target.value)} disabled={devices.length === 0}><option value="">请选择设备</option>{devices.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}</select></label>
    {selectedDeviceId ? <a className="button ai-entry-button" aria-label="进入 AI 诊断" href={`/devices/${selectedDeviceId}`}><Wrench /> 进入诊断</a> : <button className="button ai-entry-button" type="button" disabled aria-label="选择设备开始诊断"><Wrench /> 选择设备开始诊断</button>}
  </article>
}
