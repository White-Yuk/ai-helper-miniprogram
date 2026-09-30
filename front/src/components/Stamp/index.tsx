import { View, Text } from '@tarojs/components'

import './index.scss'

interface StampProps {
  type?: 'ok' | 'no'
  size?: number
  rotate?: number
  className?: string
}

/** 作业本批改章：答对盖绿色 √、答错盖红色 × */
export default function Stamp({ type = 'ok', size = 70, rotate = -12, className = '' }: StampProps) {
  return (
    <View
      className={`stamp stamp--${type} ${className}`}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        fontSize: `${Math.round(size * 0.42)}px`,
        transform: `rotate(${rotate}deg)`,
      }}
    >
      <View className='stamp__inner' />
      <Text className='stamp__mark'>{type === 'ok' ? '√' : '×'}</Text>
    </View>
  )
}
