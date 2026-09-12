import type { DeviceStatus, FaultSeverity, FaultStatus, RiskLevel } from './types'

export const deviceStatusLabels: Record<DeviceStatus, string> = {
  active: '运行中',
  inactive: '已停用',
  maintenance: '维护中',
}

export const faultSeverityLabels: Record<FaultSeverity, string> = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '严重',
}

export const faultStatusLabels: Record<FaultStatus, string> = {
  open: '待处理',
  investigating: '调查中',
  resolved: '已解决',
}

export const riskLevelLabels: Record<RiskLevel, string> = {
  LOW: '低',
  MEDIUM: '中',
  HIGH: '高',
  CRITICAL: '严重',
}

const badgeLabels: Record<string, string> = {
  ...deviceStatusLabels,
  ...faultSeverityLabels,
  ...faultStatusLabels,
}

const knownErrors: Record<string, string> = {
  'Device not found': '未找到该设备。',
  'Serial number already exists': '序列号已存在，请更换后重试',
  'AI diagnosis is not configured': 'AI 诊断尚未配置，请联系管理员。',
  'AI provider authentication failed': 'AI 服务认证失败，请联系管理员。',
  'AI diagnosis capacity is temporarily unavailable': 'AI 诊断服务当前繁忙，请稍后重试。',
  'AI provider returned an invalid response': 'AI 服务返回了无效结果，请重试。',
  'Configured AI provider is not compatible with structured diagnosis':
    '当前 AI 模型无法返回兼容的结构化诊断，请联系管理员。',
  'AI diagnosis is temporarily unavailable': 'AI 诊断服务暂时不可用，请稍后重试。',
  'AI diagnosis rate limit exceeded': 'AI 诊断请求过于频繁，请稍后重试。',
  'Failed to fetch': '无法连接后端服务，请确认服务已启动后重试。',
}

export const badgeLabel = (value: string) => badgeLabels[value] ?? value

export const localizedErrorMessage = (error: unknown) => {
  if (!(error instanceof Error)) return '操作失败，请稍后重试。'
  return knownErrors[error.message] ?? '操作失败，请稍后重试。'
}

export const parseApiDateTime = (value: string) => {
  const hasTimeZone = /(?:z|[+-]\d{2}:\d{2})$/i.test(value)
  return new Date(hasTimeZone ? value : `${value}Z`)
}

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

export const formatDate = (value: string) => dateFormatter.format(parseApiDateTime(value))
export const formatDateTime = (value: string) => dateTimeFormatter.format(parseApiDateTime(value))
