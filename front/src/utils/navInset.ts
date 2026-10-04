import Taro from '@tarojs/taro'

/**
 * 自定义导航右侧避让值（px）：让位于顶栏右上角的内容避开微信胶囊按钮。
 *
 * - 小程序端：屏幕右缘 - 胶囊左缘 + 安全间距（不同机型 / 基础库动态计算）
 * - H5 端：没有系统胶囊，返回 0
 * - 获取失败：返回保守兜底值 104（常见机型所需避让宽度）
 */
export function getCapsuleInset(): number {
  if (process.env.TARO_ENV !== 'weapp') return 0
  try {
    const rect = Taro.getMenuButtonBoundingClientRect()
    const info = Taro.getWindowInfo()
    if (rect && rect.left > 0 && info.windowWidth > 0) {
      return info.windowWidth - rect.left + 8
    }
  } catch {
    // 获取胶囊信息失败时走兜底值
  }
  return 104
}
