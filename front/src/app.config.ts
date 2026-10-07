export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/profile/index',
    'pages/profile-edit/index',
    'pages/generating/index',
    'pages/quiz/index',
    'pages/result/index',
    'pages/report/index',
    'pages/mastery/index',
    'pages/stats/index',
    'pages/wrongbook/index',
    'pages/redo/index',
    'pages/library/index',
    'pages/poster/index'
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationStyle: 'custom',
    backgroundColor: '#FFF6E3',
    navigationBarBackgroundColor: '#FFF6E3',
    navigationBarTitleText: 'AI学习助手',
    navigationBarTextStyle: 'black'
  }
})
