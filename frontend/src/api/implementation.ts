import type { Device, DeviceInput, DiagnosisInput, DiagnosisResult, Fault, FaultInput, FaultStatusUpdate } from '../types'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL.replace(/\/$/, '')}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const payload = await response.json() as { detail?: string | Array<{ msg?: string }> }
      if (typeof payload.detail === 'string') message = payload.detail
      else if (Array.isArray(payload.detail)) message = payload.detail.map((item) => item.msg).filter(Boolean).join(', ') || message
    } catch { /* Retain the status fallback for non-JSON responses. */ }
    throw new ApiError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  listDevices: () => request<Device[]>('/devices'),
  getDevice: (id: number) => request<Device>(`/devices/${id}`),
  createDevice: (input: DeviceInput) => request<Device>('/devices', { method: 'POST', body: JSON.stringify(input) }),
  updateDevice: (id: number, input: DeviceInput) => request<Device>(`/devices/${id}`, { method: 'PUT', body: JSON.stringify(input) }),
  deleteDevice: (id: number) => request<void>(`/devices/${id}`, { method: 'DELETE' }),
  listFaults: (deviceId: number) => request<Fault[]>(`/devices/${deviceId}/faults`),
  createFault: (deviceId: number, input: FaultInput) => request<Fault>(`/devices/${deviceId}/faults`, { method: 'POST', body: JSON.stringify(input) }),
  updateFaultStatus: (id: number, input: FaultStatusUpdate) => request<Fault>(`/faults/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteFault: (id: number) => request<void>(`/faults/${id}`, { method: 'DELETE' }),
  getFault: (id: number) => request<Fault>(`/faults/${id}`),
  diagnoseDevice: (id: number, input: DiagnosisInput) => request<DiagnosisResult>(`/devices/${id}/diagnose`, { method: 'POST', body: JSON.stringify(input) }),
}
