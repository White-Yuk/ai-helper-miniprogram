import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import { ensureLogin } from './services/auth'

import './styles/global.scss'

function App({ children }: PropsWithChildren<any>) {
  useLaunch(() => {
    // 启动即静默登录（不阻塞页面渲染；失败时下次请求会自动重试）
    void ensureLogin()
  })

  // children 是将要会渲染的页面
  return children
}
  


export default App
