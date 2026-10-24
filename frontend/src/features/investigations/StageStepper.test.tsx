import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StageStepper } from './StageStepper'

describe('StageStepper', () => {
  it('announces each stage with its state', () => {
    render(
      <StageStepper
        stages={[
          { name: 'Discover', state: 'done', tone: 'success' },
          { name: 'Read', state: 'active', tone: 'info' },
          { name: 'Extract', state: 'waiting', tone: 'neutral' },
        ]}
      />,
    )
    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Discover: done')
    expect(items[1]).toHaveTextContent('Read: in progress')
    expect(items[2]).toHaveTextContent('Extract: waiting')
  })
})
