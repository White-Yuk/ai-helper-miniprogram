import { useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import ProgressBar from '../../components/ProgressBar'
import Stamp from '../../components/Stamp'
import SpeechBubble from '../../components/SpeechBubble'
import BoomSticker from '../../components/BoomSticker'
import InkButton from '../../components/InkButton'
import QuestionPanel from '../../components/QuestionPanel'
import { gradeAnswer } from '../../utils/grader'
import { fetchWrongbook, submitRedo } from '../../services/api'
import type { Question, WrongItem } from '../../types'

import './index.scss'

type Status = 'loading' | 'success' | 'error' | 'finished'

/** WrongItem -> Question（复用答题面板与判题逻辑） */
function toQuestion(item: WrongItem): Question {
  return {
    id: item.question_id,
    type: item.type,
    stem: item.stem,
    options: item.options,
    answer: item.answer,
    explanation: item.explanation,
    knowledge_point: item.knowledge_point,
    difficulty: 'easy',
  }
}

/** “上次你填/选的是…”提示文案 */
function formatWrongHint(item: WrongItem): string {
  const joined = item.last_wrong_answers.join('、')
  if (item.type === 'fill') return `⚠️ 上次你填的是「${joined}」——再试一次，这次肯定行！`
  if (item.type === 'judge') return `⚠️ 上次你选了「${joined}」——再想想，这次肯定行！`
  return `⚠️ 上次你选的是「${joined}」——再想想，这次肯定行！`
}

export default function Redo() {
  const [status, setStatus] = useState<Status>('loading')
  const [queue, setQueue] = useState<WrongItem[]>([])
  const [index, setIndex] = useState(0)
  const [phase, setPhase] = useState<'answering' | 'feedback'>('answering')
  const [selected, setSelected] = useState<string[]>([])
  const [fillInputs, setFillInputs] = useState<string[]>([])
  const [lastCorrect, setLastCorrect] = useState(false)
  const [clearedCount, setClearedCount] = useState(0)
  const [remaining, setRemaining] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')

  const startRef = useRef(Date.now())
  const startedRef = useRef(false)

  const singleQuestionId = Taro.getCurrentInstance().router?.params?.question_id || ''

  const load = async () => {
    setStatus('loading')
    try {
      const data = await fetchWrongbook()
      let items = data.items
      if (singleQuestionId) {
        items = items.filter((item) => item.question_id === singleQuestionId)
        if (items.length === 0) {
          Taro.showToast({ title: '这道题已经被你清理啦 🎉', icon: 'none' })
          setTimeout(() => Taro.navigateBack(), 1200)
          return
        }
      }
      if (items.length === 0) {
        Taro.showToast({ title: '暂时没有需要清理的错题', icon: 'none' })
        setTimeout(() => Taro.navigateBack(), 1200)
        return
      }
      setRemaining(data.total)
      setQueue(items)
      setIndex(0)
      setStatus('success')
    } catch (error) {
      setErrorMsg((error as { message?: string })?.message || '加载失败，请稍后重试')
      setStatus('error')
    }
  }

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 切题时重置作答状态
  useEffect(() => {
    if (status !== 'success') return
    const item = queue[index]
    if (!item) return
    const blankCount = item.type === 'fill' ? Math.max(item.answer.length, 1) : 0
    setFillInputs(new Array(blankCount).fill(''))
    setSelected([])
    setPhase('answering')
    startRef.current = Date.now()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, status])

  const item = queue[index]
  const question = item ? toQuestion(item) : null

  const submit = (answers: string[]) => {
    if (!item || !question || phase !== 'answering') return
    const correct = gradeAnswer(question, answers)
    const duration = Date.now() - startRef.current

    // 提交重做结果（失败不阻塞，下次可再练）
    submitRedo({
      quiz_id: item.quiz_id,
      question_id: item.question_id,
      selected_answers: answers,
      is_correct: correct,
      duration_ms: duration,
    })
      .then((data) => setRemaining(data.remaining))
      .catch((error) => console.warn('[redo] 重做结果提交失败（不影响本轮）', error))

    if (correct) setClearedCount((count) => count + 1)
    setSelected(answers)
    setLastCorrect(correct)
    setPhase('feedback')
  }

  const next = () => {
    if (index + 1 >= queue.length) {
      setStatus('finished')
      return
    }
    setIndex(index + 1)
  }

  const handleBack = () => {
    Taro.showModal({
      title: '退出清理？',
      content: '已清理的结果会保留，随时回来继续哦',
      confirmText: '退出',
      cancelText: '继续清理',
      success: (res) => {
        if (res.confirm) {
          Taro.navigateBack()
        }
      },
    })
  }

  const handleOptionClick = (key: string) => {
    if (!question || phase !== 'answering') return
    if (question.type === 'single') {
      submit([key])
      return
    }
    setSelected((prev) => (prev.includes(key) ? prev.filter((one) => one !== key) : [...prev, key]))
  }

  const handleFillInput = (fillIndex: number, value: string) => {
    setFillInputs((prev) => {
      const next = [...prev]
      next[fillIndex] = value
      return next
    })
  }

  const canSubmitMulti = selected.length > 0
  const canSubmitFill = fillInputs.some((value) => value.trim().length > 0)

  const wrongHint =
    item && phase === 'answering' && item.last_wrong_answers.length > 0 ? formatWrongHint(item) : ''

  return (
    <PageShell className='redo-page'>
      <View className='redo-head'>
        <BackButton onClick={handleBack} />
        <View className='redo-head__main'>
          <View className='redo-tag'>
            <Text>♻️ 错题重做 · 第 {Math.min(index + 1, queue.length || 1)} / {queue.length || 1} 道</Text>
          </View>
        </View>
      </View>

      {status === 'loading' && (
        <View className='redo-status'>
          <Text className='redo-status__text'>正在准备错题… 📝</Text>
        </View>
      )}

      {status === 'error' && (
        <View className='redo-status'>
          <Text className='redo-status__text'>{errorMsg}</Text>
          <InkButton type='primary' size='large' onClick={load}>
            🔄 重新加载
          </InkButton>
        </View>
      )}

      {status === 'success' && question && (
        <View className='redo-body'>
          {/* 进度 */}
          <View className='progress-chip'>
            <Text>清理进度</Text>
            <Text>
              {index + 1} / {queue.length}
            </Text>
          </View>
          <ProgressBar percent={Math.round(((index + 1) / queue.length) * 100)} color='red' height={16} />

          {/* 题面与作答区 */}
          <View className='redo-q'>
            <QuestionPanel
              question={question}
              phase={phase}
              selected={selected}
              fillInputs={fillInputs}
              onClickOption={handleOptionClick}
              onJudge={(value) => submit([value])}
              onFillInput={handleFillInput}
              showDifficulty={false}
            />
          </View>

          {/* 上次错误提示（作答中显示） */}
          {wrongHint !== '' && (
            <View className='redo-hint'>
              <Text>{wrongHint}</Text>
            </View>
          )}

          {/* 反馈卡 */}
          {phase === 'feedback' && (
            <View className={`fb-card ${lastCorrect ? 'fb-card--good' : ''}`}>
              <Stamp type={lastCorrect ? 'ok' : 'no'} size={56} />
              <View className='fb-card__text'>
                <Text className='fb-card__title'>{lastCorrect ? '叮！清理成功！' : '还差一点点！'}</Text>
                <Text className='fb-card__sub'>
                  {lastCorrect ? '这道题已移出错题本 🎉' : '别急，它还会留在错题本等你再来'}
                </Text>
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
          {phase === 'answering' && (question.type === 'single' || question.type === 'judge') && (
            <View className='redo-foot-tip'>
              <Text>🤔 想好了就选，答对就把它请出错题本！</Text>
            </View>
          )}
          {phase === 'answering' && question.type === 'multiple' && (
            <View className='redo-foot'>
              <InkButton type='secondary' size='large' disabled={!canSubmitMulti} onClick={() => submit(selected)}>
                确认答案{selected.length > 0 ? `（已选 ${selected.length} 项）` : ''}
              </InkButton>
            </View>
          )}
          {phase === 'answering' && question.type === 'fill' && (
            <View className='redo-foot'>
              <InkButton type='secondary' size='large' disabled={!canSubmitFill} onClick={() => submit(fillInputs)}>
                确认答案
              </InkButton>
            </View>
          )}
          {phase === 'feedback' && (
            <View className='redo-foot'>
              <InkButton type='secondary' size='large' onClick={next}>
                {index + 1 >= queue.length ? '完成清理 →' : lastCorrect ? '下一题 →' : '下一题，继续加油 →'}
              </InkButton>
            </View>
          )}
        </View>
      )}

      {status === 'finished' && (
        <View className='redo-finish'>
          <BoomSticker size={210}>
            <Text className='redo-finish__boom'>清理完成！</Text>
          </BoomSticker>
          <Text className='redo-finish__copy'>
            本轮清理成功 {clearedCount} 道
            {clearedCount === queue.length ? ' · 全清！太强了 🎉' : ''}
          </Text>
          <Text className='redo-finish__sub'>
            {remaining > 0 ? `错题本还剩 ${remaining} 道待清理` : '错题本被你清空啦！🎉'}
          </Text>
          <View className='redo-finish__actions'>
            <InkButton type='primary' size='large' onClick={() => Taro.navigateBack()}>
              返回错题本 →
            </InkButton>
          </View>
        </View>
      )}
    </PageShell>
  )
}
