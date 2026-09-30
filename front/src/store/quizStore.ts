import { create } from 'zustand'

import type { AnswerRecord, QuizData } from '../types'

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

  startQuiz: (quiz: QuizData) => void
  recordAnswer: (record: AnswerRecord, xpGain: number) => void
  reset: () => void
}

export const useQuizStore = create<QuizState>((set) => ({
  quiz: null,
  records: [],
  combo: 0,
  maxCombo: 0,
  xp: 0,

  startQuiz: (quiz) => set({ quiz, records: [], combo: 0, maxCombo: 0, xp: 0 }),

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

  reset: () => set({ quiz: null, records: [], combo: 0, maxCombo: 0, xp: 0 }),
}))
