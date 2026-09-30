import { PropsWithChildren } from 'react'
import { View } from '@tarojs/components'

import './index.scss'

interface SpeechBubbleProps {
  variant?: 'yellow' | 'white'
  tail?: boolean
  className?: string
}

/** 漫画对话气泡：AI 讲解与引导的载体 */
export default function SpeechBubble({
  variant = 'yellow',
  tail = true,
  className = '',
  children,
}: PropsWithChildren<SpeechBubbleProps>) {
  return (
    <View className={`speech-bubble speech-bubble--${variant} ${tail ? 'speech-bubble--tail' : ''} ${className}`}>
      {children}
    </View>
  )
}
