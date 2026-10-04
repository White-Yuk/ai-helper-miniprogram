import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import Mascot from '../../components/Mascot'
import InkButton from '../../components/InkButton'
import { fetchWrongbook } from '../../services/api'
import type { WrongbookData } from '../../types'
import { getCapsuleInset } from '../../utils/navInset'

import './index.scss'

type Status = 'loading' | 'success' | 'error'

export default function Wrongbook() {
  const [status, setStatus] = useState<Status>('loading')
  const [data, setData] = useState<WrongbookData | null>(null)
  const [errorMsg, setErrorMsg] = useState('')

  const load = async () => {
    try {
      const result = await fetchWrongbook()
      setData(result)
      setStatus('success')
    } catch (error) {
      setErrorMsg((error as { message?: string })?.message || '错题本加载失败，请稍后重试')
      setStatus('error')
    }
  }

  // 每次页面显示时刷新（重做完返回后看到最新列表）
  useDidShow(() => {
    void load()
  })

  const startRedo = (questionId?: string) => {
    if (!data || data.total === 0) return
    if (questionId) {
      Taro.navigateTo({ url: `/pages/redo/index?question_id=${questionId}` })
    } else {
      Taro.navigateTo({ url: '/pages/redo/index' })
    }
  }

  const goHome = () => {
    Taro.redirectTo({ url: '/pages/index/index' })
  }

  return (
    <PageShell className='wrongbook-page'>
      {/* 顶栏（右侧动态避开微信胶囊按钮：防止待清理徽章被遮挡） */}
      <View className='wrongbook-top' style={{ paddingRight: getCapsuleInset() }}>
        <BackButton />
        <Text className='wrongbook-top__title'>我的错题本</Text>
        {status === 'success' && data && data.total > 0 && (
          <Text className='wrongbook-top__count'>共 {data.total} 道待清理</Text>
        )}
      </View>

      {status === 'loading' && (
        <View className='wrongbook-status'>
          <Mascot size={120} />
          <Text className='wrongbook-status__text'>正在翻错题本… 🔍</Text>
        </View>
      )}

      {status === 'error' && (
        <View className='wrongbook-status'>
          <Mascot variant='dizzy' size={120} />
          <Text className='wrongbook-status__text'>{errorMsg}</Text>
          <InkButton type='primary' size='large' onClick={load}>
            🔄 重新加载
          </InkButton>
        </View>
      )}

      {status === 'success' && data && data.total === 0 && (
        <View className='wrongbook-empty'>
          <Mascot size={110} />
          <Text className='wrongbook-empty__title'>错题本空空如也！</Text>
          <Text className='wrongbook-empty__desc'>
            要么你全答对了，要么…你还没开始闯关？{'\n'}不管哪种，现在都是刷题的好时候
          </Text>
          <InkButton type='primary' size='large' onClick={goHome}>
            去闯一关 →
          </InkButton>
        </View>
      )}

      {status === 'success' && data && data.total > 0 && (
        <View className='wrongbook-list'>
          {data.items.map((item) => (
            <View key={`${item.quiz_id}-${item.question_id}`} className='wrong-card'>
              <View className='wrong-card__top'>
                <Text className='wrong-card__tag'>{item.knowledge_point || '知识点'}</Text>
                <Text className='wrong-card__count'>错 {item.wrong_count} 次</Text>
              </View>
              <Text className='wrong-card__stem'>{item.stem}</Text>
              <View className='wrong-card__foot'>
                <View
                  className='wrong-card__btn'
                  hoverClass='wrong-card__btn--active'
                  onClick={() => startRedo(item.question_id)}
                >
                  <Text>重做 →</Text>
                </View>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 底部主按钮 */}
      {status === 'success' && data && data.total > 0 && (
        <View className='wrongbook-foot'>
          <InkButton type='primary' size='large' onClick={() => startRedo()}>
            开始清理错题（{data.total}）→
          </InkButton>
        </View>
      )}
    </PageShell>
  )
}
