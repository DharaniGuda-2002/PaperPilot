// Verifies WCAG 2.2 contrast for the foreground/background token pairs the UI uses.
// Reads real values from src/styles/tokens.css. Exit code 1 on any failure.
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/styles/tokens.css', import.meta.url), 'utf8')
const tokens = Object.fromEntries(
  [...css.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map(([, name, hex]) => [name, hex]),
)

// [foreground, background, minimum ratio, where it is used]
const TEXT = 4.5
const NON_TEXT = 3
const PAIRS = [
  ['color-success', 'color-bg-surface', TEXT, 'landing evidence card check list'],
  ['color-text-primary', 'color-warning-bg', TEXT, 'highlighted numbers in the landing quote'],
  ['color-text-inverse', 'color-primary', TEXT, 'step numbers on the landing page'],
  ['color-text-inverse', 'color-primary', TEXT, 'primary button and send arrow'],
  ['color-text-inverse', 'color-primary-hover', TEXT, 'primary button hover'],
  ['color-brand-700', 'color-bg-selected', TEXT, 'active sidebar link'],
  ['color-brand-700', 'color-bg-page', TEXT, 'links on the page background'],
  ['color-primary', 'color-bg-surface', NON_TEXT, 'top-bar search focus and meter bars'],
  ['color-text-muted', 'color-bg-surface', TEXT, 'top-bar search border and placeholder'],
  ['color-text-secondary', 'color-bg-page', TEXT, 'subtitles on the page background'],
  ['color-text-primary', 'color-bg-page', TEXT, 'body text on page'],
  ['color-text-primary', 'color-bg-surface', TEXT, 'body text on cards'],
  ['color-text-secondary', 'color-bg-surface', TEXT, 'secondary text'],
  ['color-text-secondary', 'color-bg-subtle', TEXT, 'neutral badge'],
  ['color-text-muted', 'color-bg-surface', TEXT, 'hints and metadata'],
  ['color-text-secondary', 'color-bg-page', TEXT, 'loading/empty text (.muted) on page'],
  ['color-text-secondary', 'color-bg-subtle', TEXT, 'disabled button label'],
  ['color-brand-900', 'color-bg-surface', TEXT, 'headings'],
  ['color-brand-700', 'color-bg-surface', TEXT, 'links'],
  ['color-brand-900', 'color-bg-surface', TEXT, 'link hover'],
  ['color-brand-600', 'color-bg-surface', NON_TEXT, 'meter bar and stepper outline'],
  ['color-text-inverse', 'color-brand-600', NON_TEXT, 'stepper check mark on done node'],
  ['color-text-secondary', 'color-brand-100', TEXT, 'empty comparison cell (hatch)'],
  ['color-brand-900', 'color-bg-selected', TEXT, 'active stepper node'],
  ['color-text-inverse', 'color-brand-900', TEXT, 'primary button'],
  ['color-text-inverse', 'color-brand-700', TEXT, 'primary button hover'],
  ['color-info', 'color-info-bg', TEXT, 'info badge / notice'],
  ['color-success', 'color-success-bg', TEXT, 'success badge'],
  ['color-warning', 'color-warning-bg', TEXT, 'warning badge'],
  ['color-error', 'color-error-bg', TEXT, 'error badge / alert'],
  ['color-error', 'color-bg-surface', TEXT, 'field error text, stage error detail'],
  ['color-warning', 'color-warning-bg', TEXT, 'warning notice'],
  ['color-success', 'color-bg-surface', NON_TEXT, 'completed stage icon'],
  ['color-warning', 'color-bg-surface', TEXT, 'retrying stage icon, finding warning text, matrix warnings'],
  ['color-text-primary', 'color-brand-50', TEXT, 'inspector quotation'],
  ['color-text-secondary', 'color-bg-subtle', TEXT, 'table header'],
  ['color-text-primary', 'color-brand-50', TEXT, 'open evidence paper background'],
  ['color-brand-900', 'color-brand-50', TEXT, 'evidence paper title when open'],
  ['color-info', 'color-bg-surface', NON_TEXT, 'running stage icon'],
  ['color-focus-ring', 'color-bg-surface', NON_TEXT, 'focus ring on cards'],
  ['color-focus-ring', 'color-bg-page', NON_TEXT, 'focus ring on page'],
  ['color-text-muted', 'color-bg-surface', NON_TEXT, 'text input / secondary button boundary'],
  ['color-brand-700', 'color-brand-50', TEXT, 'example chip'],
  ['color-brand-700', 'color-brand-100', TEXT, 'example chip hover'],
  ['color-brand-900', 'color-brand-100', TEXT, 'active sidebar link, step numbers'],
  ['color-text-secondary', 'color-brand-50', TEXT, 'sidebar link hover'],
  ['color-text-secondary', 'color-brand-50', TEXT, 'row metadata on hover'],
  ['color-brand-700', 'color-brand-50', TEXT, 'row title on hover'],
  ['color-text-secondary', 'color-bg-subtle', TEXT, 'sidebar preview note'],
  ['color-text-secondary', 'color-bg-page', TEXT, 'landing nav and lead text'],
  ['color-brand-700', 'color-bg-page', TEXT, 'hero accent text on page'],
  ['color-brand-900', 'color-bg-page', TEXT, 'page titles on page'],
  // Not checked: border-default/border-strong are decorative dividers (no 3:1 requirement).
]

function luminance(hex) {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const [r, g, b] = channels.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

let failures = 0
for (const [fg, bg, min, use] of PAIRS) {
  if (!tokens[fg] || !tokens[bg]) throw new Error(`Unknown token in pair ${fg} / ${bg}`)
  const r = ratio(tokens[fg], tokens[bg])
  const ok = r >= min
  if (!ok) failures++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${r.toFixed(2).padStart(5)}:1 (min ${min})  ${fg} on ${bg}  — ${use}`)
}
process.exit(failures ? 1 : 0)
