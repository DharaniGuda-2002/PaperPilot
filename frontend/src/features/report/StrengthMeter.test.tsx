import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StrengthMeter } from './StrengthMeter'

describe('StrengthMeter', () => {
  it('marks the current step and shows the published definition', () => {
    render(<StrengthMeter strength="limited" definition="One or two checkable sources." />)
    expect(screen.getByLabelText(/Evidence strength: Limited \(step 2 of 4\)/)).toBeInTheDocument()
    expect(screen.getByText('Limited').closest('li')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('Moderate').closest('li')).not.toHaveAttribute('aria-current')
    expect(screen.getByText('One or two checkable sources.')).toBeInTheDocument()
  })
})
