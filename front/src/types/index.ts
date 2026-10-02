/** 与后端 API 对应的类型定义（字段与 backend/app/models 保持一致） */

export type QuestionType = 'single' | 'multiple' | 'judge' | 'fill'
export type QuizDifficulty = 'easy' | 'mixed' | 'hard'
export type QuestionDifficulty = 'easy' | 'medium' | 'hard'

export interface QuizOption {
  key: string
  text: string
}

export interface Question {
  id: string
  type: QuestionType
  stem: string
  options: QuizOption[]
  /** 单选/多选：选项键数组；判断：["对"]/["错"]；填空：每个空的标准答案 */
  answer: string[]
  explanation: string
  knowledge_point: string
  difficulty: QuestionDifficulty
}

export interface QuizGenerateRequest {
  user_input: string
  question_count: number
  difficulty: QuizDifficulty
  question_types: QuestionType[]
}

/** 题库生成接口返回的数据 */
export interface QuizData {
  quiz_id: string
  title: string
  summary: string
  questions: Question[]
}

export interface AnswerRecord {
  question_id: string
  selected_answers: string[]
  is_correct: boolean
  duration_ms: number
}

export interface ReportGenerateRequest {
  quiz_id: string
  topic: string
  questions: Question[]
  answer_records: AnswerRecord[]
}

/** 复盘报告数据 */
export interface ReportData {
  accuracy: number
  mastered_points: string[]
  weak_points: string[]
  three_line_summary: string[]
  advice: string[]
  share_quote: string
}

/** 后端统一响应结构 */
export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
}

/** 用户信息（对应后端 /auth/login 与 /me） */
export interface UserPublic {
  id: number
  nickname: string
  avatar: string
}

/** 登录接口返回数据 */
export interface LoginData {
  token: string
  expires_at: string
  is_new: boolean
  user: UserPublic
}

/** 用户学习统计（对应用户中心三宫格） */
export interface UserStats {
  quiz_count: number
  answered_count: number
  avg_accuracy: number
}

/** 最近未完成闯关摘要（“上次没打完的”卡片） */
export interface ContinueLearning {
  quiz_id: string
  title: string
  current_index: number
  total: number
}

/** GET /me 返回数据（用户信息 + 统计 + 续答） */
export interface MeData {
  id: number
  nickname: string
  avatar: string
  stats: UserStats
  continue_learning: ContinueLearning | null
}

/* ---------------- 阶段 3：历史答题记录 + 续答 ---------------- */

/** 保存中途进度请求（幂等：全量覆盖） */
export interface QuizProgressRequest {
  /** 已答题数（= 恢复时的起始题索引） */
  current_index: number
  records: AnswerRecord[]
}

/** 保存中途进度响应 */
export interface QuizProgressData {
  current_index: number
  saved_count: number
}

/** 提交完整作答请求 */
export interface QuizSubmitRequest {
  records: AnswerRecord[]
}

/** 提交完整作答响应 */
export interface QuizSubmitData {
  quiz_id: string
  status: string
  answered_count: number
}

/** 最近未完成闯关（含完整题库与已答记录，供续答恢复） */
export interface UnfinishedQuizData {
  quiz_id: string
  title: string
  summary: string
  questions: Question[]
  current_index: number
  records: AnswerRecord[]
  total: number
  updated_at: string
}
