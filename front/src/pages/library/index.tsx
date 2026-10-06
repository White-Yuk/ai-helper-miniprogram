import { useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'

import PageShell from '../../components/PageShell'
import BackButton from '../../components/BackButton'
import InkButton from '../../components/InkButton'
import Mascot from '../../components/Mascot'
import { ApiError, deleteDocument, listDocuments, uploadDocument } from '../../services/api'
import type { DocItem } from '../../types'

import './index.scss'

/** 前端预校验（与后端一致：≤20MB；后端仍做权威校验） */
const MAX_SIZE_MB = 20
const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'md']

const STATUS_META: Record<DocItem['status'], { label: string; tone: 'doing' | 'ok' | 'fail' }> = {
  pending: { label: '排队中', tone: 'doing' },
  processing: { label: '处理中', tone: 'doing' },
  ready: { label: '已就绪', tone: 'ok' },
  failed: { label: '处理失败', tone: 'fail' },
}

/** 字节 → 可读大小 */
function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)}KB`
  return `${bytes}B`
}

/** 步骤流 → 当前处理描述（轮询展示） */
function describeProcessing(item: DocItem): string {
  if (item.steps.length === 0) return '排队中，等待处理…'
  const doing = item.steps.find((step) => step.state === 'doing')
  if (doing) return doing.detail ? `${doing.label}：${doing.detail}` : doing.label
  const done = [...item.steps].reverse().find((step) => step.state === 'done')
  return done?.detail || '正在处理…'
}

export default function Library() {
  const [docs, setDocs] = useState<DocItem[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const aliveRef = useRef(true)

  const loadList = async () => {
    try {
      const data = await listDocuments()
      if (aliveRef.current) setDocs(data.documents)
    } catch (error) {
      if (aliveRef.current && error instanceof ApiError) {
        Taro.showToast({ title: error.message, icon: 'none' })
      }
    } finally {
      if (aliveRef.current) setLoading(false)
    }
  }

  useEffect(() => {
    aliveRef.current = true
    loadList()
    return () => {
      aliveRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 有排队中 / 处理中文档时轮询（2s 一查；无进行中文档即停；页面卸载即停）
  useEffect(() => {
    const busy = docs.some((doc) => doc.status === 'pending' || doc.status === 'processing')
    if (!busy || !aliveRef.current) return
    const timer = setTimeout(() => {
      if (aliveRef.current) loadList()
    }, 2000)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docs])

  const doUpload = async (payload: { filePath?: string; file?: File; filename: string; size: number }) => {
    const ext = payload.filename.slice(payload.filename.lastIndexOf('.') + 1).toLowerCase()
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      Taro.showToast({ title: '仅支持 PDF / Word(.docx) / Markdown(.md)', icon: 'none' })
      return
    }
    if (payload.size > MAX_SIZE_MB * 1024 * 1024) {
      Taro.showToast({ title: `文件不能超过 ${MAX_SIZE_MB}MB`, icon: 'none' })
      return
    }

    setUploading(true)
    try {
      await uploadDocument({ filePath: payload.filePath, file: payload.file })
      Taro.showToast({ title: '已开始处理，稍候自动刷新', icon: 'none' })
      await loadList()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '上传失败，请重试'
      Taro.showToast({ title: message, icon: 'none' })
    } finally {
      if (aliveRef.current) setUploading(false)
    }
  }

  const chooseAndUpload = async () => {
    if (uploading) return

    // H5：浏览器直接选择本地文件（动态创建 input，避免跨端标签差异）
    if (process.env.TARO_ENV === 'h5') {
      const file = await new Promise<File | null>((resolve) => {
        const input = document.createElement('input')
        input.type = 'file'
        input.accept = '.pdf,.docx,.md'
        input.onchange = () => resolve(input.files?.[0] ?? null)
        input.click()
      })
      if (!file) return
      await doUpload({ file, filename: file.name, size: file.size })
      return
    }

    // 微信端：从聊天记录选择文件（平台限制）
    try {
      const res = await Taro.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: ALLOWED_EXTENSIONS,
      })
      const picked = res.tempFiles?.[0]
      if (!picked) return
      await doUpload({ filePath: picked.path, filename: picked.name, size: picked.size })
    } catch {
      // 用户取消选择：静默
    }
  }

  const removeDoc = async (item: DocItem) => {
    const res = await Taro.showModal({
      title: '删除资料',
      content: `确定删除「${item.filename}」吗？删除后不再参与出题检索。`,
      confirmText: '删除',
      confirmColor: '#E8432E',
    })
    if (!res.confirm) return
    try {
      await deleteDocument(item.doc_id)
      Taro.showToast({ title: '已删除', icon: 'none' })
      await loadList()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '删除失败，请重试'
      Taro.showToast({ title: message, icon: 'none' })
    }
  }

  return (
    <PageShell className='library-page'>
      <View className='library-top'>
        <BackButton />
        <Text className='library-top__title'>我的资料库</Text>
      </View>

      <View className='library-intro'>
        <Text className='library-intro__text'>
          上传你的学习资料（PDF / Word / Markdown），出题时 AI 会优先检索你的资料 📚
        </Text>
      </View>

      <InkButton type='primary' size='large' onClick={chooseAndUpload}>
        {uploading ? '⏳ 上传中…' : '📎 上传资料'}
      </InkButton>

      {loading ? (
        <View className='library-status'>
          <Mascot size={120} />
          <Text className='library-status__text'>正在加载…</Text>
        </View>
      ) : docs.length === 0 ? (
        <View className='library-empty'>
          <Mascot size={120} />
          <Text className='library-empty__title'>还没有资料</Text>
          <Text className='library-empty__desc'>
            微信端请先把文件发到「文件传输助手」，再点上方按钮从聊天记录选择；浏览器端可直接选文件
          </Text>
        </View>
      ) : (
        <View className='library-list'>
          {docs.map((item) => {
            const meta = STATUS_META[item.status]
            return (
              <View key={item.doc_id} className='doc-card'>
                <View className='doc-card__head'>
                  <Text className='doc-card__name'>{item.filename}</Text>
                  <Text className={`doc-card__badge doc-card__badge--${meta.tone}`}>{meta.label}</Text>
                </View>
                <View className='doc-card__meta'>
                  <Text className='doc-card__meta-text'>
                    {item.file_type.toUpperCase()} · {formatSize(item.file_size)}
                  </Text>
                  <Text className='doc-card__delete' onClick={() => removeDoc(item)}>
                    删除
                  </Text>
                </View>
                {item.status === 'pending' || item.status === 'processing' ? (
                  <Text className='doc-card__progress'>{describeProcessing(item)}</Text>
                ) : null}
                {item.status === 'ready' ? (
                  <Text className='doc-card__progress'>
                    共 {item.chunk_count ?? 0} 个知识块，可被出题检索
                  </Text>
                ) : null}
                {item.status === 'failed' ? (
                  <Text className='doc-card__error'>{item.error_message || '处理失败，请删除后重试'}</Text>
                ) : null}
              </View>
            )
          })}
        </View>
      )}
    </PageShell>
  )
}
