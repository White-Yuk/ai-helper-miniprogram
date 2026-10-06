import Taro from '@tarojs/taro'

import type {
  ApiResponse,
  DocumentCreated,
  DocumentListData,
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
  QuizTaskCreated,
  QuizTaskData,
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
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: unknown
  /** 允许 data 为 null（如“无未完成闯关”是合法空态） */
  allowNull?: boolean
  /** 跳过「确保登录」与自动重登（供登录 / 健康检查等接口使用，防止递归） */
  skipAuth?: boolean
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

type EnsureLoginFn = (force?: boolean) => Promise<void>
let ensureLoginImpl: EnsureLoginFn | null = null

/**
 * 由 auth 服务注册「确保登录」实现（避免模块循环依赖）。
 * 请求层在无 token / token 失效时先完成登录，从源头避免 401。
 */
export function registerEnsureLogin(fn: EnsureLoginFn): void {
  ensureLoginImpl = fn
}

async function request<T>(options: RequestOptions): Promise<T> {
  // 需要登录态的接口：先确保登录完成（已有 token 时零开销；登录失败不阻塞，由 4003 分支兜底）
  if (!options.skipAuth && ensureLoginImpl) {
    try {
      await ensureLoginImpl()
    } catch {
      // 登录失败：继续发起请求，交由响应侧处理
    }
  }
  return requestOnce<T>(options, true)
}

async function requestOnce<T>(options: RequestOptions, allowReauthRetry: boolean): Promise<T> {
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
      // 微信小程序 wx.request 超时上限为 60s（硬性，超出被静默截断）→ 长耗时生成
      // 不依赖单次长请求（已改为「创建任务 + 轮询短查询」）；此值实际仅对 H5 端生效。
      timeout: 90000,
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
      // 登录失效：清除本地 token，强制重新登录后自动重试一次（避免页面直接报“未登录或登录已过期”）
      clearToken()
      if (allowReauthRetry && !options.skipAuth && ensureLoginImpl) {
        try {
          await ensureLoginImpl(true)
          return await requestOnce<T>(options, false)
        } catch {
          // 重登失败：走下方统一抛错
        }
      }
      reauthHandler?.()
    }
    throw new ApiError(code, body?.message ?? '请求失败，请稍后重试')
  }
  return body.data as T
}

/** 健康检查 */
export function checkHealth() {
  return request<{ status: string; app_name: string; version: string }>({
    url: '/api/v1/health',
    skipAuth: true,
  })
}

/** 生成闯关题库（同步；保留供 H5 / 调试，小程序端请使用任务接口） */
export function generateQuiz(payload: QuizGenerateRequest) {
  return request<QuizData>({ url: '/api/v1/quiz/generate', method: 'POST', data: payload })
}

/* ---------------- 异步生成任务（知识获取增强） ---------------- */

/** 创建生成任务：立即返回 task_id（异步任务 + 轮询流程的第一步） */
export function createQuizTask(payload: QuizGenerateRequest) {
  return request<QuizTaskCreated>({ url: '/api/v1/quiz/tasks', method: 'POST', data: payload })
}

/** 查询生成任务（状态 / 步骤 / 结果 / 错误） */
export function getQuizTask(taskId: string) {
  return request<QuizTaskData>({ url: `/api/v1/quiz/tasks/${taskId}` })
}

export interface WaitQuizTaskOptions {
  /** 轮询间隔（默认 2000ms） */
  intervalMs?: number
  /** 最大轮询次数（默认 150 次 ≈ 5 分钟） */
  maxAttempts?: number
  /** 每次拿到任务后的回调（实时渲染步骤；抛错会中断轮询） */
  onTick?: (task: QuizTaskData) => void
  /** 返回 true 时中断轮询（页面卸载场景） */
  isCancelled?: () => boolean
}

/**
 * 轮询任务直至终态：done 返回题库数据；failed 抛 ApiError（携带任务错误码，如 4006 知识盲区）。
 * 注意：轮询中的每次请求都是短查询（不依赖小程序的 60s 超时上限）。
 */
