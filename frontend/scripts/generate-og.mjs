import satori from 'satori'
import { Resvg } from '@resvg/resvg-js'
import matter from 'gray-matter'
import pkg from 'fast-glob'
const { glob } = pkg
import { createElement as h } from 'react'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const WIDTH = 1200
const HEIGHT = 630
const DEFAULT_LANG = 'en'

const fontData = fs.readFileSync(path.join(ROOT, 'assets/fonts/sans-regular.ttf'))
const fallbackBg = ['og-bg.jpg', 'og-bg.jpeg', 'og-bg.png']
  .map(f => path.join(ROOT, 'assets/images', f))
  .find(f => fs.existsSync(f))

function toDataUrl(filePath) {
  const ext = path.extname(filePath).slice(1).toLowerCase()
  const mime = ext === 'png' ? 'image/png' : 'image/jpeg'
  return `data:${mime};base64,${fs.readFileSync(filePath).toString('base64')}`
}

function resolveOutputPath(contentFile) {
  const rel = path.relative(path.join(ROOT, 'content'), contentFile)
  const parts = rel.split(path.sep)
  const match = parts.at(-1).match(/(?:index|_index)\.(\w+)\.md$/)
  if (!match) return null
  const lang = match[1]
  const dir = parts.slice(0, -1).join('/')
  const slug = dir || 'index'
  const prefix = lang === DEFAULT_LANG ? '' : `${lang}/`
  return `static/og/${prefix}${slug}.png`
}

function findFeaturedImage(contentFile) {
  const dir = path.dirname(contentFile)
  for (const ext of ['jpg', 'jpeg', 'png', 'webp']) {
    const p = path.join(dir, `featured-image.${ext}`)
    if (fs.existsSync(p)) return p
  }
  return null
}

async function buildOgImage({ title, description, bgPath }) {
  const bgDataUrl = toDataUrl(bgPath || fallbackBg)

  const el = h('div', {
    style: {
      width: WIDTH, height: HEIGHT,
      display: 'flex', position: 'relative',
      fontFamily: 'Inter', overflow: 'hidden',
    },
  },
    h('img', {
      src: bgDataUrl,
      style: { position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover' },
    }),
    h('div', {
      style: {
        position: 'absolute', bottom: 0, left: 0, right: 0, height: '75%',
        background: 'linear-gradient(to top, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.5) 55%, transparent 100%)',
      },
    }),
    h('div', {
      style: {
        position: 'absolute', top: 36, right: 46,
        backgroundColor: 'rgba(0,0,0,0.45)',
        borderRadius: 20,
        padding: '6px 16px',
        color: 'white',
        fontSize: 18, letterSpacing: '0.03em',
      },
    }, 'aws-sensei.cloud'),
    h('div', {
      style: {
        position: 'absolute', bottom: 55, left: 60, right: 60,
        display: 'flex', flexDirection: 'column', gap: '14px',
      },
    },
      h('div', {
        style: {
          color: 'white',
          fontSize: 50, fontWeight: 700, lineHeight: 1.2,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitBoxOrient: 'vertical',
          WebkitLineClamp: 2,
        },
      }, title || ''),
      description && h('div', {
        style: {
          color: 'rgba(255,255,255,0.72)',
          fontSize: 22, lineHeight: 1.5,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitBoxOrient: 'vertical',
          WebkitLineClamp: 2,
        },
      }, description),
    ),
  )

  const svg = await satori(el, {
    width: WIDTH, height: HEIGHT,
    fonts: [
      { name: 'Inter', data: fontData, weight: 400, style: 'normal' },
      { name: 'Inter', data: fontData, weight: 700, style: 'normal' },
    ],
  })

  return new Resvg(svg, { fitTo: { mode: 'width', value: WIDTH } }).render().asPng()
}

async function main() {
  const files = await glob('content/**/{index,_index}.*.md', { cwd: ROOT, absolute: true })
  let count = 0

  for (const file of files) {
    const { data } = matter(fs.readFileSync(file, 'utf8'))
    if (data.draft) continue

    const outputPath = resolveOutputPath(file)
    if (!outputPath) continue

    const absOut = path.join(ROOT, outputPath)
    fs.mkdirSync(path.dirname(absOut), { recursive: true })

    const png = await buildOgImage({
      title: data.title,
      description: data.description,
      bgPath: findFeaturedImage(file),
    })

    fs.writeFileSync(absOut, png)
    console.log(`✓  ${outputPath}`)
    count++
  }

  console.log(`\n${count} OG images generated`)
}

main().catch(e => { console.error(e); process.exit(1) })
