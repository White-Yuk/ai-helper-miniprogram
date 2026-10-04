import { useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import ProgressBar from '../../components/ProgressBar'
import Badge from '../../components/Badge'
import Stamp from '../../components/Stamp'
import SpeechBubble from '../../components/SpeechBubble'
import InkButton from '../../components/InkButton'
import QuestionPanel from '../../components/QuestionPanel'
import { gradeAnswer } from '../../utils/grader'
import { getCapsuleInset } from '../../utils/navInset'
import { saveQuizProgress } from '../../services/api'
import { XP_CORRECT, XP_WRONG, useQuizStore } from '../../store/quizStore'
import type { Question } from '../../types'

import './index.scss'

export default function Quiz() {
  const quiz = useQuizStore((state) => state.quiz)
  const xp = useQuizStore((state) => state.xp)
  const combo = useQuizStore((state) => state.combo)
  const recordAnswer = useQuizStore((state) => state.recordAnswer)

  // 续答恢复：从断点题开始（新闯关 resumeIndex 恒为 0）
  const [current, setCurrent] = useState(() =>
    Math.min(useQuizStore.getState().resumeIndex, Math.max((useQuizStore.getState().quiz?.questions.length ?? 1) - 1, 0)),
  )
  const [phase, setPhase] = useState<'answering' | 'feedback'>('answering')
  const [selected, setSelected] = useState<string[]>([])
  const [fillInputs, setFillInputs] = useState<string[]>([])
  const [lastCorrect, setLastCorrect] = useState(false)

  const questionStartRef = useRef(Date.now())

  /** 异步保存中途进度（失败不阻塞答题；未登录 / 未落库时静默） */
  const persistProgress = () => {
    const state = useQuizStore.getState()
    if (!state.quiz || state.records.length === 0) return
    saveQuizProgress(state.quiz.quiz_id, {
      current_index: state.records.length,
      records: state.records,
    }).catch((error) => {
      console.warn('[quiz] 进度保存失败（不影响答题）', error)
    })
  }

  // 没有题库（例如直接进入本页）→ 回首页
  useEffect(() => {
    if (!quiz) {
      Taro.redirectTo({ url: '/pages/index/index' })
    }
  }, [quiz])

  // 切题时重置状态
  useEffect(() => {
    if (!quiz) return
    const question = quiz.questions[current]
    if (question) {
      const blankCount = question.type === 'fill' ? Math.max(question.answer.length, 1) : 0
      setFillInputs(new Array(blankCount).fill(''))
    }
    setPhase('answering')
    setSelected([])
    questionStartRef.current = Date.now()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current])

  if (!quiz) return null

  const total = quiz.questions.length
  const question: Question = quiz.questions[current]

  const submit = (answers: string[]) => {
    if (phase !== 'answering') return
    const correct = gradeAnswer(question, answers)
    const duration = Date.now() - questionStartRef.current

    recordAnswer(
      {
        question_id: question.id,
        selected_answers: answers,
        is_correct: correct,
        duration_ms: duration,
      },
      correct ? XP_CORRECT : XP_WRONG,
    )

    // 每答一题异步保存进度（阶段 3）
    persistProgress()

    setSelected(answers)
    setLastCorrect(correct)
    setPhase('feedback')
  }

  const nextQuestion = () => {
    if (current + 1 >= total) {
      Taro.redirectTo({ url: '/pages/result/index' })
      return
    }
    setCurrent(current + 1)
  }

  const handleBack = () => {
    Taro.showModal({
      title: '退出闯关？',
      content: '进度已自动保存，随时回来继续哦',
      confirmText: '退出',
      cancelText: '继续答题',
      success: (res) => {
        if (res.confirm) {
          Taro.navigateBack()
        }
      },
    })
  }

  const handleOptionClick = (key: string) => {
    if (phase !== 'answering') return
    if (question.type === 'single') {
      submit([key])
      return
    }
    // 多选：切换勾选
    setSelected((prev) => (prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]))
  }

  const handleFillInput = (index: number, value: string) => {
    setFillInputs((prev) => {
      const next = [...prev]
      next[index] = value
      return next
    })
  }

  /* ---------- 提交按钮状态 ---------- */
  const canSubmitMulti = selected.length > 0
  const canSubmitFill = fillInputs.some((value) => value.trim().length > 0)

  const feedbackTitle = lastCorrect ? '叮！答对啦！' : '差一点点！'
  const feedbackSub = lastCorrect
    ? `+${XP_CORRECT} 经验${combo >= 2 ? ` · COMBO ×${combo} 🔥` : ''}`
    : `安慰奖 +${XP_WRONG} 经验 · 错题已记录`

  return (
    <PageShell className='quiz-page'>
      {/* 顶栏（右侧动态避开微信胶囊按钮：防止 ⚡XP 徽章与主题名被遮挡） */}
      <View className='quiz-top' style={{ paddingRight: getCapsuleInset() }}>
        <BackButton onClick={handleBack} />
        <View className='quiz-top__main'>
          <View className='quiz-top__txt'>
            <Text>
              第 {current + 1} 题 / 共 {total} 题
            </Text>
            <Text className='quiz-top__topic'>{quiz.title}</Text>
          </View>
          <ProgressBar percent={Math.min(100, Math.round(((current + 1) / total) * 100))} height={18} />
        </View>
        <Badge variant='xp'>⚡{xp}</Badge>
      </View>

      {/* 答题面板（题干 + 作答区，与错题重做页共用） */}
      <QuestionPanel
        question={question}
        phase={phase}
        selected={selected}
        fillInputs={fillInputs}
        onClickOption={handleOptionClick}
        onJudge={(value) => submit([value])}
        onFillInput={handleFillInput}
      />

      {/* 反馈卡 */}
      {phase === 'feedback' && (
        <View className={`fb-card ${lastCorrect ? 'fb-card--good' : ''}`}>
          <Stamp type={lastCorrect ? 'ok' : 'no'} size={56} />
          <View className='fb-card__text'>
            <Text className='fb-card__title'>{feedbackTitle}</Text>
            <Text className='fb-card__sub'>{feedbackSub}</Text>
          </View>
        </View>
      )}

      {/* 讲解气泡 */}
      {phase === 'feedback' && (
        <View className='explain'>
          <SpeechBubble>{question.explanation}</SpeechBubble>
          <View className='kb-tag'>
            <Text>🏷️ 知识点：{question.knowledge_point}</Text>
          </View>
        </View>
      )}

      {/* 底部操作区 */}
      {phase === 'answering' && question.type === 'single' && (
        <View className='quiz-foot-tip'>
          <Text>🤔 选一个答案吧，答错也有讲解哦</Text>
        </View>
      )}
      {phase === 'answering' && question.type === 'judge' && (
        <View className='quiz-foot-tip'>
          <Text>🤔 觉得对就点「对」，觉得错就点「错」</Text>
        </View>
      )}
      {phase === 'answering' && question.type === 'multiple' && (
        <View className='quiz-foot'>
          <InkButton type='secondary' size='large' disabled={!canSubmitMulti} onClick={() => submit(selected)}>
            确认答案{selected.length > 0 ? `（已选 ${selected.length} 项）` : ''}
          </InkButton>
        </View>
      )}
      {phase === 'answering' && question.type === 'fill' && (
        <View className='quiz-foot'>
          <InkButton type='secondary' size='large' disabled={!canSubmitFill} onClick={() => submit(fillInputs)}>
            确认答案
          </InkButton>
        </View>
      )}
      {phase === 'feedback' && (
        <View className='quiz-foot'>
          <InkButton type='secondary' size='large' onClick={nextQuestion}>
            {current + 1 >= total ? '查看复盘报告 →' : lastCorrect ? '太棒了，下一题 →' : '我懂了，下一题 →'}
          </InkButton>
        </View>
      )}
    </PageShell>
  )
}
