import { useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import Mascot from '../../components/Mascot'
import SpeechBubble from '../../components/SpeechBubble'
import InkButton from '../../components/InkButton'
import { ApiError, generateReport, submitQuiz } from '../../services/api'
import { useQuizStore } from '../../store/quizStore'
import type { ReportData } from '../../types'

import './index.scss'

type Status = 'loading' | 'success' | 'error'

export default function Report() {
  const quiz = useQuizStore((state) => state.quiz)
  const records = useQuizStore((state) => state.records)

  const [status, setStatus] = useState<Status>('loading')
  const [report, setReport] = useState<ReportData | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const startedRef = useRef(false)

  const load = async () => {
    if (!quiz) return
    setStatus('loading')

    try {
      const data = await generateReport({
        quiz_id: quiz.quiz_id,
        topic: quiz.title,
        questions: quiz.questions,
        answer_records: records,
      })
      setReport(data)
      setStatus('success')

      // 阶段 3：提交完成数据（quiz 置 done + answers 定稿）；失败不阻塞报告展示，
      // 此时 quiz 仍为“进行中”，首页续答卡片可再次进入本页重试（提交幂等）
      void submitQuiz(quiz.quiz_id, { records }).catch((error) => {
        console.warn('[report] 完成数据提交失败', error)
      })

      // 存档：供海报页与首页「上次战绩」使用
      const { xp, maxCombo } = useQuizStore.getState()
      Taro.setStorageSync('last_report', {
        topic: quiz.title,
        accuracy: data.accuracy,
        xp,
        max_combo: maxCombo,
        share_quote: data.share_quote,
        date: new Date().toLocaleDateString(),
      })
    } catch (error) {
      setErrorMsg(error instanceof ApiError ? error.message : '报告生成失败，请稍后重试')
      setStatus('error')
    }
  }

  useEffect(() => {
    if (!quiz) {
      Taro.redirectTo({ url: '/pages/index/index' })
      return
    }
    if (startedRef.current) return
    startedRef.current = true
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const goPoster = () => {
    Taro.navigateTo({ url: '/pages/poster/index' })
  }

  const wrongCount = records.filter((record) => !record.is_correct).length

  return (
    <PageShell className='report-page'>
      {status === 'loading' && (
        <View className='report-status'>
          <Mascot size={130} />
          <SpeechBubble className='report-status__bubble'>正在生成复盘报告…{'\n'}翻翻错题，看看你哪里最强 💪</SpeechBubble>
        </View>
      )}

      {status === 'error' && (
        <View className='report-status'>
          <Mascot variant='dizzy' size={130} />
          <Text className='report-status__error'>{errorMsg}</Text>
          <View className='report-status__actions'>
            <InkButton type='primary' size='large' onClick={load}>
              🔄 重新生成报告
            </InkButton>
          </View>
        </View>
      )}

      {status === 'success' && report && quiz && (
        <View className='report-body'>
          {/* 头部 */}
          <View className='report-head'>
            <View className='report-head__left'>
              <BackButton onClick={() => Taro.navigateBack()} />
            </View>
            <View className='report-head__card'>
              <Text className='report-head__title'>{quiz.title} · 复盘报告</Text>
              <Text className='report-head__sub'>
                共 {quiz.questions.length} 题 · 错 {wrongCount} 题
              </Text>
            </View>
          </View>

          {/* 正确率 */}
          <View className='ring-wrap'>
            <View className='ring'>
              <View
                className='ring__arc'
                style={{ background: `conic-gradient(#3FA34D 0 ${report.accuracy * 3.6}deg, #EAE2D4 ${report.accuracy * 3.6}deg 360deg)` }}
              />
              <View className='ring__hole'>
                <Text className='ring__val'>{report.accuracy}%</Text>
              </View>
            </View>
            <View className='ring-copy'>
              <Text>本关正确率 </Text>
              <Text className='ring-copy__strong'>{report.accuracy}%</Text>
              <Text>{'\n'}连对最高 ×{useQuizStore.getState().maxCombo} · 错 {wrongCount} 题</Text>
            </View>
          </View>

          {/* 三句总结 */}
          <View className='sec-flag'>三句话总结这关 👇</View>
          <View className='sum-list'>
            {report.three_line_summary.slice(0, 3).map((line, index) => (
              <View key={line} className='sum-item'>
                <Text className='sum-item__no'>{String(index + 1).padStart(2, '0')}</Text>
                <Text className='sum-item__text'>{line}</Text>
              </View>
            ))}
          </View>

          {/* 掌握 / 薄弱 */}
          <View className='point-grid'>
            <View className='point-card point-card--good'>
              <Text className='point-card__title'>✅ 掌握较好</Text>
              {report.mastered_points.map((point) => (
                <Text key={point} className='point-card__item'>
                  · {point}
                </Text>
              ))}
            </View>
            <View className='point-card point-card--bad'>
              <Text className='point-card__title'>❌ 薄弱点</Text>
              {report.weak_points.length > 0 ? (
                report.weak_points.map((point) => (
                  <Text key={point} className='point-card__item'>
                    · {point}
                  </Text>
                ))
              ) : (
                <Text className='point-card__item'>· 全部拿下，暂无薄弱点</Text>
              )}
            </View>
          </View>

          {/* 建议 */}
          <View className='advice-bar'>
            <Text>💡 下一步：{report.advice.join('；')}</Text>
          </View>

          <InkButton type='primary' size='large' onClick={goPoster}>
            生成战报海报，去炫耀 →
          </InkButton>
        </View>
      )}
    </PageShell>
  )
}
