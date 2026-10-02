import Taro from '@tarojs/taro'

import type {
  ApiResponse,
  KnowledgeDetailData,
  LoginData,
  MeData,
  ProfileUpdateRequest,
  QuizData,
  QuizGenerateRequest,
  QuizProgressData,
  QuizProgressRequest,
  QuizSubmitData,
  QuizSubmitRequest,
  RedoSubmitData,
  RedoSubmitRequest,
  ReportData,
  ReportGenerateRequest,
  StatsData,
  StatsRange,
  UnfinishedQuizData,
  UserPublic,
  WrongbookData,
} from '../types'

/**
 * 后端服务地址：
 * - 微信开发者工具：填 http://127.0.0.1:8000 并勾选「不校验合法域名」
 * - 真机预览：改为电脑局域网 IP，如 http://192.168.x.x:8000
 */
export const API_BASE_URL = process.env.TARO_APP_API_BASE || 'http://127.0.0.1:8000'

export class ApiError extends Error {
  code: number

  constructor(code: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

interface RequestOptions {
  url: string
  method?: 'GET' | 'POST' | 'PUT'
  data?: unknown
  /** 允许 data 为 null（如“无未完成闯关”是合法空态） */
  allowNull?: boolean
}

/* ---------------- 登录态（token）管理 ---------------- */

const TOKEN_KEY = 'auth_token'

export function getToken(): string {
  try {
    return Taro.getStorageSync(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(token: string): void {
  Taro.setStorageSync(TOKEN_KEY, token)
}

export function clearToken(): void {
  try {
    Taro.removeStorageSync(TOKEN_KEY)
  } catch {
    // 忽略存储异常
  }
}

type ReauthHandler = () => void
let reauthHandler: ReauthHandler | null = null

/** 注册登录失效（4003）时的重新登录处理器（由 auth 服务注册，避免循环依赖）。 */
export function onUnauthorized(handler: ReauthHandler): void {
  reauthHandler = handler
}

async function request<T>(options: RequestOptions): Promise<T> {
  const header: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) {
    header.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await Taro.request({
      url: `${API_BASE_URL}${options.url}`,
      method: options.method ?? 'GET',
      data: options.data,
      header,
      timeout: 90000, // AI 生成耗时较长，放宽超时
    })
  } catch (error) {
    const errMsg = (error as { errMsg?: string } | undefined)?.errMsg || ''
    if (errMsg.toLowerCase().includes('timeout')) {
      throw new ApiError(-2, 'AI 想得太久了，请求超时，请重试一下')
    }
    throw new ApiError(-1, '网络连接失败，请检查后端服务是否已启动')
  }

  const body = response.data as ApiResponse<T>
  if (!body || body.code !== 0 || (body.data == null && !options.allowNull)) {
    const code = body?.code ?? -1
    if (code === 4003) {
      // 登录失效：清除本地 token，并触发一次静默重登（下次请求生效）
      clearToken()
      reauthHandler?.()
    }
    throw new ApiError(code, body?.message ?? '请求失败，请稍后重试')
  }
  return body.data as T
}

/** 健康检查 */
export function checkHealth() {
  return request<{ status: string; app_name: string; version: string }>({ url: '/api/v1/health' })
}

/** 生成闯关题库 */
export function generateQuiz(payload: QuizGenerateRequest) {
  return request<QuizData>({ url: '/api/v1/quiz/generate', method: 'POST', data: payload })
}

/** 生成复盘报告 */
export function generateReport(payload: ReportGenerateRequest) {
  return request<ReportData>({ url: '/api/v1/report/generate', method: 'POST', data: payload })
}

/* ---------------- 登录相关接口 ---------------- */

/** 微信登录：Taro.login() 的 code 换取 token */
export function loginWithCode(code: string) {
  return request<LoginData>({ url: '/api/v1/auth/login', method: 'POST', data: { code } })
}

/** 开发态模拟登录（后端开启 AUTH_MOCK_ENABLED 时可用） */
export function devLogin(deviceId: string) {
  return request<LoginData>({ url: '/api/v1/auth/dev-login', method: 'POST', data: { device_id: deviceId } })
}

/** 当前登录用户信息（含统计与续答） */
export function fetchMe() {
  return request<MeData>({ url: '/api/v1/me' })
}

/* ---------------- 历史答题记录 + 续答（阶段 3） ---------------- */

/** 最近未完成闯关（含完整题库与已答记录）；无进行中闯关时返回 null */
export function fetchUnfinishedQuiz() {
  return request<UnfinishedQuizData | null>({ url: '/api/v1/quiz/unfinished', allowNull: true })
}

/** 保存中途进度（幂等：全量覆盖） */
export function saveQuizProgress(quizId: string, payload: QuizProgressRequest) {
  return request<QuizProgressData>({ url: `/api/v1/quiz/${quizId}/progress`, method: 'PUT', data: payload })
}

/** 提交完整作答（服务端将 quiz 置为完成） */
export function submitQuiz(quizId: string, payload: QuizSubmitRequest) {
  return request<QuizSubmitData>({ url: `/api/v1/quiz/${quizId}/submit`, method: 'POST', data: payload })
}

/* ---------------- 学习报表 / 知识掌握详情（阶段 5） ---------------- */

/** 学习报表：正确率趋势 + 各领域掌握度 */
export function fetchStats(range: StatsRange) {
  return request<StatsData>({ url: `/api/v1/me/stats?range=${range}` })
}

/** 知识掌握详情（知识点清单：掌握 / 薄弱 / 未学） */
export function fetchKnowledgeDetail(quizId: string) {
  return request<KnowledgeDetailData>({ url: `/api/v1/knowledge-base/${quizId}` })
}

/* ---------------- 错题本（阶段 6） ---------------- */

/** 错题本：待清理错题列表 */
export function fetchWrongbook() {
  return request<WrongbookData>({ url: '/api/v1/wrongbook' })
}

/** 提交错题重做结果（答对即清理） */
export function submitRedo(payload: RedoSubmitRequest) {
  return request<RedoSubmitData>({ url: '/api/v1/wrongbook/redo', method: 'POST', data: payload })
}

/* ---------------- 用户资料（阶段 7） ---------------- */

/** 更新用户资料（昵称 / 头像） */
export function updateProfile(payload: ProfileUpdateRequest) {
  return request<UserPublic>({ url: '/api/v1/me', method: 'PUT', data: payload })
}

/** 头像文件上传：返回可访问的相对 URL（/static/avatars/xxx.png） */
export async function uploadAvatar(filePath: string): Promise<{ url: string }> {
  const header: Record<string, string> = {}
  const token = getToken()
  if (token) {
    header.Authorization = `Bearer ${token}`
  }

  let response: Awaited<ReturnType<typeof Taro.uploadFile>>
  try {
    response = await Taro.uploadFile({
      url: `${API_BASE_URL}/api/v1/me/avatar`,
      filePath,
      name: 'file',
      header,
      timeout: 60000,
    })
  } catch {
    throw new ApiError(-1, '头像上传失败，请检查网络后重试')
  }

  let body: ApiResponse<{ url: string }> | null = null
  try {
    body = JSON.parse(response.data) as ApiResponse<{ url: string }>
  } catch {
    body = null
  }
  if (!body || body.code !== 0 || !body.data) {
    throw new ApiError(body?.code ?? -1, body?.message ?? '头像上传失败，请重试')
  }
  return body.data
}

/** 把后端相对路径（/static/...）转为可访问的绝对地址 */
export function resolveAssetUrl(path: string): string {
  if (!path) return ''
  if (/^https?:\/\//.test(path)) return path
  return `${API_BASE_URL}${path}`
}
