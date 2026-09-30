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
