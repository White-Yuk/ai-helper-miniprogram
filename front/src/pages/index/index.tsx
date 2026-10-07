import { useState } from 'react'
import { View, Text, Textarea, Image } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import Mascot from '../../components/Mascot'
import InkButton from '../../components/InkButton'
import { fetchUnfinishedQuiz, resolveAssetUrl } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import { useQuizStore } from '../../store/quizStore'
import { useUserStore } from '../../store/userStore'
import type { QuestionType, QuizDifficulty, UnfinishedQuizData } from '../../types'
import { getCapsuleInset } from '../../utils/navInset'

import './index.scss'

const EXAMPLE_TOPICS = ['Python 入门', '量子力学', '法国大革命', '剪辑技巧']

const TYPE_OPTIONS: { key: QuestionType; label: string }[] = [
  { key: 'single', label: '单选' },
  { key: 'multiple', label: '多选' },
  { key: 'judge', label: '判断' },
  { key: 'fill', label: '填空' },
]

const COUNT_OPTIONS = [3, 5, 10]

const DIFFICULTY_OPTIONS: { key: QuizDifficulty; label: string }[] = [
  { key: 'easy', label: '简单' },
  { key: 'mixed', label: '混合' },
  { key: 'hard', label: '困难' },
]

/** 续答卡片副标题（对齐原型 P01：“上次正确率 80% · 错 1 题”） */
function buildResumeSubtitle(data: UnfinishedQuizData): string {
  if (data.records.length === 0) return '还没开打 · 现在出发'
  const correct = data.records.filter((record) => record.is_correct).length
  const accuracy = Math.round((correct / data.records.length) * 100)
  return `上次正确率 ${accuracy}% · 错 ${data.records.length - correct} 题`
}

