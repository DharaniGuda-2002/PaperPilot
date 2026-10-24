import type { ReactNode } from 'react'

interface Entry {
  q: string
  a: ReactNode
}

const COMMON: Entry[] = [
  {
    q: 'What does PaperPilot do?',
    a: 'You type a research question. It finds relevant papers, reads them, pulls out facts such as datasets, baselines, results and limitations, and writes a short report. Every fact comes with the exact sentence and page it was taken from.',
  },
  {
    q: 'What happens after I press the arrow?',
    a: 'Five steps run one after another: find papers, download and read them, extract facts, check each fact against the paper text, then compare results and write the report. The progress strip on the investigation page shows where it is.',
  },
  {
    q: 'Why does my investigation say "Queued" and never finish?',
    a: 'The public site runs only the website and the API, not the background workers that do the reading, because free hosting cannot run them. Your question is saved but waits. To see a full result, run PaperPilot on your own computer with Docker Compose (the steps are in the README on GitHub).',
  },
  {
    q: 'How long does a full run take?',
    a: 'About 2 to 6 minutes for 25 papers in my local tests. Most of the time goes to downloading PDFs.',
  },
  {
    q: 'Where do the papers come from?',
    a: 'From OpenAlex, a free index of research. PaperPilot only downloads open-access PDFs, and it respects each site’s robots.txt rules.',
  },
  {
    q: 'What does “evidence strength” mean?',
    a: (
      <>
        It is a label from counting sources, not a score from an AI model. <strong>Strong</strong>: three or more
        full-text papers agree and none contradicts. <strong>Moderate</strong>: two papers, or three or more
        full-text papers with some disagreement. <strong>Limited</strong>: one paper, only abstracts, or two papers with some disagreement.
        <strong>Insufficient</strong>: no paper supports it with a checkable quotation.
      </>
    ),
  },
  {
    q: 'What does “abstract only” mean?',
    a: 'No free full-text PDF was available, so only the paper’s short summary was read. That gives less detail and no page numbers.',
  },
  {
    q: 'Is my question private?',
    a: 'No. There are no accounts, and every investigation is visible to anyone with the link. Do not enter anything confidential.',
  },
  {
    q: 'Does it cost anything?',
    a: 'No. The whole project runs on free tiers. That is also why the public site has limits: 5 new investigations per minute per visitor and 200 per day overall.',
  },
]

const HARD: Entry[] = [
  {
    q: 'Can I trust the numbers in a report?',
    a: 'Trust them as “what the paper reports”, not as proven truth. Each quotation is checked against the stored paper text, so it cannot be invented. But PaperPilot does not re-run experiments, and authors’ own claims can be wrong or measured differently.',
  },
  {
    q: 'Why does it say “no results can be compared directly”?',
    a: 'Two results are compared only if they use the same metric, on the same dataset, with the same test setup. Most papers differ in at least one of these, or the text does not say which. PaperPilot lists those results side by side but will not rank them, because that would be misleading.',
  },
  {
    q: 'Does it use AI or a language model?',
    a: 'No. Extraction and reports use fixed rules, so the output is repeatable and cannot make up a quotation. The cost is that it misses things: on my test set it found about 10% of the key facts, and about half of what it extracted was judged correct. It says “not found” far more often than a human reader would. A language model could be added later, limited to citing stored evidence.',
  },
  {
    q: '“Not found” does not mean the paper lacks it, right?',
    a: 'Right. It means the system did not find it in the text it read. If only the abstract was available, or the wording was unusual, a real result can be missed.',
  },
  {
    q: 'How was accuracy measured?',
    a: 'Against a hand-checked set of 84 facts from 5 papers. The annotations were drafted by an AI assistant and reviewed and approved by the project owner, so it is one annotator and one reviewer. Search found the right passage for 58% of fact lookups in the top 8 results, and 93% of needed passages reached the extractor across all queries. The full method and numbers are in docs/evaluation.md on GitHub.',
  },
  {
    q: 'Can it be tricked by text inside a paper?',
    a: 'Paper text is treated as data only. It is never run, never followed as instructions, and shown as plain text. Downloads go through a safe fetcher that blocks internal and private addresses.',
  },
  {
    q: 'Does it rank which method is best?',
    a: 'No, on purpose. It reports who claims what, how many sources support it, and what is missing. Deciding which method is best needs a fair comparison that most paper sets do not allow.',
  },
  {
    q: 'Why is the first page load or first search slow?',
    a: 'Free hosting puts services to sleep when idle. The first request after a quiet period can take up to a minute while they wake up.',
  },
]

function Group({ title, entries }: { title: string; entries: Entry[] }) {
  return (
    <section aria-label={title} className="faq-group">
      <h2>{title}</h2>
      {entries.map((entry) => (
        <details key={entry.q} className="faq-item">
          <summary>{entry.q}</summary>
          <div className="faq-item__answer"><p>{entry.a}</p></div>
        </details>
      ))}
    </section>
  )
}

export function FaqPage() {
  return (
    <main id="main" tabIndex={-1} className="prose">
      <h1 className="display display--page">Questions and answers</h1>
      <p className="prose__lead">Short answers first, then the harder questions about what PaperPilot can and cannot do.</p>
      <Group title="Common questions" entries={COMMON} />
      <Group title="Harder questions" entries={HARD} />
    </main>
  )
}
