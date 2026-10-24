/** Plain-language explanations shown in tooltips. One place, so wording stays consistent. */
export const GLOSSARY = {
  investigation:
    'One research question and everything PaperPilot found for it: papers, quoted evidence, and a report.',
  queued:
    'Waiting for a background worker to pick it up. The public demo has no workers, so it stays here. Run PaperPilot locally to see the full result.',
  strength:
    'How much checkable support there is, counted by sources. It is not a probability and not a score from an AI model.',
  evidence:
    'A fact a paper reports (a dataset, a result, a limitation) together with the exact sentence and page it came from.',
  quotation:
    'The sentence is copied word for word from the paper, and PaperPilot checked that it really appears in the stored text.',
  abstractOnly:
    'No free full-text PDF was available, so only the short summary (abstract) was read. Abstracts give less detail and no page numbers.',
  comparable:
    'Two results can be compared only if they use the same metric, on the same dataset, under the same test setup. Otherwise PaperPilot lists them side by side but does not compare them.',
  validation:
    'Automatic checks that the quotation is in the paper, the page matches, the numbers appear in the sentence, and the value is in a sensible range.',
  protocol:
    'How a result was measured, for example a train/test split. Results measured differently are not comparable.',
  notFound:
    'The system looked in the text it read and did not find it. That is not proof the paper lacks it.',
  reported:
    'These numbers are what the authors report. PaperPilot does not re-run their experiments.',
} as const

export type GlossaryKey = keyof typeof GLOSSARY
