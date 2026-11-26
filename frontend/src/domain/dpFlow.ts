/**
 * 差分隐私用途申请 / 配置选择回执 / 差分执行的统一前端领域层。
 *
 * 选择面板（隐私预算页）与差分查询提交入口（差分查询页）都从这里取数并调用
 * 同一套服务端校验（validate_usage_and_cost），避免两处各写一份用途/费用规则。
 */
import { request } from '@/api/client'

export type DpApplication = {
  id?: number
  application_id?: number
  application_no: string
  申请编号?: string
  dataset?: string
  field?: string
  purpose?: string
  allowance?: number
  额度Epsilon?: string
  status?: string
  dp_status?: string
  [key: string]: unknown
}

export type DpCandidate = {
  id: number
  config_id?: number
  配置编号?: string
  code?: string
  噪声机制?: string
  Epsilon值?: string
  cost: number
  费用?: number
  关联字段?: string
  field?: string
  配置版本?: string
  version?: string
  status?: string
  active?: boolean
  field_match: boolean
  cost_fit: boolean
  eligible: boolean
  selectable?: boolean
  reasons: string[]
  原因?: string
}

export type DpReceipt = {
  receipt_no: string
  回执编号?: string
  application_no: string
  申请编号?: string
  config_id: number
  配置ID?: number
  config_no: string
  配置编号?: string
  config_version: string
  配置版本?: string
  获准版本?: string
  field: string
  申请字段?: string
  cost: number
  费用Epsilon?: string
  dataset: string
  status?: string
  [key: string]: unknown
}

export type DpBudget = {
  id?: number
  code?: string
  预算编号?: string
  total?: number
  consumed?: number
  remaining?: number
  reserved?: number
  预占Epsilon?: string | number
  总预算Epsilon?: string
  已消耗Epsilon?: string
  剩余Epsilon?: string
  status?: string
  消耗记录?: string
}

export type DpExecution = {
  query_no?: string
  查询编号?: string
  receipt_no?: string
  application_no?: string
  申请编号?: string
  配置编号?: string
  获准版本?: string
  approved_version?: string
  消耗Epsilon?: string
  remaining?: number
  预算剩余Epsilon?: string | number
  执行状态?: string
  execution_status?: string
  deactivated_at_execution?: boolean
  执行时配置状态?: string
  executed_at?: string
  [key: string]: unknown
}

export type DpState = {
  application: DpApplication | null
  applications?: DpApplication[]
  budget: DpBudget | null
  candidates: DpCandidate[]
  executable_candidates?: DpCandidate[]
  receipt: DpReceipt | null
  execution: DpExecution | null
}

export type DpResult = {
  ok: boolean
  message: string
  reason?: string
  state?: DpState
  validation?: { message?: string; [key: string]: unknown }
  receipt?: DpReceipt
  配置回执?: DpReceipt
  execution?: DpExecution
  budget?: DpBudget
  idempotent?: boolean
  released?: number
  退回Epsilon?: string
  [key: string]: unknown
}

async function postJson<T = DpResult>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  })
  const data = (await response.json().catch(() => ({}))) as T
  if (!response.ok) {
    const detail = (data as { message?: string; detail?: string })?.message
      || (data as { detail?: string })?.detail
      || `接口返回 ${response.status}`
    throw new Error(detail)
  }
  return data
}

export function fetchDpState(application = ''): Promise<DpState> {
  const query = application ? `?application=${encodeURIComponent(application)}` : ''
  return request(`/api/dp/state${query}`).then(async (response) => {
    if (!response.ok) throw new Error('差分流程状态读取失败')
    return (await response.json()) as DpState
  })
}

/** 只校验/评估候选，不产生回执。 */
export function evaluateSelection(body: Record<string, unknown>): Promise<DpResult> {
  return postJson('/api/dp/evaluate', body)
}

/** 校验用途与费用并锁定可用配置，生成回执、预占额度。 */
export function confirmConfig(body: Record<string, unknown>): Promise<DpResult> {
  return postJson('/api/dp/confirm', body)
}

/** 差分查询提交：服务端再次执行同一份校验，并按回执核对实际参数。 */
export function executeDifferential(body: Record<string, unknown>): Promise<DpResult> {
  return postJson('/api/differential_sql/submit', body)
}

export function cancelApplication(body: Record<string, unknown>): Promise<DpResult> {
  return postJson('/api/dp/cancel', body)
}

/** 纯前端即时提示用：与服务端同口径的字段/费用判断（权威结论仍以服务端为准）。 */
export function localCandidateReason(
  candidate: Pick<DpCandidate, 'field_match' | 'cost_fit' | 'active' | 'reasons'>,
): string {
  if (!candidate.active) return candidate.reasons?.[0] ?? '配置未生效或已停用'
  if (!candidate.field_match) return candidate.reasons?.find((r) => r.includes('字段不符')) ?? '关联字段与申请字段不符'
  if (!candidate.cost_fit) return candidate.reasons?.find((r) => r.includes('超出')) ?? '费用超出申请额度'
  return '字段与费用均匹配，可确认'
}
