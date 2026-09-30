import { PropsWithChildren } from 'react'
import { View } from '@tarojs/components'

import './index.scss'

interface BadgeProps {
  /** xp 黄色经验徽章 / combo 红色连击 / plain 白底 */
  variant?: 'xp' | 'combo' | 'plain'
  className?: string
}

/** 小徽章：XP / 连击 / 普通标签 */
export default function Badge({ variant = 'plain', className = '', children }: PropsWithChildren<BadgeProps>) {
  return <View className={`badge badge--${variant} ${className}`}>{children}</View>
}
