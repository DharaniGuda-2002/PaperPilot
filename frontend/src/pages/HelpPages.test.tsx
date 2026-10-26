import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { InfoTip } from '../components/InfoTip'
import { renderRoute } from '../test/render'

describe('FAQ page', () => {
  it('has common and harder questions, collapsed until opened', async () => {
    renderRoute('/faq')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Frequently asked questions')
    expect(screen.getByRole('heading', { name: 'Common questions' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Harder questions' })).toBeInTheDocument()
    const question = screen.getByText('Does it use AI or a language model?')
    expect(question.closest('details')).not.toHaveAttribute('open')
    await userEvent.click(question)
    expect(question.closest('details')).toHaveAttribute('open')
  })
})

describe('About page', () => {
  it('shows who built it with a working email link', () => {
    renderRoute('/about')
    expect(screen.getByText('Dharani Guda')).toBeInTheDocument()
    expect(screen.queryByText('dharaniguda2002@gmail.com')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Email me/ })).toHaveAttribute(
      'href',
      'mailto:dharaniguda2002@gmail.com',
    )
  })
})

describe('InfoTip', () => {
  it('explains a term on click and closes on Escape', async () => {
    render(<InfoTip term="strength" label="evidence strength" />)
    const button = screen.getByRole('button', { name: 'What does "evidence strength" mean?' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    await userEvent.click(button)
    expect(screen.getByRole('tooltip')).toHaveTextContent(/not a probability/)
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})

describe('App shell', () => {
  it('links back to the public home page from inside the app', () => {
    renderRoute('/app/investigations/new')
    const home = screen.getAllByRole('link', { name: /PaperPilot/ }).map((link) => link.getAttribute('href'))
    expect(home).toEqual(['/', '/'])
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/app')
  })
})

describe('How it works link', () => {
  it('is in the app sidebar and scrolls the landing page to the steps', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    renderRoute('/app')
    expect(screen.getByRole('link', { name: 'How it works' })).toHaveAttribute('href', '/#how-it-works')
    renderRoute('/#how-it-works')
    await waitFor(() => expect(scroll).toHaveBeenCalled())
  })
})
