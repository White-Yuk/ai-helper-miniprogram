import Taro from '@tarojs/taro'

import type {
  ApiResponse,
  QuizData,
  QuizGenerateRequest,
  ReportData,
  ReportGenerateRequest,
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
  method?: 'GET' | 'POST'
  data?: unknown
}

async function request<T>(options: RequestOptions): Promise<T> {
  let response
  try {
    response = await Taro.request({
      url: `${API_BASE_URL}${options.url}`,
      method: options.method ?? 'GET',
      data: options.data,
      header: { 'Content-Type': 'application/json' },
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
  if (!body || body.code !== 0 || body.data == null) {
    throw new ApiError(body?.code ?? -1, body?.message ?? '请求失败，请稍后重试')
  }
  return body.data
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
