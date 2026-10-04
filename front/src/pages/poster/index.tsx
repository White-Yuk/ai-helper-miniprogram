import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import Mascot from '../../components/Mascot'
import InkButton from '../../components/InkButton'
import qrImg from '../../assets/qr-placeholder.png'
import { useQuizStore } from '../../store/quizStore'
import { calcAccuracy } from '../../utils/grader'

import './index.scss'

interface LastReport {
  topic: string
  accuracy: number
  xp: number
  max_combo: number
  share_quote: string
  date: string
}

/** 分享海报（简化占位版）：展示战报 + 操作引导 */
export default function Poster() {
  const quiz = useQuizStore((state) => state.quiz)
  const records = useQuizStore((state) => state.records)
  const xpStore = useQuizStore((state) => state.xp)
  const maxComboStore = useQuizStore((state) => state.maxCombo)

  const stored = Taro.getStorageSync('last_report') as LastReport | ''

  // 优先使用存档数据；否则从当前会话兜底
  const topic = (stored && stored.topic) || quiz?.title || '知识闯关'
  const accuracy =
    stored && typeof stored.accuracy === 'number'
      ? stored.accuracy
      : calcAccuracy(
          records.length || quiz?.questions.length || 0,
          records.filter((record) => record.is_correct).length,
        )
  const xp = (stored && stored.xp) || xpStore
  const maxCombo = (stored && stored.max_combo) || maxComboStore
  const quote = (stored && stored.share_quote) || '把知识做成关卡，记忆会更深。'

  const onSave = () => {
    Taro.showToast({ title: '长按海报截图保存吧', icon: 'none', duration: 2500 })
  }

  const onShare = () => {
    Taro.showToast({ title: '点击右上角「…」分享给好友', icon: 'none', duration: 2500 })
  }

  return (
    <PageShell className='poster-page'>
      <View className='poster-top'>
        <BackButton onClick={() => Taro.navigateBack()} />
        <Text className='poster-top__hint'>长按海报可截图保存 📸</Text>
      </View>

      <View className='poster'>
        <Text className='poster__sfx'>BOOM!</Text>

        <View className='poster__brand'>
          <Text>🤖 AI 闯关学习 · 学习战报</Text>
        </View>

        <Mascot variant='happy' size={100} className='poster__mascot' />

        <Text className='poster__title'>今天我又{'\n'}闯过一关！</Text>

        <View className='poster__quote'>
          <Text className='poster__quote-mark'>“</Text>
          <Text className='poster__quote-text'>{quote}</Text>
        </View>

        <View className='poster__stats'>
          <View className='poster__stat'>
            <Text className='poster__stat-value poster__stat-value--green'>{accuracy}%</Text>
            <Text className='poster__stat-label'>正确率</Text>
          </View>
          <View className='poster__stat'>
            <Text className='poster__stat-value'>+{xp}</Text>
            <Text className='poster__stat-label'>XP 经验</Text>
          </View>
          <View className='poster__stat'>
            <Text className='poster__stat-value'>×{maxCombo}</Text>
            <Text className='poster__stat-label'>最高连对</Text>
          </View>
        </View>

        <View className='poster__foot'>
          <Image className='poster__qr' src={qrImg} mode='aspectFit' />
          <View className='poster__foot-text'>
            <Text className='poster__foot-t1'>长按扫码，来和我一起闯关</Text>
            <Text className='poster__foot-t2'>输入任何知识，AI 帮你出题</Text>
          </View>
        </View>

        <Text className='poster__topic'>本期主题：{topic}</Text>
      </View>

      <View className='poster-actions'>
        <InkButton type='secondary' size='large' onClick={onSave}>
          💾 保存到相册
        </InkButton>
        <InkButton type='primary' size='large' className='poster-actions__gap' onClick={onShare}>
          📤 分享给好友
        </InkButton>
      </View>
    </PageShell>
  )
}