export async function waitQuizTask(taskId: string, options: WaitQuizTaskOptions = {}): Promise<QuizData> {
  const intervalMs = options.intervalMs ?? 2000
  const maxAttempts = options.maxAttempts ?? 150

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (options.isCancelled?.()) {
      throw new ApiError(-5, '轮询已取消')
    }
    const task = await getQuizTask(taskId)
    options.onTick?.(task)

    if (task.status === 'done') {
      if (!task.result) {
        throw new ApiError(-4, '任务数据异常，请重试一下')
      }
      return task.result
    }
    if (task.status === 'failed') {
      throw new ApiError(task.error?.code ?? -4, task.error?.message ?? '生成失败了，请重试一下')
    }

    await new Promise<void>((resolve) => {
      setTimeout(resolve, intervalMs)
    })
  }
  throw new ApiError(-3, '生成超时了，请重试一下')
}

/** 生成复盘报告 */
export function generateReport(payload: ReportGenerateRequest) {
  return request<ReportData>({ url: '/api/v1/report/generate', method: 'POST', data: payload })
}

/* ---------------- 登录相关接口 ---------------- */

/** 微信登录：Taro.login() 的 code 换取 token */
export function loginWithCode(code: string) {
  return request<LoginData>({ url: '/api/v1/auth/login', method: 'POST', data: { code }, skipAuth: true })
}

/** 开发态模拟登录（后端开启 AUTH_MOCK_ENABLED 时可用） */
export function devLogin(deviceId: string) {
  return request<LoginData>({
    url: '/api/v1/auth/dev-login',
    method: 'POST',
    data: { device_id: deviceId },
    skipAuth: true,
  })
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

/* ---------------- RAG 资料库（文档上传与检索增强） ---------------- */

/** 我的文档列表（含处理状态与步骤，供轮询） */
export function listDocuments() {
  return request<DocumentListData>({ url: '/api/v1/documents' })
}

/** 删除文档（记录 + 向量 + 原文件） */
export function deleteDocument(docId: string) {
  return request<{ doc_id: string; deleted: boolean }>({
    url: `/api/v1/documents/${docId}`,
    method: 'DELETE',
  })
}

/**
 * 上传文档（multipart）。受理即返回（后台异步处理），状态由列表轮询跟进。
 * - 微信端：传 filePath（Taro.chooseMessageFile 的临时路径）
 * - H5 端：传 file（浏览器 File 对象，走原生 fetch + FormData）
 */
export async function uploadDocument(params: {
  filePath?: string
  file?: File
  filename?: string
}): Promise<DocumentCreated> {
  if (process.env.TARO_ENV === 'h5') {
    if (!params.file) throw new ApiError(-1, '未选择文件')
    return uploadDocumentH5(params.file)
  }
  if (!params.filePath) throw new ApiError(-1, '未选择文件')
  return uploadDocumentTaro(params.filePath)
}

/** 微信端上传：Taro.uploadFile（60s 上限内，≤20MB 本地/局域网安全） */
async function uploadDocumentTaro(filePath: string): Promise<DocumentCreated> {
  const header: Record<string, string> = {}
  const token = getToken()
  if (token) {
    header.Authorization = `Bearer ${token}`
  }

  let response: Awaited<ReturnType<typeof Taro.uploadFile>>
  try {
    response = await Taro.uploadFile({
      url: `${API_BASE_URL}/api/v1/documents`,
      filePath,
      name: 'file',
      header,
      timeout: 60000,
    })
  } catch {
    throw new ApiError(-1, '文件上传失败，请检查网络后重试')
  }

  let body: ApiResponse<DocumentCreated> | null = null
  try {
    body = JSON.parse(response.data) as ApiResponse<DocumentCreated>
  } catch {
    body = null
  }
  if (!body || body.code !== 0 || !body.data) {
    throw new ApiError(body?.code ?? -1, body?.message ?? '文件上传失败，请重试')
  }
  return body.data
}

/** H5 端上传：原生 fetch + FormData（浏览器直接选择本地文件） */
async function uploadDocumentH5(file: File): Promise<DocumentCreated> {
  const form = new FormData()
  form.append('file', file, file.name)
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/documents`, {
      method: 'POST',
      headers,
      body: form,
    })
  } catch {
    throw new ApiError(-1, '文件上传失败，请检查网络后重试')
  }

  let body: ApiResponse<DocumentCreated> | null = null
  try {
    body = (await response.json()) as ApiResponse<DocumentCreated>
  } catch {
    body = null
  }
  if (!body || body.code !== 0 || !body.data) {
    throw new ApiError(body?.code ?? -1, body?.message ?? '文件上传失败，请重试')
  }
  return body.data
}
