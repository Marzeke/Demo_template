import type { AgentStatus } from '../types'

// 12 x 12 pixel critters. Letters are palette slots; '.' is transparent.
//   B body  D body shade  E eye  H hat  h hat shade  A accent  a accent 2  P flag pole  S sparkle
const SIZE = 12

const BODY = [
  '............',
  '............',
  '............',
  '..BBBBBBBB..',
  '.BBBBBBBBBB.',
  '.BBEBBBBEBB.',
  'BBBBBBBBBBBB',
  'BBBBBBBBBBBB',
  '.BBBBBBBBBB.',
  '.DDDDDDDDDD.',
]

const LEGS: [string, string][] = [
  ['..B.B..B.B..', '..D.D..D.D..'],
  ['.B.B....B.B.', '.D.D....D.D.'],
]

// Drawn over the top rows of the body, one per effort tier.
const HATS: Record<string, string[]> = {
  // beanie with a flag on a pole
  heavy: [
    '..........PA',
    '...HHHHH..PA',
    '..HhHhHhH.P.',
    '..HHHHHHHHP.',
  ],
  // hard hat with a wide brim
  careful: [
    '............',
    '....HHHH....',
    '...HHHHHH...',
    '..HHHHHHHH..',
    '.hhhhhhhhhh.',
  ],
  // cap with goggles and a peak to the right
  medium: [
    '............',
    '....HHHH....',
    '...HHHHHH...',
    '..AAaAAaAAhh',
  ],
  // small cap with a chequered flag
  light: [
    '..........PA',
    '..........Pa',
    '...HHHHH..P.',
    '..HHHHHHHhP.',
  ],
  custom: [
    '............',
    '............',
    '...HHHHHH...',
    '..HHHHHHHH..',
  ],
}

const SPARKLE = [
  [2, 0],
  [3, 0],
  [1, 1],
] as const

export type MascotTheme = 'screenshot' | 'claude'

type Palette = { B: number; D: number; E: number; P: number; S: number; hats: Record<string, { H: number; h: number; A: number; a: number }> }

export const THEMES: Record<MascotTheme, Palette> = {
  // The colours of the reference screenshot: coral critters, tier-coloured hats.
  screenshot: {
    B: 0xe8775a,
    D: 0xc4583e,
    E: 0x2b1b17,
    P: 0xd9d9d9,
    S: 0xf5f5f5,
    hats: {
      heavy: { H: 0x7a4a2e, h: 0x5c3420, A: 0x4b87e0, a: 0x4b87e0 },
      careful: { H: 0xf2c14e, h: 0xd49a2a, A: 0xf2c14e, a: 0xf2c14e },
      medium: { H: 0x9aa0a6, h: 0x6e747a, A: 0x3d7bd9, a: 0x1f2a36 },
      light: { H: 0x2e8b57, h: 0x1f6b40, A: 0xffffff, a: 0x1a1a1a },
      custom: { H: 0x9aa0a6, h: 0x6e747a, A: 0x9aa0a6, a: 0x9aa0a6 },
    },
  },
  // Claude's palette: the terracotta of Claude Code's own mascot, with Anthropic's accent colours.
  claude: {
    B: 0xd97757,
    D: 0xb85c3e,
    E: 0x141413,
    P: 0xb0aea5,
    S: 0xfaf9f5,
    hats: {
      heavy: { H: 0x141413, h: 0x3d3d3a, A: 0xd97757, a: 0xd97757 },
      careful: { H: 0xd4a27f, h: 0xb0835f, A: 0xd4a27f, a: 0xd4a27f },
      medium: { H: 0xb0aea5, h: 0x87867f, A: 0x6a9bcc, a: 0x141413 },
      light: { H: 0x788c5d, h: 0x5c6e45, A: 0xfaf9f5, a: 0x141413 },
      custom: { H: 0xb0aea5, h: 0x87867f, A: 0xb0aea5, a: 0xb0aea5 },
    },
  },
}

const TRANSPARENT = -1

// Halfway to grey: how a stopped or failed agent fades.
const mute = (rgb: number): number => {
  const ch = (shift: number) => (rgb >> shift) & 0xff
  const mix = (c: number) => Math.round(c * 0.45 + 0x60 * 0.55)

  return (mix(ch(16)) << 16) | (mix(ch(8)) << 8) | mix(ch(0))
}

/** The sprite as a 12 x 12 grid of 0xRRGGBB colours, -1 where transparent. */
export const spritePixels = (tier: string, status: AgentStatus, frame: number, theme: MascotTheme): number[][] => {
  const palette = THEMES[theme]
  const hatColours = palette.hats[tier] ?? palette.hats.custom!
  const rows = [...BODY, ...(LEGS[status === 'running' ? frame % 2 : 0] ?? LEGS[0]!)].map(r => r.split(''))
  const hat = HATS[tier] ?? HATS.custom!
  hat.forEach((line, y) =>
    line.split('').forEach((ch, x) => {
      if (ch !== '.') rows[y]![x] = ch
    }),
  )
  if (status === 'completed') for (const [y, x] of SPARKLE) rows[y]![x] = 'S'

  const colour: Record<string, number> = {
    B: palette.B,
    D: palette.D,
    E: palette.E,
    P: palette.P,
    S: palette.S,
    ...hatColours,
  }
  const isFaded = status === 'failed' || status === 'stopped'

  return rows.map(r =>
    r.map(ch => {
      const c = colour[ch]
      if (c === undefined) return TRANSPARENT

      return isFaded ? mute(c) : c
    }),
  )
}

const DEFAULT_COLOUR = 0x01000000
const UPPER_HALF = 0x2580
const LOWER_HALF = 0x2584
const SPACE = 0x20

/** Terminal cells for a Raster: two pixel rows per cell with half blocks, base64 of u32 triplets. */
export const rasterCells = (pixels: number[][]): { columns: number; rows: number; cells: string } => {
  const columns = SIZE
  const rows = Math.ceil(pixels.length / 2)
  const words = new Uint32Array(columns * rows * 3)
  for (let r = 0; r < rows; r++) {
    for (let x = 0; x < columns; x++) {
      const top = pixels[r * 2]?.[x] ?? TRANSPARENT
      const bottom = pixels[r * 2 + 1]?.[x] ?? TRANSPARENT
      const i = (r * columns + x) * 3
      if (top === TRANSPARENT && bottom === TRANSPARENT) {
        words.set([SPACE, DEFAULT_COLOUR, DEFAULT_COLOUR], i)
      } else if (top === TRANSPARENT) {
        words.set([LOWER_HALF, bottom, DEFAULT_COLOUR], i)
      } else {
        words.set([UPPER_HALF, top, bottom === TRANSPARENT ? DEFAULT_COLOUR : bottom], i)
      }
    }
  }
  const bytes = new Uint8Array(words.buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]!)

  return { columns, rows, cells: btoa(binary) }
}

const hex = (rgb: number): string => `#${rgb.toString(16).padStart(6, '0')}`

/** The sprite as an SVG of square pixels, for the desktop app and VS Code. */
export const spriteSvg = (pixels: number[][], scale = 3): string => {
  const size = SIZE * scale
  const rects: string[] = []
  pixels.forEach((row, y) =>
    row.forEach((c, x) => {
      if (c !== TRANSPARENT) {
        rects.push(`<rect x="${x * scale}" y="${y * scale}" width="${scale}" height="${scale}" fill="${hex(c)}"/>`)
      }
    }),
  )

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" shape-rendering="crispEdges">${rects.join('')}</svg>`
}