export default function Index() {
  const me = useUserStore((state) => state.me)
  const loadMe = useUserStore((state) => state.loadMe)
  const [userInput, setUserInput] = useState('')
  const [sheetVisible, setSheetVisible] = useState(false)
  const [types, setTypes] = useState<QuestionType[]>(['single', 'multiple', 'judge'])
  const [count, setCount] = useState(5)
  const [difficulty, setDifficulty] = useState<QuizDifficulty>('mixed')
  const [unfinished, setUnfinished] = useState<UnfinishedQuizData | null>(null)

  // 每次页面显示时：读取续答卡片 / 接收「专练薄弱点」预填主题；刷新「上次没打完的」
  useDidShow(() => {
    const prefill = Taro.getStorageSync('prefill_input')
    if (prefill) {
      setUserInput(String(prefill))
      Taro.removeStorageSync('prefill_input')
    }

    ensureLogin()
      .then(() => fetchUnfinishedQuiz())
      .then((data) => setUnfinished(data))
      .catch(() => {
        // 未登录 / 网络异常：不展示卡片，不打扰主流程
      })

    // 刷新用户信息（右上角头像展示；失败静默，保持“我”字占位）
    loadMe().catch(() => {})
  })

  /** 继续上次没打完的闯关（阶段 3） */
  const resumeQuiz = () => {
    if (!unfinished) return
    const { quiz_id, title, summary, questions, records, current_index, total } = unfinished
    useQuizStore.getState().restoreQuiz({ quiz_id, title, summary, questions }, records, current_index)
    // 已答完但未提交（如报告生成失败退出）：直接回报告页重试
    if (current_index >= total) {
      Taro.navigateTo({ url: '/pages/report/index' })
    } else {
      Taro.navigateTo({ url: '/pages/quiz/index' })
    }
  }

  const openConfig = () => {
    if (!userInput.trim()) {
      Taro.showToast({ title: '先输入一个知识点吧', icon: 'none' })
      return
    }
    setSheetVisible(true)
  }

  const toggleType = (key: QuestionType) => {
    setTypes((prev) => {
      if (prev.includes(key)) {
        if (prev.length === 1) {
          Taro.showToast({ title: '至少要留一种题型', icon: 'none' })
          return prev
        }
        return prev.filter((item) => item !== key)
      }
      return [...prev, key]
    })
  }

  const startGenerate = () => {
    const payload = {
      user_input: userInput.trim(),
      question_count: count,
      difficulty,
      question_types: types,
    }
    Taro.setStorageSync('pending_quiz_request', payload)
    setSheetVisible(false)
    Taro.navigateTo({ url: '/pages/generating/index' })
  }

  const handleAvatar = () => {
    Taro.navigateTo({ url: '/pages/profile/index' })
  }

  return (
    <PageShell className='index-page'>
      {/* 顶栏（右侧动态避开微信胶囊按钮区域） */}
      <View className='home-top' style={{ paddingRight: getCapsuleInset() }}>
        <View className='logo-sticker'>
          <Text className='logo-sticker__ai'>AI</Text>
          <Text className='logo-sticker__text'>学习助手</Text>
        </View>
        <View className='avatar-dot' hoverClass='avatar-dot--active' onClick={handleAvatar}>
          {me?.avatar ? (
            <Image className='avatar-dot__img' src={resolveAssetUrl(me.avatar)} mode='aspectFill' />
          ) : (
            <Text>我</Text>
          )}
        </View>
      </View>

      {/* 主视觉卡 */}
      <View className='hero-card'>
        <View className='hero-card__speech'>
          <Text>嘿！今天想把什么{'\n'}变成你的关卡？</Text>
        </View>
        <Text className='hero-card__sfx'>SHUA!</Text>
        <Mascot className='hero-card__mascot' size={118} />
      </View>

      {/* 输入卡 */}
      <View className='input-card'>
        <Textarea
          className='input-card__textarea'
          value={userInput}
          onInput={(event) => setUserInput(event.detail.value)}
          placeholder='输入一个知识点，比如：什么是 RAG？'
          placeholderClass='input-card__placeholder'
          maxlength={2000}
          autoHeight
          showConfirmBar={false}
        />
        <View className='input-card__hint'>
          <View className='input-card__hint-tag'>提示</View>
          <Text>一句话 / 一段文字 / 一个主题都可以</Text>
        </View>
      </View>

      {/* 主按钮 */}
      <InkButton type='primary' size='large' className='start-btn' onClick={openConfig}>
        ⚡ 开始生成闯关！
      </InkButton>

      {/* 示例主题 */}
      <View className='sec-flag'>试试这些 👇</View>
      <View className='chips'>
        {EXAMPLE_TOPICS.map((topic) => (
          <View
            key={topic}
            className='chip'
            hoverClass='chip--active'
            onClick={() => setUserInput(topic)}
          >
            <Text>{topic}</Text>
          </View>
        ))}
      </View>

      {/* 上次没打完的（阶段 3：续答入口，原型 P01） */}
      {unfinished && (
        <View>
          <View className='sec-flag'>上次没打完的 👇</View>
          <View className='recent-card' hoverClass='recent-card--active' onClick={resumeQuiz}>
            <View className='recent-card__main'>
              <Text className='recent-card__title'>
                {unfinished.title} · 第 {Math.min(unfinished.current_index + 1, unfinished.total)}/{unfinished.total} 关
              </Text>
              <Text className='recent-card__sub'>{buildResumeSubtitle(unfinished)}</Text>
            </View>
            <Text className='recent-card__go'>继续 →</Text>
          </View>
        </View>
      )}

      {/* 配置弹层 */}
      {sheetVisible && (
        <View className='config-mask' onClick={() => setSheetVisible(false)}>
          <View className='config-sheet' onClick={(event) => event.stopPropagation()}>
            <View className='config-sheet__handle' />
            <View className='config-sheet__title'>
              <Text>配置你的关卡</Text>
            </View>
            <View className='config-sheet__sub'>
              <Text>题型自由搭配，AI 按需出题</Text>
            </View>

            <View className='sheet-label'>
              <View className='sheet-label__dot' />
              <Text>搭配题型</Text>
            </View>
            <View className='type-grid'>
              {TYPE_OPTIONS.map(({ key, label }) => {
                const active = types.includes(key)
                return (
                  <View
                    key={key}
                    className={`type-chip ${active ? 'type-chip--on' : ''}`}
                    hoverClass='none'
                    onClick={() => toggleType(key)}
                  >
                    <View className='type-chip__box'>
                      <Text>{active ? '✓' : ''}</Text>
                    </View>
                    <Text className='type-chip__label'>{label}</Text>
                  </View>
                )
              })}
            </View>

            <View className='sheet-label'>
              <View className='sheet-label__dot' />
              <Text>来几道？</Text>
            </View>
            <View className='seg'>
              {COUNT_OPTIONS.map((num) => (
                <View
                  key={num}
                  className={`seg__item ${count === num ? 'seg__item--on' : ''}`}
                  onClick={() => setCount(num)}
                >
                  <Text>{num} 题</Text>
                </View>
              ))}
            </View>

            <View className='sheet-label'>
              <View className='sheet-label__dot' />
              <Text>难度口味</Text>
            </View>
            <View className='seg'>
              {DIFFICULTY_OPTIONS.map(({ key, label }) => (
                <View
                  key={key}
                  className={`seg__item ${difficulty === key ? 'seg__item--on' : ''}`}
                  onClick={() => setDifficulty(key)}
                >
                  <Text>{label}</Text>
                </View>
              ))}
            </View>

            <InkButton type='primary' size='large' className='config-sheet__cta' onClick={startGenerate}>
              ⚡ 开始生成！
            </InkButton>
            <View className='config-sheet__tip'>
              <Text>已选 {types.length} 种题型 · 填空检验记忆，选择考验理解</Text>
            </View>
          </View>
        </View>
      )}
    </PageShell>
  )
}
