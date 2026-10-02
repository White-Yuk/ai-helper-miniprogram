import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import Mascot from '../../components/Mascot'
import InkButton from '../../components/InkButton'
import { fetchKnowledgeDetail } from '../../services/api'
import type { KnowledgeDetailData, KnowledgeState } from '../../types'

import './index.scss'

const STATE_LABEL: Record<KnowledgeState, string> = {
  mastered: '掌握',
  weak: '薄弱',
  unlearned: '未学',
}

const STATE_CLASS: Record<KnowledgeState, string> = {
  mastered: 'ok',
  weak: 'warn',
  unlearned: 'none',
}

type Status = 'loading' | 'success' | 'error'

export default function Mastery() {
  const [status, setStatus] = useState<Status>('loading')
  const [data, setData] = useState<KnowledgeDetailData | null>(null)
  const [errorMsg, setErrorMsg] = useState('')

  const quizId = Taro.getCurrentInstance().router?.params?.quiz_id || ''

  const load = async () => {
    if (!quizId) {
      setErrorMsg('缺少闯关参数，无法查看详情')
      setStatus('error')
      return
    }
    setStatus('loading')
    try {
      const result = await fetchKnowledgeDetail(quizId)
      setData(result)
      setStatus('success')
    } catch (error) {
      setErrorMsg((error as { message?: string })?.message || '加载失败，请稍后重试')
      setStatus('error')
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const goBack = () => {
    const pages = Taro.getCurrentPages()
    if (pages.length > 1) {
      Taro.navigateBack()
    } else {
      Taro.redirectTo({ url: '/pages/index/index' })
    }
  }

  /** 再来一关，专练薄弱点：回首页并预填强化主题（等待用户确认后生成） */
  const practiceWeakPoints = () => {
    if (!data) return
    const weakPoints = data.points
      .filter((point) => point.state === 'weak')
      .map((point) => point.name)
      .slice(0, 3)
    const focus = weakPoints.length > 0 ? `（薄弱点：${weakPoints.join('、')}）` : ''
    Taro.setStorageSync('prefill_input', `强化练习：${data.title}${focus}`)
    Taro.redirectTo({ url: '/pages/index/index' })
  }

  const hasWeak = !!data && data.weak_count > 0

  return (
    <PageShell className='mastery-page'>
      {/* 顶栏 */}
      <View className='mastery-top'>
        <BackButton onClick={goBack} />
        <Text className='mastery-top__title'>知识掌握</Text>
      </View>

      {status === 'loading' && (
        <View className='mastery-status'>
          <Mascot size={120} />
          <Text className='mastery-status__text'>正在翻你的知识档案… 📚</Text>
        </View>
      )}

      {status === 'error' && (
        <View className='mastery-status'>
          <Mascot variant='dizzy' size={120} />
          <Text className='mastery-status__text'>{errorMsg}</Text>
          <InkButton type='primary' size='large' onClick={load}>
            🔄 重新加载
          </InkButton>
        </View>
      )}

      {status === 'success' && data && (
        <View className='mastery-body'>
          {/* 头部：环形 + 概览 */}
          <View className='master-head'>
            <View className='ring-sm'>
              <View
                className='ring-sm__arc'
                style={{
                  background: `conic-gradient(#3FA34D 0 ${data.accuracy * 3.6}deg, #EAE2D4 ${data.accuracy * 3.6}deg 360deg)`,
                }}
              />
              <View className='ring-sm__hole'>
                <Text className='ring-sm__val'>{data.accuracy}%</Text>
              </View>
            </View>
            <View className='master-head__info'>
              <Text className='master-head__title'>{data.title}</Text>
              <Text className='master-head__sub'>
                共 {data.total_points} 个知识点 · 已掌握 {data.mastered_count} 个{'\n'}
                薄弱 {data.weak_count} 个 · 未学 {data.unlearned_count} 个
              </Text>
            </View>
          </View>

          {/* 知识点清单 */}
          <View className='sec-flag'>知识点掌握明细 👇</View>
          <View className='kp-list'>
            {data.points.map((point) => (
              <View
                key={point.name}
                className={`kp-row ${point.state === 'unlearned' ? 'kp-row--dim' : ''}`}
              >
                <Text className='kp-row__name'>{point.name}</Text>
                <View className='kp-row__bar'>
                  <View className='bar-track'>
                    <View
                      className={`bar-fill ${point.state === 'mastered' ? 'bar-fill--green' : point.state === 'weak' ? 'bar-fill--red' : ''}`}
                      style={{ width: `${point.accuracy}%` }}
                    />
                  </View>
                </View>
                <Text className={`kp-state kp-state--${STATE_CLASS[point.state]}`}>
                  {STATE_LABEL[point.state]}
                </Text>
              </View>
            ))}
          </View>

          {/* 提示 */}
          <View className='mastery-tip'>
            <Text>💡 薄弱点会自动成错题重练，别担心漏掉</Text>
          </View>

          <View className='mastery-foot'>
            <InkButton type='primary' size='large' onClick={practiceWeakPoints}>
              {hasWeak ? '再来一关，专练薄弱点 →' : '再来一关，巩固一下 →'}
            </InkButton>
          </View>
        </View>
      )}
    </PageShell>
  )
}
