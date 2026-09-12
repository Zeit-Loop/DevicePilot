export type DeviceStatus = 'active' | 'inactive' | 'maintenance'
export type FaultSeverity = 'low' | 'medium' | 'high' | 'critical'
export type FaultStatus = 'open' | 'investigating' | 'resolved'

export interface Device {
  id: number
  name: string
  device_type: string
  serial_number: string
  location: string | null
  status: DeviceStatus
  created_at: string
  updated_at: string
}

export type DeviceInput = Pick<
  Device,
  'name' | 'device_type' | 'serial_number' | 'location' | 'status'
>

export interface Fault {
  id: number
  device_id: number
  title: string
  description: string
  severity: FaultSeverity
  status: FaultStatus
  created_at: string
}

export type FaultStatusUpdate = Pick<Fault, 'status'>

export type FaultInput = Pick<Fault, 'title' | 'description' | 'severity' | 'status'>

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface DiagnosisInput {
  description: string
}

export interface DiagnosisSource {
  document: string
  chunk_index: number
}

export interface DiagnosisResult {
  risk_level: RiskLevel
  summary: string
  possible_causes: string[]
  recommended_checks: string[]
  recommended_actions: string[]
  sources?: DiagnosisSource[]
}
