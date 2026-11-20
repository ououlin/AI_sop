// 与后端 models.py 对应的类型定义

export type GestureType = 'open' | 'fist' | 'pinch' | 'point' | 'unknown'
export type HandType = 'Left' | 'Right'
export type StepStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'skipped'
  | 'error'
  | 'timeout'
  | 'unauthorized_skip'
export type ConnectionState = 'connecting' | 'connected' | 'disconnected'

export interface Landmark {
  x: number
  y: number
  z: number
}

export interface HandResult {
  handedness: HandType
  gesture: GestureType
  landmarks: Landmark[]
  center_x: number
  center_y: number
  current_zone: string
}

export interface StepRuntimeState {
  step_id: number
  name: string
  status: StepStatus
  matched_duration: number
  hold_duration_sec: number
  timeout_sec: number
  completed_at: string | null
  started_at: string | null
  description: string
}

export interface StatusMessage {
  type: string
  sop_name: string
  source: string | null
  paused: boolean
  all_done: boolean
  current_step_index: number
  steps: StepRuntimeState[]
  hands: HandResult[]
  objects: unknown[]
  alarms: unknown[]
  fps: number
  timestamp: string
}

export interface SopStatus {
  loaded: boolean
  sop_name?: string
  source?: string | null
  paused?: boolean
  current_step_index?: number
  all_done?: boolean
  steps?: StepRuntimeState[]
}

/** SOP 文件列表项 */
export interface SopFileEntry {
  key: string
  name: string
  source: 'file' | 'database'
  version?: string
  loaded?: boolean
}

/** 租户（平台管理） */
export interface TenantInfo {
  id: number
  code: string
  name: string
  status: 'active' | 'suspended' | string
  plan_code: string
  created_at: string | null
  user_count: number | null
}

/** 套餐目录 */
export interface PlanInfo {
  code: string
  name: string
  price_month: number | null
  max_stations: number | null
  retention_days: number | null
  features: string[]
}

/** 租户订阅与配额 */
export interface SubscriptionInfo {
  tenant_id: number
  plan_code: string
  plan_name: string
  price_month: number | null
  max_stations: number | null
  retention_days: number | null
  features: string[]
  status: string
  started_at: string | null
  expires_at: string | null
  expired: boolean
}

/** 工序模板（市场） */
export interface MarketTemplate {
  template_id: string
  name: string
  industry: string
  difficulty: string
  summary: string
  recommended_objects: string[]
  step_count: number
  sop_name: string
}

export interface MarketTemplateStep {
  step_id: number
  name: string
  target_zone: string
  required_gesture: string
  required_objects: Array<{ class_name: string; min_count: number; target_zone: string | null }>
  hold_duration_sec: number
  timeout_sec: number
  description: string
}

export interface MarketTemplateDetail extends MarketTemplate {
  steps: MarketTemplateStep[]
}

/** 检测模型目录项 */
export interface MarketModel {
  model_id: string
  name: string
  task: string
  source: string
  license: string
  size_mb: number
  bundled: boolean
  note: string
}

/** Toast 消息 */
export interface ToastItem {
  id: number
  text: string
  type: 'success' | 'error' | 'info'
}
