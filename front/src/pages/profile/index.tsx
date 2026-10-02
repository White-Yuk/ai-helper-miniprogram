import { useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import Mascot from '../../components/Mascot'
import { ApiError } from '../../services/api'
import { useUserStore } from '../../store/userStore'

import './index.scss'

const TOOLBOX = [
  { key: 'library', icon: '📚', label: '知识库' },
  { key: 'wrongbook', icon: '📕', label: '错题本' },
  { key: 'stats', icon: '📊', label: '学习汇报' },
  { key: 'settings', icon: '⚙️', label: '设置' },
] as const

const TOOLBOX_LAUNCHING: Record<(typeof TOOLBOX)[number]['key'], string> = {
  library: '知识库即将上线',
  wrongbook: '错题本即将上线',
  stats: '学习汇报即将上线',
  settings: '设置即将上线',
}

export default function Profile() {
  const me = useUserStore((state) => state.me)
  const loading = useUserStore((state) => state.loading)
  const loadMe = useUserStore((state) => state.loadMe)

  useEffect(() => {
    loadMe().catch((error) => {
      const message = error instanceof ApiError ? error.message : '用户信息加载失败，请稍后重试'
      Taro.showToast({ title: message, icon: 'none' })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const stats = me?.stats
  const continueLearning = me?.continue_learning

  const nickname = me?.nickname || (loading ? '登录中…' : '未登录')

  const handleToolClick = (key: keyof typeof TOOLBOX_LAUNCHING) => {
    Taro.showToast({ title: TOOLBOX_LAUNCHING[key], icon: 'none' })
  }

  return (
    <PageShell className='profile-page'>
      {/* 顶栏 */}
      <View className='profile-top'>
        <BackButton />
        <Text className='profile-top__title'>个人中心</Text>
      </View>

      {/* 用户信息 */}
      <View className='profile-head'>
        <View className='profile-head__avatar'>
          <Mascot size={62} />
        </View>
        <View className='profile-head__info'>
          <Text className='profile-head__name'>{nickname}</Text>
          <Text className='profile-head__desc'>已闯 {stats?.quiz_count ?? 0} 关</Text>
        </View>
      </View>

      {/* 数据概览 */}
      <View className='stat3'>
        <View className='stat3__box'>
          <Text className='stat3__value'>{stats?.quiz_count ?? 0}</Text>
          <Text className='stat3__label'>闯关数</Text>
        </View>
        <View className='stat3__box'>
          <Text className='stat3__value'>{stats?.answered_count ?? 0}</Text>
          <Text className='stat3__label'>累计答题</Text>
        </View>
        <View className='stat3__box'>
          <Text className='stat3__value stat3__value--green'>{stats?.avg_accuracy ?? 0}%</Text>
          <Text className='stat3__label'>平均正确率</Text>
        </View>
      </View>

      {/* 工具箱 */}
      <View className='sec-flag'>我的工具箱 👇</View>
      <View className='toolbox'>
        {TOOLBOX.map((item) => (
          <View
            key={item.key}
            className='toolbox__item'
            hoverClass='toolbox__item--active'
            onClick={() => handleToolClick(item.key)}
          >
            <Text className='toolbox__icon'>{item.icon}</Text>
            <Text className='toolbox__label'>{item.label}</Text>
          </View>
        ))}
      </View>

      {/* 继续学习（阶段 3 接入数据后展示） */}
      {continueLearning && (
        <View className='continue-card'>
          <View className='continue-card__info'>
            <Text className='continue-card__title'>
              上次学到：{continueLearning.title} · 第 {continueLearning.current_index + 1}/{continueLearning.total} 关
            </Text>
            <Text className='continue-card__sub'>别让它跑了，继续通关吧！</Text>
          </View>
          <Text className='continue-card__go'>继续 →</Text>
        </View>
      )}
    </PageShell>
  )
}
