import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import './index.scss'

interface BackButtonProps {
  className?: string
  onClick?: () => void
}

/** 返回按钮：圆角方框 + 箭头，默认行为为返回上一页 */
export default function BackButton({ className = '', onClick }: BackButtonProps) {
  const handleClick = () => {
    if (onClick) {
      onClick()
      return
    }
    Taro.navigateBack()
  }

  return (
    <View className={`back-btn ${className}`} hoverClass='back-btn--active' onClick={handleClick}>
      <Text className='back-btn__arrow'>←</Text>
    </View>
  )
}
