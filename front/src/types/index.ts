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

/* ---------------- 阶段 5：学习报表 / 知识掌握详情 ---------------- */

export type StatsRange = 'week' | 'month' | 'all'

/** 按天趋势点（无答题的日期 accuracy 为 null） */
export interface TrendPoint {
  date: string
  total: number
  correct: number
  accuracy: number | null
}

/** 各领域（按闯关）掌握度 */
export interface DomainStat {
  quiz_id: string
  name: string
  total: number
  correct: number
  accuracy: number
}

/** GET /me/stats 返回数据 */
export interface StatsData {
  range: StatsRange
  overall_accuracy: number | null
  trend: TrendPoint[]
  domains: DomainStat[]
}

export type KnowledgeState = 'mastered' | 'weak' | 'unlearned'

/** 单个知识点掌握情况 */
export interface KnowledgePointStat {
  name: string
  total: number
  answered: number
  correct: number
  accuracy: number
  state: KnowledgeState
}

/** GET /knowledge-base/{quiz_id} 返回数据 */
export interface KnowledgeDetailData {
  quiz_id: string
  title: string
  accuracy: number
  total_points: number
  mastered_count: number
  weak_count: number
  unlearned_count: number
  points: KnowledgePointStat[]
}

/* ---------------- 阶段 6：错题本 ---------------- */

/** 错题本条目（含完整题目数据，可直接重做） */
export interface WrongItem {
  quiz_id: string
  question_id: string
  type: QuestionType
  stem: string
  options: QuizOption[]
  answer: string[]
  explanation: string
  knowledge_point: string
  wrong_count: number
  last_wrong_answers: string[]
}

/** GET /wrongbook 返回数据 */
export interface WrongbookData {
  total: number
  items: WrongItem[]
}

/** POST /wrongbook/redo 请求 */
export interface RedoSubmitRequest {
  quiz_id: string
  question_id: string
  selected_answers: string[]
  is_correct: boolean
  duration_ms: number
}

/** POST /wrongbook/redo 响应 */
export interface RedoSubmitData {
  remaining: number
}

/* ---------------- 阶段 7：用户资料 ---------------- */

/** PUT /me 请求（昵称 / 头像至少一项） */
export interface ProfileUpdateRequest {
  nickname?: string
  avatar?: string
}
