import { PropsWithChildren, ReactNode } from 'react'
import { View } from '@tarojs/components'

import './index.scss'

interface InkButtonProps {
  /** primary 红底白字 / secondary 黄底黑字 / ghost 白底黑字 */
  type?: 'primary' | 'secondary' | 'ghost'
  size?: 'normal' | 'large'
  disabled?: boolean
  className?: string
  onClick?: () => void
}

/** 漫画描边按钮：粗描边 + 硬阴影，按压时位移 */
export default function InkButton({
  type = 'primary',
  size = 'normal',
  disabled = false,
  className = '',
  onClick,
  children,
}: PropsWithChildren<InkButtonProps>) {
  return (
    <View
      className={`ink-btn ink-btn--${type} ink-btn--${size} ${disabled ? 'ink-btn--disabled' : ''} ${className}`}
      hoverClass={disabled ? 'none' : 'ink-btn--active'}
      hoverStayTime={80}
      onClick={disabled ? undefined : onClick}
    >
      {children as ReactNode}
    </View>
  )
}
