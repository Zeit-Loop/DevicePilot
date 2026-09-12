import { useState, type FormEvent } from 'react'
import { X } from 'lucide-react'
import { deviceStatusLabels, faultSeverityLabels, faultStatusLabels, localizedErrorMessage } from '../localization'
import type { Device, DeviceInput, DeviceStatus, FaultInput, FaultSeverity, FaultStatus } from '../types'

export function DeviceForm({ device, onClose, onSave }: { device?: Device; onClose: () => void; onSave: (value: DeviceInput) => Promise<void> }) {
  const [value, setValue] = useState<DeviceInput>(device ? { name: device.name, device_type: device.device_type, serial_number: device.serial_number, location: device.location, status: device.status } : { name: '', device_type: '', serial_number: '', location: '', status: 'active' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const set = (field: keyof DeviceInput, next: string) => setValue((current) => ({ ...current, [field]: next }))
  const submit = async (event: FormEvent) => { event.preventDefault(); setSaving(true); setError(''); try { await onSave({ ...value, name: value.name.trim(), serial_number: value.serial_number.trim(), location: value.location?.trim() || null }) } catch (err) { setError(localizedErrorMessage(err)); setSaving(false) } }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="device-form-title">
    <div className="modal-header"><div><span className="eyebrow">设备登记</span><h2 id="device-form-title">{device ? '编辑设备' : '新建设备'}</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭表单"><X /></button></div>
    <form onSubmit={submit} className="form-grid">{error && <p className="form-error" role="alert">{error}</p>}
      <label>设备名称<input required value={value.name} onChange={(e) => set('name', e.target.value)} onInvalid={(e) => e.currentTarget.setCustomValidity('请填写设备名称。')} onInput={(e) => e.currentTarget.setCustomValidity('')} placeholder="例如：装配线传感器" /></label>
      <label>设备类型<input required value={value.device_type} onChange={(e) => set('device_type', e.target.value)} onInvalid={(e) => e.currentTarget.setCustomValidity('请填写设备类型。')} onInput={(e) => e.currentTarget.setCustomValidity('')} placeholder="例如：温度传感器" /></label>
      <label>序列号<input required value={value.serial_number} onChange={(e) => set('serial_number', e.target.value)} onInvalid={(e) => e.currentTarget.setCustomValidity('请填写序列号。')} onInput={(e) => e.currentTarget.setCustomValidity('')} placeholder="例如：SNS-001" /></label>
      <label>位置<input value={value.location ?? ''} onChange={(e) => set('location', e.target.value)} placeholder="例如：A 产线（选填）" /></label>
      <label className="full-width">状态<select value={value.status} onChange={(e) => set('status', e.target.value as DeviceStatus)}><option value="active">{deviceStatusLabels.active}</option><option value="inactive">{deviceStatusLabels.inactive}</option><option value="maintenance">{deviceStatusLabels.maintenance}</option></select></label>
      <div className="form-actions full-width"><button type="button" className="button button-ghost" onClick={onClose}>取消</button><button className="button button-primary" disabled={saving}>{saving ? '保存中…' : device ? '保存修改' : '创建设备'}</button></div>
    </form></section></div>
}

export function FaultForm({ onClose, onSave }: { onClose: () => void; onSave: (value: FaultInput) => Promise<void> }) {
  const [value, setValue] = useState<FaultInput>({ title: '', description: '', severity: 'medium', status: 'open' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const set = (field: keyof FaultInput, next: string) => setValue((current) => ({ ...current, [field]: next }))
  const submit = async (event: FormEvent) => { event.preventDefault(); setSaving(true); setError(''); try { await onSave({ ...value, title: value.title.trim(), description: value.description.trim() }) } catch (err) { setError(localizedErrorMessage(err)); setSaving(false) } }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="fault-form-title"><div className="modal-header"><div><span className="eyebrow">故障登记</span><h2 id="fault-form-title">新增故障</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭表单"><X /></button></div>
    <form onSubmit={submit} className="form-grid">{error && <p className="form-error" role="alert">{error}</p>}
      <label className="full-width">故障标题<input required value={value.title} onChange={(e) => set('title', e.target.value)} onInvalid={(e) => e.currentTarget.setCustomValidity('请填写故障标题。')} onInput={(e) => e.currentTarget.setCustomValidity('')} placeholder="简要描述故障" /></label>
      <label className="full-width">故障描述<textarea required rows={4} value={value.description} onChange={(e) => set('description', e.target.value)} onInvalid={(e) => e.currentTarget.setCustomValidity('请填写故障描述。')} onInput={(e) => e.currentTarget.setCustomValidity('')} placeholder="请填写故障现象、发生时间和现场观察" /></label>
      <label>严重程度<select value={value.severity} onChange={(e) => set('severity', e.target.value as FaultSeverity)}><option value="low">{faultSeverityLabels.low}</option><option value="medium">{faultSeverityLabels.medium}</option><option value="high">{faultSeverityLabels.high}</option><option value="critical">{faultSeverityLabels.critical}</option></select></label>
      <label>故障状态<select value={value.status} onChange={(e) => set('status', e.target.value as FaultStatus)}><option value="open">{faultStatusLabels.open}</option><option value="investigating">{faultStatusLabels.investigating}</option><option value="resolved">{faultStatusLabels.resolved}</option></select></label>
      <div className="form-actions full-width"><button type="button" className="button button-ghost" onClick={onClose}>取消</button><button className="button button-primary" disabled={saving}>{saving ? '保存中…' : '保存故障'}</button></div>
    </form></section></div>
}
