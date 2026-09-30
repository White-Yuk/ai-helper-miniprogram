import type { Question } from '../types'

/**
 * 填空答案归一化（模糊判分）：
 * - 去除所有空白
 * - 全角字母/数字转半角
 * - 统一小写
 */
export function normalizeFillAnswer(text: string): string {
  return text
    .trim()
    .replace(/\s+/g, '')
    .replace(/[Ａ-Ｚａ-ｚ０-９]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xfee0))
    .toLowerCase()
}

/**
 * 本地判题（与后端题型约定一致）：
 * - single / judge：单答案精确匹配
 * - multiple：必须完全一致（全对才算对）
 * - fill：每个空归一化后精确匹配
 */
export function gradeAnswer(question: Question, selected: string[]): boolean {
  if (!selected || selected.length === 0) return false

  switch (question.type) {
    case 'single':
    case 'judge':
      return selected.length === 1 && selected[0] === question.answer[0]
    case 'multiple': {
      if (selected.length !== question.answer.length) return false
      const a = [...selected].sort()
      const b = [...question.answer].sort()
      return a.every((value, index) => value === b[index])
    }
    case 'fill': {
      if (selected.length !== question.answer.length) return false
      return question.answer.every(
        (expected, index) => normalizeFillAnswer(selected[index] || '') === normalizeFillAnswer(expected),
      )
    }
    default:
      return false
  }
}

/** 计算正确率（0-100 整数） */
export function calcAccuracy(total: number, correct: number): number {
  if (total <= 0) return 0
  return Math.round((correct / total) * 100)
}

/** 星级评价：>=90% 三星 / >=70% 两星 / 通关一星 */
export function calcStars(accuracy: number, passed: boolean): number {
  if (!passed) return 0
  if (accuracy >= 90) return 3
  if (accuracy >= 70) return 2
  return 1
}
