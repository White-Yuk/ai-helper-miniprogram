import { View, Text, Input } from '@tarojs/components'

import type { Question } from '../../types'

import './index.scss'

export interface QuestionPanelProps {
  question: Question
  /** answering = 作答中；feedback = 已提交（显示对错标记） */
  phase: 'answering' | 'feedback'
  selected: string[]
  fillInputs: string[]
  /** 单选（选择即提交）/ 多选（切换勾选）点击项 */
  onClickOption: (key: string) => void
  /** 判断题点击 */
  onJudge: (value: '对' | '错') => void
  /** 填空输入（第 index 个空） */
  onFillInput: (index: number, value: string) => void
  /** 是否展示难度标签（错题重做页不展示） */
  showDifficulty?: boolean
}

/** 下划线占位：用于填空题干的渲染 */
function splitByBlank(stem: string): string[] {
  return stem.split('____')
}

/**
 * 答题面板：题干卡 + 选项 / 判断 / 填空作答区（闯关页与错题重做页共用）。
 * 状态与提交逻辑由父级管理，本组件只负责渲染与回调。
 */
export default function QuestionPanel({
  question,
  phase,
  selected,
  fillInputs,
  onClickOption,
  onJudge,
  onFillInput,
  showDifficulty = true,
}: QuestionPanelProps) {
  const isSelected = (key: string) => selected.includes(key)

  const optionClass = (key: string) => {
    if (phase === 'answering') {
      return isSelected(key) ? 'opt opt--selected' : 'opt'
    }
    if (question.answer.includes(key)) return 'opt opt--correct'
    if (isSelected(key)) return 'opt opt--wrong'
    return 'opt'
  }

  const judgeClass = (value: '对' | '错') => {
    if (phase === 'answering') return ''
    if (question.answer[0] === value) return 'judge-btn--correct'
    if (isSelected(value)) return 'judge-btn--wrong'
    return 'judge-btn--dim'
  }

  const renderStem = () => {
    if (question.type !== 'fill') {
      return <Text>{question.stem}</Text>
    }
    const parts = splitByBlank(question.stem)
    return (
      <Text>
        {parts.map((part, index) => (
          <Text key={`${part}-${index}`}>
            {part}
            {index < parts.length - 1 && (
              <Text className={phase === 'feedback' ? 'q-blank q-blank--done' : 'q-blank'}>
                {phase === 'feedback' ? question.answer[index] || '' : '     '}
              </Text>
            )}
          </Text>
        ))}
      </Text>
    )
  }

  return (
    <>
      {/* 题干卡 */}
      <View className='q-card'>
        <View className='q-card__flags'>
          <Text className={`q-tag q-tag--${question.type}`}>
            {question.type === 'single' && '单选'}
            {question.type === 'multiple' && '多选'}
            {question.type === 'judge' && '判断'}
            {question.type === 'fill' && '填空'}
          </Text>
          {showDifficulty && (
            <Text className='q-tag q-tag--level'>
              难度 ·
              {question.difficulty === 'easy' ? '易' : question.difficulty === 'medium' ? '中' : '难'}
            </Text>
          )}
        </View>
        <View className='q-card__stem'>{renderStem()}</View>
      </View>

      {/* 答题区：单选 / 多选 */}
      {(question.type === 'single' || question.type === 'multiple') && (
        <View className='opt-list'>
          {question.options.map((option) => (
            <View
              key={option.key}
              className={optionClass(option.key)}
              hoverClass='none'
              onClick={() => onClickOption(option.key)}
            >
              <View className={`opt__key ${question.type === 'multiple' ? 'opt__key--sq' : ''}`}>
                <Text>{question.type === 'multiple' && isSelected(option.key) ? '✓' : option.key}</Text>
              </View>
              <Text className='opt__text'>{option.text}</Text>
              {phase === 'feedback' && question.answer.includes(option.key) && <Text className='opt__flag'>✅</Text>}
              {phase === 'feedback' && question.type !== 'multiple' && isSelected(option.key) && !question.answer.includes(option.key) && (
                <Text className='opt__flag'>❌</Text>
              )}
            </View>
          ))}
        </View>
      )}

      {/* 答题区：判断 */}
      {question.type === 'judge' && (
        <View className='judge-row'>
          <View className={`judge-btn ${judgeClass('对')}`} onClick={() => phase === 'answering' && onJudge('对')}>
            <Text className='judge-btn__sym'>✓</Text>
            <Text className='judge-btn__label'>对</Text>
          </View>
          <View className={`judge-btn ${judgeClass('错')}`} onClick={() => phase === 'answering' && onJudge('错')}>
            <Text className='judge-btn__sym'>✗</Text>
            <Text className='judge-btn__label'>错</Text>
          </View>
        </View>
      )}

      {/* 答题区：填空 */}
      {question.type === 'fill' && (
        <View className='fill-card'>
          <View className='fill-card__label'>
            <Text>✍️ {phase === 'feedback' ? '你的答案' : '写下你的答案'}</Text>
          </View>
          {fillInputs.map((value, index) => (
            <View key={index} className='fill-card__row'>
              {fillInputs.length > 1 && <Text className='fill-card__index'>第 {index + 1} 空</Text>}
              <View className='fill-card__input-box'>
                <Input
                  className='fill-card__input'
                  value={value}
                  disabled={phase === 'feedback'}
                  alwaysEmbed
                  placeholder='填写答案…'
                  placeholderClass='fill-card__placeholder'
                  onInput={(event) => onFillInput(index, event.detail.value)}
                />
              </View>
            </View>
          ))}
        </View>
      )}
    </>
  )
}
