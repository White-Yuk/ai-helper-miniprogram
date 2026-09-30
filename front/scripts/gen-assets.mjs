/**
 * 静态资源生成脚本：把 scripts/assets-src/*.svg 渲染为 3x 分辨率 PNG
 * 用途：微信小程序不支持内联 SVG，统一转为 PNG 静态资源（保证与设计稿一致）
 *
 * 使用：npm run gen:assets
 */
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join, basename } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Resvg } from '@resvg/resvg-js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SRC_DIR = join(__dirname, 'assets-src')
const OUT_DIR = join(__dirname, '..', 'src', 'assets')
const SCALE = 3 // 3 倍分辨率，满足高清屏

mkdirSync(OUT_DIR, { recursive: true })

const files = readdirSync(SRC_DIR).filter((f) => f.endsWith('.svg'))
if (files.length === 0) {
  console.error('assets-src 中没有找到 svg 文件')
  process.exit(1)
}

for (const file of files) {
  const svgText = readFileSync(join(SRC_DIR, file), 'utf-8')
  const match = svgText.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/)
  const width = match ? parseFloat(match[1]) : 120

  const resvg = new Resvg(svgText, {
    fitTo: { mode: 'width', value: Math.round(width * SCALE) },
    background: undefined, // 透明背景
  })
  const png = resvg.render().asPng()
  const outName = `${basename(file, '.svg')}.png`
  writeFileSync(join(OUT_DIR, outName), png)
  console.log(`OK ${file} -> ${outName} (${(png.length / 1024).toFixed(1)}KB)`)
}

console.log(`\n完成：共生成 ${files.length} 个 PNG 到 src/assets/`)
