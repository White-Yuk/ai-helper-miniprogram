import { View, Image } from '@tarojs/components'

import mascotNormal from '../../assets/mascot-normal.png'
import mascotHappy from '../../assets/mascot-happy.png'
import mascotDizzy from '../../assets/mascot-dizzy.png'

import './index.scss'

const SOURCES = {
  normal: mascotNormal,
  happy: mascotHappy,
  dizzy: mascotDizzy,
} as const

interface MascotProps {
  variant?: keyof typeof SOURCES
  size?: number
  className?: string
}

/** 吉祥物「蘑菇头学渣少年」：日常 / 欢呼 / 晕菜 三态 */
export default function Mascot({ variant = 'normal', size = 120, className = '' }: MascotProps) {
  return (
    <View className={`mascot ${className}`} style={{ width: `${size}px`, height: `${size}px` }}>
      <Image className='mascot__img' src={SOURCES[variant]} mode='aspectFit' />
    </View>
  )
}
