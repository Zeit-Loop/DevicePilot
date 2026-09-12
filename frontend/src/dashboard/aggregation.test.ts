import { describe, expect, it } from 'vitest'
import { parseApiDateTime } from '../localization'
import { buildDashboardData, buildSevenDayTrend, sortRecentFaults } from './aggregation'
import type { Device, Fault } from '../types'

const devices: Device[] = [
  { id: 1, name: 'Pump A', device_type: 'Pump', serial_number: 'P-1', location: null, status: 'active', created_at: '2026-09-01T00:00:00', updated_at: '2026-09-01T00:00:00' },
  { id: 2, name: 'Pump B', device_type: 'Pump', serial_number: 'P-2', location: null, status: 'inactive', created_at: '2026-09-01T00:00:00', updated_at: '2026-09-01T00:00:00' },
  { id: 3, name: 'Pump C', device_type: 'Pump', serial_number: 'P-3', location: null, status: 'maintenance', created_at: '2026-09-01T00:00:00', updated_at: '2026-09-01T00:00:00' },
]

const fault = (overrides: Partial<Fault>): Fault => ({
  id: 1,
  device_id: 1,
  title: 'Fault',
  description: 'Description',
  severity: 'medium',
  status: 'open',
  created_at: '2026-09-07T12:00:00',
  ...overrides,
})

describe('dashboard aggregation', () => {
  it('counts device states and only unresolved faults from successfully loaded histories', () => {
    const result = buildDashboardData(devices, [
      { device: devices[0], fault: fault({ id: 1, status: 'open' }) },
      { device: devices[0], fault: fault({ id: 2, status: 'investigating' }) },
      { device: devices[1], fault: fault({ id: 3, device_id: 2, status: 'resolved' }) },
    ])

    expect(result.summary).toEqual({ total: 3, active: 1, unavailable: 2, pendingFaults: 2 })
    expect(result.statusDistribution).toEqual([
      { status: 'active', label: '运行中', count: 1 },
      { status: 'inactive', label: '已停用', count: 1 },
      { status: 'maintenance', label: '维护中', count: 1 },
    ])
  })

  it('sorts recent faults by created_at DESC and uses fault id as a stable tie-breaker', () => {
    const entries = [
      { device: devices[0], fault: fault({ id: 2, title: 'Second', created_at: '2026-09-07T10:00:00' }) },
      { device: devices[0], fault: fault({ id: 3, title: 'Newest tie', created_at: '2026-09-07T11:00:00' }) },
      { device: devices[0], fault: fault({ id: 1, title: 'Older tie', created_at: '2026-09-07T11:00:00' }) },
    ]

    expect(sortRecentFaults(entries).map(({ fault: item }) => item.id)).toEqual([3, 1, 2])
  })

  it('aggregates the last seven user-local calendar days instead of UTC dates', () => {
    const now = new Date(2026, 8, 7, 12, 0, 0)
    const localPreviousDay = new Date(2026, 8, 6, 23, 30, 0).toISOString()
    const localToday = new Date(2026, 8, 7, 0, 15, 0).toISOString()
    const outsideWindow = new Date(2026, 7, 31, 23, 59, 59).toISOString()

    const trend = buildSevenDayTrend([
      { device: devices[0], fault: fault({ id: 1, created_at: localPreviousDay }) },
      { device: devices[0], fault: fault({ id: 2, created_at: localToday }) },
      { device: devices[0], fault: fault({ id: 3, created_at: outsideWindow }) },
    ], now)

    expect(trend.map(({ label, count }) => [label, count])).toEqual([
      ['09/01', 0], ['09/02', 0], ['09/03', 0], ['09/04', 0],
      ['09/05', 0], ['09/06', 1], ['09/07', 1],
    ])
  })

  it('interprets timezone-less backend timestamps as UTC before using the local day', () => {
    const createdAt = parseApiDateTime('2026-09-06T16:30:00.000000')
    expect(createdAt.toISOString()).toBe('2026-09-06T16:30:00.000Z')

    const localDay = `${String(createdAt.getMonth() + 1).padStart(2, '0')}/${String(createdAt.getDate()).padStart(2, '0')}`
    const localNoon = new Date(createdAt.getFullYear(), createdAt.getMonth(), createdAt.getDate(), 12)
    const trend = buildSevenDayTrend([
      { device: devices[0], fault: fault({ created_at: '2026-09-06T16:30:00.000000' }) },
    ], localNoon)

    expect(trend.find((item) => item.label === localDay)?.count).toBe(1)
  })
})
