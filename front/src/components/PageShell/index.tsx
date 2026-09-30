import { PropsWithChildren } from 'react'
import { View } from '@tarojs/components'
import Taro from '@tarojs/taro'

import './index.scss'

interface PageShellProps {
  className?: string
}

/** 页面外壳：漫画纸背景 + 自定义导航的状态栏占位 */
export default function PageShell({ children, className = '' }: PropsWithChildren<PageShellProps>) {
  let statusBarHeight = 0
  try {
    statusBarHeight = Taro.getWindowInfo().statusBarHeight ?? 0
  } catch {
    statusBarHeight = 0
  }

  return (
    <View className={`page-shell ${className}`} style={{ paddingTop: `${statusBarHeight}px` }}>
      {children}
    </View>
  )
}
