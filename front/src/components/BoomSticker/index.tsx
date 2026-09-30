import { PropsWithChildren } from 'react'
import { View, Image } from '@tarojs/components'

import boomYellow from '../../assets/boom-yellow.png'
import boomRed from '../../assets/boom-red.png'

import './index.scss'

interface BoomStickerProps {
  /** 贴纸边长（px） */
  size?: number
  color?: 'yellow' | 'red'
  className?: string
}

/** 爆炸贴纸：答对 / COMBO / 结算的欢呼元素 */
export default function BoomSticker({
  size = 150,
  color = 'yellow',
  className = '',
  children,
}: PropsWithChildren<BoomStickerProps>) {
  return (
    <View className={`boom-sticker ${className}`} style={{ width: `${size}px`, height: `${size}px` }}>
      <Image className='boom-sticker__bg' src={color === 'red' ? boomRed : boomYellow} mode='aspectFit' />
      <View className='boom-sticker__content'>{children}</View>
    </View>
  )
}
