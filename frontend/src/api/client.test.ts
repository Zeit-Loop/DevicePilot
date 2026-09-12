import { describe, expect, it, vi } from 'vitest'
import { API_BASE_URL, api } from './client'
import type { DeviceInput, DiagnosisResult, FaultInput } from '../types'

const deviceInput: DeviceInput = {
  name: 'Boiler Monitor', device_type: 'Sensor', serial_number: 'SNS-900',
  location: 'Boiler room', status: 'active',
}
const faultInput: FaultInput = {
  title: 'Pressure drift', description: 'Pressure rises outside the expected range.',
  severity: 'high', status: 'open',
}
const diagnosisResult: DiagnosisResult = {
  risk_level: 'HIGH',
  summary: 'Grinding and heat indicate a potentially unsafe mechanical fault.',
  possible_causes: ['Bearing wear'],
  recommended_checks: ['Isolate power and inspect the bearing assembly'],
  recommended_actions: ['Keep the motor offline until inspected'],
}
const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})

describe('central API client', () => {
  it('defaults to the same-origin API proxy', () => {
    expect(API_BASE_URL).toBe('/api')
  })

  it('uses the configured API base URL and exact device routes/methods', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ id: 1, ...deviceInput }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: 1, ...deviceInput }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.listDevices()
    await api.createDevice(deviceInput)
    await api.updateDevice(1, deviceInput)
    await api.deleteDevice(1)
    expect(fetchMock).toHaveBeenNthCalledWith(1, `${API_BASE_URL}/devices`, expect.any(Object))
    expect(fetchMock).toHaveBeenNthCalledWith(2, `${API_BASE_URL}/devices`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(deviceInput) }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, `${API_BASE_URL}/devices/1`,
      expect.objectContaining({ method: 'PUT', body: JSON.stringify(deviceInput) }))
    expect(fetchMock).toHaveBeenNthCalledWith(4, `${API_BASE_URL}/devices/1`,
      expect.objectContaining({ method: 'DELETE' }))
  })

  it('uses exact device fault routes and surfaces backend error details', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ id: 5, device_id: 1, ...faultInput }, 201))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Device not found' }, 404))
    vi.stubGlobal('fetch', fetchMock)
    await api.listFaults(1)
    await api.createFault(1, faultInput)
    expect(fetchMock).toHaveBeenNthCalledWith(1, `${API_BASE_URL}/devices/1/faults`, expect.any(Object))
    expect(fetchMock).toHaveBeenNthCalledWith(2, `${API_BASE_URL}/devices/1/faults`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(faultInput) }))
    await expect(api.getDevice(404)).rejects.toThrow('Device not found')
  })

  it('posts the diagnosis description to the exact device route and returns structured data', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(diagnosisResult))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.diagnoseDevice(7, { description: 'Grinding noise' })).resolves.toEqual(diagnosisResult)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/devices/7/diagnose`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ description: 'Grinding noise' }) }),
    )
  })

  it('surfaces a safe diagnosis error detail from the backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(
      jsonResponse({ detail: 'AI diagnosis is not configured' }, 503),
    ))

    await expect(api.diagnoseDevice(7, { description: 'Grinding noise' }))
      .rejects.toThrow('AI diagnosis is not configured')
  })
})

it('patches only status and deletes the exact fault, handling 204', async () => {
  const updated = { id: 5, device_id: 1, ...faultInput, status: 'resolved' }
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(updated)).mockResolvedValueOnce(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(api.updateFaultStatus(5, { status: 'resolved' })).resolves.toEqual(updated)
  await expect(api.deleteFault(5)).resolves.toBeUndefined()
  expect(fetchMock).toHaveBeenNthCalledWith(1, `${API_BASE_URL}/faults/5`, expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ status: 'resolved' }) }))
  expect(fetchMock).toHaveBeenNthCalledWith(2, `${API_BASE_URL}/faults/5`, expect.objectContaining({ method: 'DELETE' }))
})
