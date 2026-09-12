import { deviceStatusLabels, parseApiDateTime } from '../localization'
import type { Device, DeviceStatus, Fault } from '../types'

export interface DashboardFault {
  device: Device
  fault: Fault
}

export interface StatusDatum {
  status: DeviceStatus
  label: string
  count: number
}

export interface TrendDatum {
  dateKey: string
  label: string
  count: number
}

const dateKey = (date: Date) => [
  date.getFullYear(),
  String(date.getMonth() + 1).padStart(2, '0'),
  String(date.getDate()).padStart(2, '0'),
].join('-')

export function sortRecentFaults(entries: DashboardFault[], limit = 5) {
  return [...entries].sort((left, right) => {
    const timeDifference = parseApiDateTime(right.fault.created_at).getTime() - parseApiDateTime(left.fault.created_at).getTime()
    if (timeDifference !== 0) return timeDifference
    if (right.fault.id !== left.fault.id) return right.fault.id - left.fault.id
    return right.device.id - left.device.id
  }).slice(0, limit)
}

export function buildSevenDayTrend(entries: DashboardFault[], now = new Date()): TrendDatum[] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today)
    date.setDate(today.getDate() - (6 - index))
    return {
      dateKey: dateKey(date),
      label: `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`,
      count: 0,
    }
  })
  const counts = new Map(days.map((day) => [day.dateKey, 0]))

  for (const { fault } of entries) {
    const createdAt = parseApiDateTime(fault.created_at)
    if (Number.isNaN(createdAt.getTime())) continue
    const key = dateKey(createdAt)
    if (counts.has(key)) counts.set(key, (counts.get(key) ?? 0) + 1)
  }

  return days.map((day) => ({ ...day, count: counts.get(day.dateKey) ?? 0 }))
}

export function buildDashboardData(devices: Device[], faults: DashboardFault[]) {
  const statuses: DeviceStatus[] = ['active', 'inactive', 'maintenance']
  return {
    summary: {
      total: devices.length,
      active: devices.filter((device) => device.status === 'active').length,
      unavailable: devices.filter((device) => device.status === 'inactive' || device.status === 'maintenance').length,
      pendingFaults: faults.filter(({ fault }) => fault.status !== 'resolved').length,
    },
    statusDistribution: statuses.map((status) => ({
      status,
      label: deviceStatusLabels[status],
      count: devices.filter((device) => device.status === status).length,
    })),
    recentFaults: sortRecentFaults(faults),
    trend: buildSevenDayTrend(faults),
  }
}
