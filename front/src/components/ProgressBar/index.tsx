import { View } from '@tarojs/components'

import './index.scss'

interface ProgressBarProps {
  /** 0 - 100 */
  percent: number
  color?: 'yellow' | 'red'
  height?: number
  className?: string
}

/** 闯关进度条：粗描边胶囊 + 斜纹填充 */
export default function ProgressBar({ percent, color = 'yellow', height = 20, className = '' }: ProgressBarProps) {
  const safePercent = Math.max(0, Math.min(100, percent))
  return (
    <View className={`progress-bar progress-bar--${color} ${className}`} style={{ height: `${height}px` }}>
      <View className='progress-bar__fill' style={{ width: `${safePercent}%` }} />
    </View>
  )
}
