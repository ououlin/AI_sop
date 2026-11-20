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

/** Toast 消息 */
export interface ToastItem {
  id: number
  text: string
  type: 'success' | 'error' | 'info'
}
