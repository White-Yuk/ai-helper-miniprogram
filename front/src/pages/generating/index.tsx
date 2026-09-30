import { useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import Mascot from '../../components/Mascot'
import SpeechBubble from '../../components/SpeechBubble'
import ProgressBar from '../../components/ProgressBar'
import InkButton from '../../components/InkButton'
import { ApiError, generateQuiz } from '../../services/api'
import { useQuizStore } from '../../store/quizStore'
import type { QuizGenerateRequest } from '../../types'

import './index.scss'

type Stage = 'loading' | 'error'

const STEPS = ['搜集资料 · 锁定核心知识', '划重点 · 圈出关键概念', '出题中 · 按你的题型搭配生成…']

export default function Generating() {
  const [stage, setStage] = useState<Stage>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [errorCode, setErrorCode] = useState('')
  const [stepIndex, setStepIndex] = useState(0)
  const startedRef = useRef(false)

  const run = async () => {
    setStage('loading')
    setStepIndex(0)

    const request = Taro.getStorageSync('pending_quiz_request') as QuizGenerateRequest | ''
    if (!request) {
      Taro.redirectTo({ url: '/pages/index/index' })
      return
    }

    try {
      const data = await generateQuiz(request)
      useQuizStore.getState().startQuiz(data)
      Taro.redirectTo({ url: '/pages/quiz/index' })
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMsg(error.message)
        setErrorCode(error.code >= 0 ? String(error.code) : error.code === -2 ? 'TIMEOUT' : 'NETWORK')
      } else {
        setErrorMsg('生成失败了，请稍后重试')
        setErrorCode('UNKNOWN')
      }
      setStage('error')
    }
  }

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true

    run()
    const timer = setInterval(() => {
      setStepIndex((index) => (index >= STEPS.length - 1 ? index : index + 1))
    }, 1800)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const changeTopic = () => {
    Taro.redirectTo({ url: '/pages/index/index' })
  }

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
            {STEPS.map((label, index) => (
              <View key={label} className={`step ${index === stepIndex ? 'step--doing' : ''}`}>
                <View className='step__icon'>{index < stepIndex ? '✓' : index === stepIndex ? '⟳' : ''}</View>
                <Text className='step__label'>{label}</Text>
              </View>
            ))}
          </View>

          <ProgressBar percent={66} height={20} className='loading-stage__progress' />
          <Text className='loading-stage__foot'>别急，比等一碗泡面还快 🍜</Text>
        </View>
      ) : (
        <View className='error-stage'>
          <Mascot variant='dizzy' size={150} />
          <Text className='error-stage__title'>AI 卡壳了…</Text>
          <Text className='error-stage__desc'>
            {errorMsg || '题目生成失败，可能是网络打了个盹 💤'}
            {'\n'}别慌，重试一般就好
          </Text>

          <View className='error-stage__actions'>
            <InkButton type='primary' size='large' onClick={run}>
              🔄 重新生成
            </InkButton>
            <InkButton type='secondary' size='large' className='error-stage__gap' onClick={changeTopic}>
              换个主题试试
            </InkButton>
          </View>

          <Text className='error-stage__code'>错误码：{errorCode}</Text>
        </View>
      )}
    </PageShell>
  )
}
