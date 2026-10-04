import { useEffect, useState } from 'react'
import { View, Text, Input, Image, Button } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import Mascot from '../../components/Mascot'
import InkButton from '../../components/InkButton'
import { resolveAssetUrl, updateProfile, uploadAvatar } from '../../services/api'
import { useUserStore } from '../../store/userStore'
import type { ProfileUpdateRequest } from '../../types'

import './index.scss'

/**
 * 编辑资料（阶段 7，原型未覆盖，按设计系统自绘）：
 * - 头像：小程序端使用官方 chooseAvatar 能力；H5 调试用 chooseImage 兜底
 * - 昵称：小程序端使用官方 nickname 输入框；H5 用普通输入框
 */
export default function ProfileEdit() {
  const me = useUserStore((state) => state.me)
  const loadMe = useUserStore((state) => state.loadMe)

  const [nickname, setNickname] = useState('')
  const [avatarFile, setAvatarFile] = useState('') // 新选择的本地临时路径（保存时才上传）
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!me) {
      loadMe().catch(() => {
        // 静默失败：页面展示默认值
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // me 就绪后初始化昵称（仅当用户未编辑过）
  useEffect(() => {
    if (me) {
      setNickname((prev) => prev || me.nickname)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me])

  const chooseAvatarWeapp = (event: { detail?: { avatarUrl?: string } }) => {
    const url = event.detail?.avatarUrl
    if (url) setAvatarFile(url)
  }

  const chooseAvatarH5 = async () => {
    try {
      const res = await Taro.chooseImage({ count: 1 })
      const path = res.tempFilePaths?.[0]
      if (path) setAvatarFile(path)
    } catch {
      // 用户取消选择
    }
  }

  const avatarSrc = avatarFile || (me?.avatar ? resolveAssetUrl(me.avatar) : '')

  const save = async () => {
    const trimmed = nickname.trim()
    if (!trimmed) {
      Taro.showToast({ title: '昵称不能为空', icon: 'none' })
      return
    }
    if (trimmed.length > 32) {
      Taro.showToast({ title: '昵称最多 32 个字符', icon: 'none' })
      return
    }

    setSaving(true)
    try {
      let avatarUrl: string | undefined
      if (avatarFile) {
        const uploaded = await uploadAvatar(avatarFile)
        avatarUrl = uploaded.url
      }
      const payload: ProfileUpdateRequest = { nickname: trimmed }
      if (avatarUrl) payload.avatar = avatarUrl
      await updateProfile(payload)
      await loadMe()
      Taro.showToast({ title: '已保存 ✅', icon: 'none' })
      setTimeout(() => Taro.navigateBack(), 800)
    } catch (error) {
      Taro.showToast({ title: (error as Error)?.message || '保存失败，请重试', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <PageShell className='profile-edit-page'>
      {/* 顶栏 */}
      <View className='profile-edit-top'>
        <BackButton />
        <Text className='profile-edit-top__title'>编辑资料</Text>
      </View>

      {/* 头像选择 */}
      <View className='edit-avatar'>
        {process.env.TARO_ENV === 'weapp' ? (
          <Button className='edit-avatar__btn' openType='chooseAvatar' onChooseAvatar={chooseAvatarWeapp}>
            {avatarSrc ? (
              <Image className='edit-avatar__img' src={avatarSrc} mode='aspectFill' />
            ) : (
              <Mascot size={84} />
            )}
          </Button>
        ) : (
          <View className='edit-avatar__btn' onClick={chooseAvatarH5}>
            {avatarSrc ? (
              <Image className='edit-avatar__img' src={avatarSrc} mode='aspectFill' />
            ) : (
              <Mascot size={84} />
            )}
          </View>
        )}
        <Text className='edit-avatar__tip'>点击头像更换（支持 JPG / PNG，2MB 以内）</Text>
      </View>

      {/* 昵称输入（外观由外层 View 容器保证，input 本体保持最简，规避原生组件样式差异） */}
      <View className='edit-field'>
        <Text className='edit-field__label'>昵称</Text>
        <View className='edit-field__box'>
          <Input
            className='edit-field__input'
            type={process.env.TARO_ENV === 'weapp' ? 'nickname' : 'text'}
            value={nickname}
            maxlength={32}
            alwaysEmbed
            placeholder='给自己取个响亮的名字'
            placeholderClass='edit-field__placeholder'
            onInput={(event) => setNickname(event.detail.value)}
          />
          <Text className='edit-field__count'>{nickname.length}/32</Text>
        </View>
      </View>

      <View className='edit-tip'>
        <Text>💡 昵称与头像会展示在你的个人中心，不设置也能正常闯关</Text>
      </View>

      <View className='edit-foot'>
        <InkButton type='primary' size='large' disabled={saving} onClick={save}>
          {saving ? '保存中…' : '保存资料'}
        </InkButton>
      </View>
    </PageShell>
  )
}
