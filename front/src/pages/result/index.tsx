import { useEffect, useState } from 'react'
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BoomSticker from '../../components/BoomSticker'
import InkButton from '../../components/InkButton'
import boneImg from '../../assets/bone.png'
import { calcAccuracy, calcStars } from '../../utils/grader'
import { useQuizStore } from '../../store/quizStore'

import './index.scss'

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(1, Math.round(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/** 星级评价文案库（多套预设，进入结果页随机取一句，避免每次都一样） */
const STAR_COPIES: Record<number, string[]> = {
  3: ['完美！三星全收！', '这就是实力，三星满分拿下！', '太强了，一颗星都没丢！'],
  2: ['距三星只差一点点！', '稳扎稳打，两星到手！', '就快摸到三星了，冲！'],
  1: ['继续练习，冲刺两星！', '过关就是胜利，下次更稳！', '基础打牢，下关必涨星！'],
}

function pickStarCopy(stars: number): string {
  const pool = STAR_COPIES[stars] || STAR_COPIES[1]
  return pool[Math.floor(Math.random() * pool.length)]
}

export default function Result() {
  const quiz = useQuizStore((state) => state.quiz)
  const records = useQuizStore((state) => state.records)
  const xp = useQuizStore((state) => state.xp)
  const reset = useQuizStore((state) => state.reset)

  // 先计算展示数据（quiz 为空时用安全默认值，保证 hooks 调用顺序稳定）
  const total = quiz?.questions.length ?? 0
  const correct = records.filter((record) => record.is_correct).length
  const accuracy = calcAccuracy(records.length || total, correct)
  const stars = calcStars(accuracy, true)
  const durationMs = records.reduce((sum, record) => sum + (record.duration_ms || 0), 0)

  // 星级评价文案：首次渲染随机锁定一句
  const [starCopy] = useState(() => pickStarCopy(stars))

  useEffect(() => {
    if (!quiz) {
      Taro.redirectTo({ url: '/pages/index/index' })
    }
  }, [quiz])

  if (!quiz) return null

  const goReport = () => {
    Taro.navigateTo({ url: '/pages/report/index' })
  }

  const again = () => {
    reset()
    Taro.redirectTo({ url: '/pages/index/index' })
  }

  return (
    <PageShell className='result-page'>
      <View className='result-stage'>
        <BoomSticker size={230} className='result-stage__boom'>
          <Text className='result-stage__boom-text'>闯关成功！</Text>
        </BoomSticker>

        <View className='stars'>
          {[0, 1, 2].map((index) => (
            <Text key={index} className={`stars__item ${index < stars ? '' : 'stars__item--dim'}`}>
              ★
            </Text>
          ))}
        </View>
        <Text className='result-stage__copy'>{starCopy}</Text>

        <View className='result-stats'>
          <View className='result-stats__box'>
            <Text className='result-stats__value result-stats__value--green'>{accuracy}%</Text>
            <Text className='result-stats__label'>正确率</Text>
          </View>
          <View className='result-stats__box'>
            <Text className='result-stats__value'>+{xp}</Text>
            <Text className='result-stats__label'>总经验</Text>
          </View>
          <View className='result-stats__box'>
            <Text className='result-stats__value result-stats__value--red'>{formatDuration(durationMs)}</Text>
            <Text className='result-stats__label'>用时</Text>
          </View>
        </View>

        <View className='result-egg'>
          <Image className='result-egg__img' src={boneImg} mode='aspectFit' />
          <Text className='result-egg__text'>彩蛋：每通关一次，吉祥物就多一根骨头饼干 🍪</Text>
        </View>
      </View>

      <View className='result-actions'>
        <InkButton type='primary' size='large' onClick={goReport}>
          查看复盘报告 →
        </InkButton>
        <InkButton type='secondary' size='large' className='result-actions__gap' onClick={again}>
          再来一关（换个主题）
        </InkButton>
      </View>
    </PageShell>
  )
}
