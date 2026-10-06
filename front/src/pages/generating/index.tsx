import { useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import Mascot from '../../components/Mascot'
import SpeechBubble from '../../components/SpeechBubble'
import ProgressBar from '../../components/ProgressBar'
import InkButton from '../../components/InkButton'
import { ApiError, createQuizTask, waitQuizTask } from '../../services/api'
import { useQuizStore } from '../../store/quizStore'
import type { QuizData, QuizGenerateRequest, TaskStep } from '../../types'

import './index.scss'

/**
 * 生成页（异步任务 + 轮询）：
 * 创建任务 → 每 2s 轮询（实时步骤）→ done 展示「知识溯源」卡片进入闯关 /
 * failed 按错误码展示（4006 知识盲区专用引导）。
 * 背景：小程序 wx.request 超时上限 60s，长耗时生成必须任务化。
 */

type Stage = 'loading' | 'trace' | 'error'

/** 打开页面时的占位步骤（真实步骤随后端轮询到达） */
const PLACEHOLDER_STEP: TaskStep = {
  key: 'stage:prepare',
  label: '正在创建生成任务…',
  detail: '',
  state: 'doing',
  ts: '',
}

export default function Generating() {
  const [stage, setStage] = useState<Stage>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [errorCode, setErrorCode] = useState('')
  const [steps, setSteps] = useState<TaskStep[]>([PLACEHOLDER_STEP])
  const [quizData, setQuizData] = useState<QuizData | null>(null)
  const startedRef = useRef(false)
  const aliveRef = useRef(true)

  const enterQuiz = (data: QuizData) => {
    useQuizStore.getState().startQuiz(data)
    Taro.redirectTo({ url: '/pages/quiz/index' })
  }

  const run = async () => {
    setStage('loading')
    setSteps([PLACEHOLDER_STEP])
    setQuizData(null)

    const request = Taro.getStorageSync('pending_quiz_request') as QuizGenerateRequest | ''
    if (!request) {
      Taro.redirectTo({ url: '/pages/index/index' })
      return
    }

    try {
      const created = await createQuizTask(request)
      const data = await waitQuizTask(created.task_id, {
        intervalMs: 2000,
        maxAttempts: 150,
        onTick: (task) => {
          if (aliveRef.current && task.steps.length > 0) {
            setSteps(task.steps)
          }
        },
        isCancelled: () => !aliveRef.current,
      })
      if (!aliveRef.current) return
      setQuizData(data)
      if (data.agent_trace) {
        setStage('trace') // 先展示知识溯源卡片，用户确认后进入闯关
      } else {
        enterQuiz(data)
      }
    } catch (error) {
      if (!aliveRef.current) return
      if (error instanceof ApiError) {
        setErrorMsg(error.message)
        setErrorCode(error.code >= 0 ? String(error.code) : [-2, -3].includes(error.code) ? 'TIMEOUT' : 'NETWORK')
      } else {
        setErrorMsg('生成失败了，请稍后重试')
        setErrorCode('UNKNOWN')
      }
      setStage('error')
    }
  }

  useEffect(() => {
    aliveRef.current = true
    if (!startedRef.current) {
      startedRef.current = true
      run()
    }
    return () => {
      aliveRef.current = false // 页面卸载：中断轮询
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const changeTopic = () => {
    Taro.redirectTo({ url: '/pages/index/index' })
  }

  const isBlindSpot = errorCode === '4006'
  const doneCount = steps.filter((step) => step.state === 'done').length
  const percent =
    stage === 'trace' ? 100 : Math.min(95, Math.max(15, Math.round((doneCount / (steps.length + 1)) * 100)))

  return (
    <PageShell className='generating-page'>
      {stage === 'loading' ? (
        <View className='loading-stage'>
          <View className='detective'>
            <Mascot size={150} />
            <Text className='detective__mag'>🔍</Text>
          </View>

          <SpeechBubble className='loading-stage__bubble'>侦探模式 ON！{'\n'}正在替你翻遍全网找线索…</SpeechBubble>

          <View className='steps'>
            {steps.map((step) => (
              <View key={step.key} className={`step ${step.state === 'doing' ? 'step--doing' : ''}`}>
                <View className='step__icon'>{step.state === 'done' ? '✓' : '⟳'}</View>
                <View className='step__body'>
                  <Text className='step__label'>{step.label}</Text>
                  {step.detail ? <Text className='step__detail'>{step.detail}</Text> : null}
                </View>
              </View>
            ))}
          </View>

          <ProgressBar percent={percent} height={20} className='loading-stage__progress' />
          <Text className='loading-stage__foot'>别急，比等一碗泡面还快 🍜</Text>
        </View>
      ) : null}

      {stage === 'trace' && quizData ? (
        <View className='trace-stage'>
          <Mascot size={130} />
          <SpeechBubble className='trace-stage__bubble'>线索整理完毕！{'\n'}题目都基于这些资料出好了 📚</SpeechBubble>

          <View className='trace-card'>
            <Text className='trace-card__title'>🕵️ 知识溯源（本次出题依据）</Text>
            {quizData.agent_trace ? (
              <View className='trace-card__stats'>
                <Text className='trace-card__stat'>联网检索 {quizData.agent_trace.search_count} 次</Text>
                <Text className='trace-card__stat'>深读 / 提取 {quizData.agent_trace.extract_count} 次</Text>
                {quizData.agent_trace.library_search_count ? (
                  <Text className='trace-card__stat'>资料库检索 {quizData.agent_trace.library_search_count} 次</Text>
                ) : null}
                <Text className='trace-card__stat'>资料 {quizData.agent_trace.doc_count} 条</Text>
              </View>
            ) : null}
            {quizData.agent_trace && quizData.agent_trace.queries.length > 0 ? (
              <View className='trace-card__queries'>
                {quizData.agent_trace.queries.map((query) => (
                  <Text key={query} className='trace-card__query'>
                    {query}
                  </Text>
                ))}
              </View>
            ) : null}
            {quizData.sources && quizData.sources.length > 0 ? (
              <View className='trace-card__sources'>
                {quizData.sources.slice(0, 3).map((source, index) => (
                  <Text key={`${source.type ?? 'web'}-${source.title}-${index}`} className='trace-card__source'>
                    {source.type === 'library' ? '📄 ' : '🔗 '}
                    {source.title}
                  </Text>
                ))}
              </View>
            ) : null}
          </View>

          <InkButton type='primary' size='large' onClick={() => enterQuiz(quizData)}>
            🚀 开始闯关
          </InkButton>
        </View>
      ) : null}

      {stage === 'error' ? (
        <View className='error-stage'>
          <Mascot variant='dizzy' size={150} />
          <Text className='error-stage__title'>{isBlindSpot ? '这个主题难住我了…' : 'AI 卡壳了…'}</Text>
          <Text className='error-stage__desc'>
            {isBlindSpot
              ? `${errorMsg || '这一题超出了我的知识范围，为避免出错先不硬编题目。'}\n可以补充一段介绍、粘贴相关链接，或换个主题再看看 💡`
              : `${errorMsg || '题目生成失败，可能是网络打了个盹 💤'}\n别慌，重试一般就好`}
          </Text>

          <View className='error-stage__actions'>
            {isBlindSpot ? (
              <>
                <InkButton type='primary' size='large' onClick={changeTopic}>
                  ✏️ 补充资料 / 换个主题
                </InkButton>
                <InkButton type='secondary' size='large' className='error-stage__gap' onClick={run}>
                  🔁 再试一次
                </InkButton>
              </>
            ) : (
              <>
                <InkButton type='primary' size='large' onClick={run}>
                  🔄 重新生成
                </InkButton>
                <InkButton type='secondary' size='large' className='error-stage__gap' onClick={changeTopic}>
                  换个主题试试
                </InkButton>
              </>
            )}
          </View>

          <Text className='error-stage__code'>错误码：{errorCode}</Text>
        </View>
      ) : null}
    </PageShell>
  )
}
