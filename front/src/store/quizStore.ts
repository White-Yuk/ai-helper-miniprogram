import { create } from 'zustand'

import type { AnswerRecord, QuizData } from '../types'

/** 答题经验值（答对 / 答错）；quiz 页与续答重放共用 */
export const XP_CORRECT = 20
export const XP_WRONG = 5

interface QuizState {
  /** 当前闯关的题库 */
  quiz: QuizData | null
  /** 本轮作答记录 */
  records: AnswerRecord[]
  /** 当前连对次数 */
  combo: number
  /** 最高连对 */
  maxCombo: number
  /** 本关累计 XP */
  xp: number
  /** 续答恢复时的起始题索引（新闯关恒为 0） */
  resumeIndex: number

  startQuiz: (quiz: QuizData) => void
  /** 恢复续答：注入题库 + 已答记录 + 起始题索引，并重放连击与经验值 */
  restoreQuiz: (quiz: QuizData, records: AnswerRecord[], resumeIndex: number) => void
  recordAnswer: (record: AnswerRecord, xpGain: number) => void
  reset: () => void
}

export const useQuizStore = create<QuizState>((set) => ({
  quiz: null,
  records: [],
  combo: 0,
  maxCombo: 0,
  xp: 0,
  resumeIndex: 0,

  startQuiz: (quiz) => set({ quiz, records: [], combo: 0, maxCombo: 0, xp: 0, resumeIndex: 0 }),

  restoreQuiz: (quiz, records, resumeIndex) => {
    let combo = 0
    let maxCombo = 0
    let xp = 0
    records.forEach((record) => {
      combo = record.is_correct ? combo + 1 : 0
      maxCombo = Math.max(maxCombo, combo)
      xp += record.is_correct ? XP_CORRECT : XP_WRONG
    })
    set({ quiz, records, combo, maxCombo, xp, resumeIndex })
  },

  recordAnswer: (record, xpGain) =>
    set((state) => {
      const combo = record.is_correct ? state.combo + 1 : 0
      return {
        records: [...state.records, record],
        combo,
        maxCombo: Math.max(state.maxCombo, combo),
        xp: state.xp + xpGain,
      }
    }),

  reset: () => set({ quiz: null, records: [], combo: 0, maxCombo: 0, xp: 0, resumeIndex: 0 }),
}))
