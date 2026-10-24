import { Info } from 'lucide-react'
import { useId, useState, type KeyboardEvent } from 'react'

import { GLOSSARY, type GlossaryKey } from '../lib/glossary'

/** A small "i" button that explains a term. Opens on hover, focus, or tap; closes on leave, blur, or Escape. */
export function InfoTip({ term, label }: { term: GlossaryKey; label: string }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') setOpen(false)
  }
  return (
    <span
      className="infotip"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onKeyDown={onKeyDown}
    >
      <button
        type="button"
        className="infotip__button"
        aria-label={`What does "${label}" mean?`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        <Info aria-hidden="true" size={14} />
      </button>
      {open && (
        <span role="tooltip" id={id} className="infotip__bubble">
          {GLOSSARY[term]}
        </span>
      )}
    </span>
  )
}
