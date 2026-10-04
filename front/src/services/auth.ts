/**
 * 登录服务：静默登录（无授权弹窗）。
 *
 * 流程：
 * 1. 小程序端：Taro.login() 拿 code → 后端 /auth/login 换 token
 * 2. H5 / 微信登录不可用时：后端 /auth/dev-login（开发态模拟登录，需后端开启 AUTH_MOCK_ENABLED）
 */
import Taro from '@tarojs/taro'

import { devLogin, getToken, loginWithCode, onUnauthorized, registerEnsureLogin, setToken } from './api'

const DEVICE_KEY = 'device_id'

/** 开发态设备标识：本地持久化，保证同一设备始终登录为同一用户。 */
function getDeviceId(): string {
  let deviceId = ''
  try {
    deviceId = Taro.getStorageSync(DEVICE_KEY) || ''
  } catch {
    deviceId = ''
  }
  if (!deviceId) {
    deviceId = `dev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
    try {
      Taro.setStorageSync(DEVICE_KEY, deviceId)
    } catch {
      // 忽略存储异常
    }
  }
  return deviceId
}

let loginPromise: Promise<void> | null = null

/** 确保已登录：已有 token 直接返回；并发调用共享同一次登录请求。 */
export function ensureLogin(force = false): Promise<void> {
  if (!force && getToken()) {
    return Promise.resolve()
  }
  if (!loginPromise) {
    loginPromise = doLogin().finally(() => {
      loginPromise = null
    })
  }
  return loginPromise
}

async function doLogin(): Promise<void> {
  // 小程序端：真实微信静默登录
  if (process.env.TARO_ENV === 'weapp') {
    try {
      const res = await Taro.login()
      if (res.code) {
        const data = await loginWithCode(res.code)
        setToken(data.token)
        return
      }
    } catch (error) {
      console.warn('[auth] 微信登录失败，尝试开发态模拟登录', error)
    }
  }

  // H5 调试 / 微信登录不可用：开发态模拟登录（后端未开启时静默失败）
  try {
    const data = await devLogin(getDeviceId())
    setToken(data.token)
  } catch (error) {
    console.warn('[auth] 开发态登录失败（后端可能未开启 AUTH_MOCK_ENABLED）', error)
  }
}

// 登录失效时自动重新登录（由 api 层在收到 4003 时触发）
onUnauthorized(() => {
  void ensureLogin(true)
})

// 提供给请求层：无 token / token 失效时先确保完成登录（重登成功后请求自动重试一次）
registerEnsureLogin(ensureLogin)
