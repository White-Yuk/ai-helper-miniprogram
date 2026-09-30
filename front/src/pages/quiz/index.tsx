import { useEffect, useRef, useState } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import ProgressBar from '../../components/ProgressBar'
import Badge from '../../components/Badge'
import Stamp from '../../components/Stamp'
import SpeechBubble from '../../components/SpeechBubble'
import BoomSticker from '../../components/BoomSticker'
import InkButton from '../../components/InkButton'
import { gradeAnswer } from '../../utils/grader'
import { useQuizStore } from '../../store/quizStore'
import type { Question } from '../../types'

import './index.scss'

const XP_CORRECT = 20
const XP_WRONG = 5

/** 下划线占位:用于填空题干的渲染 */
function splitByBlank(stem: string): string[] {
  return stem.split('____')
}

export default function Quiz() {
  const quiz = useQuizStore((state) => state.quiz)
  const xp = useQuizStore((state) => state.xp)
  const combo = useQuizStore((state) => state.combo)
  const recordAnswer = useQuizStore((state) => state.recordAnswer)

  const [current, setCurrent] = useState(0)
  const [phase, setPhase] = useState<'answering' | 'feedback'>('answering')
  const [selected, setSelected] = useState<string[]>([])
  const [fillInputs, setFillInputs] = useState<string[]>([])
  const [lastCorrect, setLastCorrect] = useState(false)
  const [showCombo, setShowCombo] = useState(false)

  const questionStartRef = useRef(Date.now())
  const combosShownRef = useRef<Set<number>>(new Set())

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

    setSelected(answers)
    setLastCorrect(correct)
    setPhase('feedback')

    const nextCombo = correct ? combo + 1 : 0
    if (correct && nextCombo >= 3 && nextCombo % 3 === 0 && !combosShownRef.current.has(nextCombo)) {
      combosShownRef.current.add(nextCombo)
      setShowCombo(true)
    }
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
      content: '当前进度不会保存哦',
      confirmText: '退出',
      cancelText: '继续答题',
      success: (res) => {
        if (res.confirm) {
          Taro.navigateBack()
        }
      },
    })
  }

  const isSelected = (key: string) => selected.includes(key)

  /* ---------- 选项状态样式 ---------- */
  const optionClass = (key: string) => {
    if (phase === 'answering') {
      return isSelected(key) ? 'opt opt--selected' : 'opt'
    }
    // feedback 阶段
    if (question.type === 'multiple') {
      const inAnswer = question.answer.includes(key)
      if (inAnswer) return 'opt opt--correct'
      if (isSelected(key)) return 'opt opt--wrong'
      return 'opt'
    }
    // 单选
    const inAnswer = question.answer.includes(key)
    if (inAnswer) return 'opt opt--correct'
    if (isSelected(key)) return 'opt opt--wrong'
    return 'opt'
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

  const judgeClass = (value: '对' | '错') => {
    if (phase === 'answering') return ''
    if (question.answer[0] === value) return 'judge-btn--correct'
    if (isSelected(value)) return 'judge-btn--wrong'
    return 'judge-btn--dim'
  }

  /* ---------- 题干渲染 ---------- */
  const renderStem = () => {
    if (question.type !== 'fill') {
      return <Text>{question.stem}</Text>
    }
    const parts = splitByBlank(question.stem)
    return (
      <Text>
        {parts.map((part, index) => (
          <Text key={`${part}-${index}`}>
            {part}
            {index < parts.length - 1 && (
              <Text className={phase === 'feedback' ? 'q-blank q-blank--done' : 'q-blank'}>
                {phase === 'feedback' ? question.answer[index] || '' : '     '}
              </Text>
            )}
          </Text>
        ))}
      </Text>
    )
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
      {/* 顶栏 */}
      <View className='quiz-top'>
        <BackButton onClick={handleBack} />
        <View className='quiz-top__main'>
          <View className='quiz-top__txt'>
            <Text>
              第 {current + 1} 关 / 共 {total} 关
            </Text>
            <Text className='quiz-top__topic'>{quiz.title}</Text>
          </View>
          <ProgressBar percent={Math.min(100, Math.round(((current + 1) / total) * 100))} height={18} />
        </View>
        <Badge variant='xp'>⚡{xp}</Badge>
      </View>

      {/* 题干卡 */}
      <View className='q-card'>
        <View className='q-card__flags'>
          <Text className={`q-tag q-tag--${question.type}`}>
            {question.type === 'single' && '单选'}
            {question.type === 'multiple' && '多选'}
            {question.type === 'judge' && '判断'}
            {question.type === 'fill' && '填空'}
          </Text>
          <Text className='q-tag q-tag--level'>
            难度 ·
            {question.difficulty === 'easy' ? '易' : question.difficulty === 'medium' ? '中' : '难'}
          </Text>
        </View>
        <View className='q-card__stem'>{renderStem()}</View>
      </View>

      {/* 答题区：单选/多选 */}
      {(question.type === 'single' || question.type === 'multiple') && (
        <View className='opt-list'>
          {question.options.map((option) => (
            <View key={option.key} className={optionClass(option.key)} hoverClass='none' onClick={() => handleOptionClick(option.key)}>
              <View className={`opt__key ${question.type === 'multiple' ? 'opt__key--sq' : ''}`}>
                <Text>{question.type === 'multiple' && isSelected(option.key) ? '✓' : option.key}</Text>
              </View>
              <Text className='opt__text'>{option.text}</Text>
              {phase === 'feedback' && question.answer.includes(option.key) && <Text className='opt__flag'>✅</Text>}
              {phase === 'feedback' && question.type !== 'multiple' && isSelected(option.key) && !question.answer.includes(option.key) && (
                <Text className='opt__flag'>❌</Text>
              )}
            </View>
          ))}
        </View>
      )}

      {/* 答题区：判断 */}
      {question.type === 'judge' && (
        <View className='judge-row'>
          <View className={`judge-btn ${judgeClass('对')}`} onClick={() => phase === 'answering' && submit(['对'])}>
            <Text className='judge-btn__sym'>✓</Text>
            <Text className='judge-btn__label'>对</Text>
          </View>
          <View className={`judge-btn ${judgeClass('错')}`} onClick={() => phase === 'answering' && submit(['错'])}>
            <Text className='judge-btn__sym'>✗</Text>
            <Text className='judge-btn__label'>错</Text>
          </View>
        </View>
      )}

      {/* 答题区：填空 */}
      {question.type === 'fill' && (
        <View className='fill-card'>
          <View className='fill-card__label'>
            <Text>✍️ {phase === 'feedback' ? '你的答案' : '写下你的答案'}</Text>
          </View>
          {fillInputs.map((value, index) => (
            <View key={index} className='fill-card__row'>
              {fillInputs.length > 1 && <Text className='fill-card__index'>第 {index + 1} 空</Text>}
              <Input
                className='fill-card__input'
                value={value}
                disabled={phase === 'feedback'}
                placeholder='填写答案…'
                placeholderClass='fill-card__placeholder'
                onInput={(event) => {
                  const next = [...fillInputs]
                  next[index] = event.detail.value
                  setFillInputs(next)
                }}
              />
            </View>
          ))}
        </View>
      )}

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

      {/* COMBO 弹层 */}
      {showCombo && (
        <View className='combo-mask'>
          <View className='combo-panel'>
            <BoomSticker size={220} color='yellow'>
              <Text className='combo-panel__title'>
                COMBO{'\n'}×{combo}！
              </Text>
            </BoomSticker>
            <View className='combo-panel__stickers'>
              <View className='combo-panel__chip'>
                <Text>⚡ 经验 +{XP_CORRECT}</Text>
              </View>
              <View className='combo-panel__chip combo-panel__chip--alt'>
                <Text>🪙 金币 +20</Text>
              </View>
            </View>
            <InkButton type='primary' className='combo-panel__btn' onClick={() => setShowCombo(false)}>
              手感来了，继续冲！→
            </InkButton>
            <Text className='combo-panel__hint'>连续答对 {combo} 题 · 别断啊朋友 🔥</Text>
          </View>
        </View>
      )}
    </PageShell>
  )
}
