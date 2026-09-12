import type { Device, Fault } from '../types'

export const devices: Device[] = [
  { id: 1, name: 'Assembly Sensor', device_type: 'Sensor', serial_number: 'SNS-001', location: 'Line A', status: 'active', created_at: '2026-08-20T08:00:00Z', updated_at: '2026-08-20T08:00:00Z' },
  { id: 2, name: 'Cooling Pump', device_type: 'Pump', serial_number: 'PMP-002', location: 'Plant room', status: 'inactive', created_at: '2026-08-21T08:00:00Z', updated_at: '2026-08-21T08:00:00Z' },
  { id: 3, name: 'Packaging Arm', device_type: 'Robot', serial_number: 'RBT-003', location: 'Line B', status: 'maintenance', created_at: '2026-08-22T08:00:00Z', updated_at: '2026-08-22T08:00:00Z' },
]
export const faults: Fault[] = [
  { id: 11, device_id: 1, title: 'Temperature spike', description: 'Intermittent high temperature readings.', severity: 'high', status: 'open', created_at: '2026-08-26T10:30:00Z' },
]
