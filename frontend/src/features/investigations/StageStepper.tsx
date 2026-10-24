import { Check, X } from 'lucide-react'

import type { StageSummary } from './stages'

export interface StepperStage {
  name: string
  state: StageSummary['state']
  tone: StageSummary['tone']
}

const STATE_TEXT: Record<StageSummary['state'], string> = {
  done: 'done',
  active: 'in progress',
  failed: 'failed',
  waiting: 'waiting',
  none: 'not started',
}

/** Compact progress strip: one numbered node per pipeline stage. */
export function StageStepper({ stages }: { stages: StepperStage[] }) {
  return (
    <ol className="stepper" aria-label="Pipeline progress">
      {stages.map((stage, index) => (
        <li key={stage.name} className={`stepper__step stepper__step--${stage.state}`}>
          <span className="stepper__node" aria-hidden="true">
            {stage.state === 'done' ? <Check size={14} /> : stage.state === 'failed' ? <X size={14} /> : index + 1}
          </span>
          <span className="stepper__label">
            {stage.name}
            <span className="visually-hidden">: {STATE_TEXT[stage.state]}</span>
          </span>
        </li>
      ))}
    </ol>
  )
}
