import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import Mascot from '../../components/Mascot'
import SpeechBubble from '../../components/SpeechBubble'
import InkButton from '../../components/InkButton'
import { fetchStats } from '../../services/api'
import type { StatsData, StatsRange, TrendPoint } from '../../types'

import './index.scss'

const RANGE_OPTIONS: { key: StatsRange; label: string }[] = [
  { key: 'week', label: '本周' },
  { key: 'month', label: '本月' },
  { key: 'all', label: '全部' },
]

const WEEK_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const CHART_HEIGHT = 96 // px
const FALLBACK_WIDTH = 300 // 测量失败时的兜底宽度

type Status = 'loading' | 'success' | 'error'

/** accuracy -> 纵坐标百分比（顶部留边距，100% 在上、0% 在下） */
function yPct(accuracy: number): number {
  return 94 - (accuracy / 100) * 88
}

/** 计算 x 轴标签：week 固定周一到周日；month/all 取首/三分之一/三分之二/尾的日期 */
function buildAxisLabels(trend: TrendPoint[], range: StatsRange): string[] {
  if (range === 'week') return WEEK_LABELS
  if (trend.length === 0) return []
  const last = trend.length - 1
  const indexes = Array.from(new Set([0, Math.floor(last / 3), Math.floor((last * 2) / 3), last]))
  return indexes.map((index) => trend[index].date.slice(5))
}

/** View/CSS 手绘折线图（小程序端不支持 SVG 元素） */
function TrendChart({ trend, chartWidth }: { trend: TrendPoint[]; chartWidth: number }) {
  const total = trend.length
  const valid = trend
    .map((point, index) => ({ index, accuracy: point.accuracy }))
    .filter((item): item is { index: number; accuracy: number } => item.accuracy !== null)

  const xOf = (index: number) => (total > 1 ? (index / (total - 1)) * 100 : 50)
  const width = chartWidth || FALLBACK_WIDTH

  const segments: { left: number; top: number; length: number; angle: number }[] = []
  for (let i = 0; i < valid.length - 1; i += 1) {
    const ax = (xOf(valid[i].index) / 100) * width
    const ay = (yPct(valid[i].accuracy) / 100) * CHART_HEIGHT
    const bx = (xOf(valid[i + 1].index) / 100) * width
    const by = (yPct(valid[i + 1].accuracy) / 100) * CHART_HEIGHT
    const length = Math.hypot(bx - ax, by - ay)
    const angle = (Math.atan2(by - ay, bx - ax) * 180) / Math.PI
    segments.push({ left: ax, top: ay, length, angle })
  }

  return (
    <View className='line-chart' id='line-chart' style={{ height: `${CHART_HEIGHT}px` }}>
      {segments.map((segment, index) => (
        <View
          key={`seg-${index}`}
          className='line-seg'
          style={{
            left: `${segment.left}px`,
            top: `${segment.top - 2}px`,
            width: `${segment.length}px`,
            transform: `rotate(${segment.angle}deg)`,
          }}
        />
      ))}
      {valid.map((item) => (
        <View
          key={`dot-${item.index}`}
          className='line-dot'
          style={{ left: `${xOf(item.index)}%`, top: `${yPct(item.accuracy)}%` }}
        />
      ))}
    </View>
  )
}

export default function Stats() {
  const [range, setRange] = useState<StatsRange>('week')
  const [status, setStatus] = useState<Status>('loading')
  const [data, setData] = useState<StatsData | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [chartWidth, setChartWidth] = useState(0)

  const load = async (target: StatsRange) => {
    setStatus('loading')
    try {
      const result = await fetchStats(target)
      setData(result)
      setStatus('success')
    } catch (error) {
      setErrorMsg((error as { message?: string })?.message || '报表加载失败，请稍后重试')
      setStatus('error')
    }
  }

  useEffect(() => {
    void load(range)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range])

  // 图表渲染后测量容器宽度（用于手绘线段像素坐标）
  useEffect(() => {
    if (status !== 'success') return
    Taro.nextTick(() => {
      Taro.createSelectorQuery()
        .select('#line-chart')
        .boundingClientRect((rect) => {
          const result = Array.isArray(rect) ? rect[0] : rect
          if (result && result.width > 0) setChartWidth(result.width)
        })
        .exec()
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, data])

  const goHome = () => {
    Taro.redirectTo({ url: '/pages/index/index' })
  }

  const hasNoData = !!data && data.domains.length === 0 && data.trend.every((point) => point.accuracy === null)

  return (
    <PageShell className='stats-page'>
      {/* 顶栏 */}
      <View className='stats-top'>
        <BackButton />
        <Text className='stats-top__title'>学习汇报</Text>
      </View>

      {/* 范围切换 */}
      <View className='chip-row'>
        {RANGE_OPTIONS.map(({ key, label }) => (
          <View
            key={key}
            className={`chip ${range === key ? 'chip--on' : ''}`}
            hoverClass='none'
            onClick={() => setRange(key)}
          >
            <Text>{label}</Text>
          </View>
        ))}
      </View>

      {status === 'loading' && (
        <View className='stats-status'>
          <Mascot size={120} />
          <SpeechBubble className='stats-status__bubble'>正在算你的成绩单…{'\n'}马上就好 ⏳</SpeechBubble>
        </View>
      )}

      {status === 'error' && (
        <View className='stats-status'>
          <Mascot variant='dizzy' size={120} />
          <Text className='stats-status__error'>{errorMsg}</Text>
          <InkButton type='primary' size='large' onClick={() => load(range)}>
            🔄 重新加载
          </InkButton>
        </View>
      )}

      {status === 'success' && data && hasNoData && (
        <View className='stats-empty'>
          <Mascot size={120} />
          <Text className='stats-empty__title'>还没有学习数据</Text>
          <Text className='stats-empty__desc'>
            先去闯一关，回来这里看你的进步曲线 📈
          </Text>
          <InkButton type='primary' size='large' onClick={goHome}>
            ⚡ 去闯一关
          </InkButton>
        </View>
      )}

      {status === 'success' && data && !hasNoData && (
        <View>
          {/* 正确率趋势 */}
          <View className='chart-card'>
            <View className='chart-card__title'>
              <Text>正确率趋势</Text>
              <Text className='chart-card__value'>
                {data.overall_accuracy === null ? '—' : `↗ ${data.overall_accuracy}%`}
              </Text>
            </View>
            <TrendChart trend={data.trend} chartWidth={chartWidth} />
            <View className='line-axis'>
              {buildAxisLabels(data.trend, data.range).map((label, index) => (
                <Text key={`${label}-${index}`}>{label}</Text>
              ))}
            </View>
          </View>

          {/* 各领域掌握度 */}
          <View className='chart-card'>
            <View className='chart-card__title'>
              <Text>各领域掌握度</Text>
            </View>
            {data.domains.length === 0 && <Text className='domain-empty'>先完成一次闯关，再来看看各领域掌握度～</Text>}
            {data.domains.map((domain) => (
              <View key={domain.quiz_id} className='hbar-row'>
                <Text className='hbar-row__lbl'>{domain.name}</Text>
                <View className='bar-track'>
                  <View
                    className={`bar-fill ${domain.accuracy >= 70 ? 'bar-fill--green' : domain.accuracy < 50 ? 'bar-fill--red' : ''}`}
                    style={{ width: `${domain.accuracy}%` }}
                  />
                </View>
                <Text className='hbar-row__val'>{domain.accuracy}%</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </PageShell>
  )
}
