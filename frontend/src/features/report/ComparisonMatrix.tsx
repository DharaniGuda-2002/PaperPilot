import type { Comparison, ResultCell } from '../../api/report'

const KIND = { full_text: 'Full text', abstract: 'Abstract', none: 'No text' } as Record<string, string>

function formatResult(result: ResultCell): string {
  const unit = result.unit === '%' ? '%' : ''
  const method = result.method ? ` (${result.method})` : ''
  return `${result.metric} ${result.value}${unit}${method}`
}

export function ComparisonMatrix({ comparison, onCite }: { comparison: Comparison; onCite: (id: string) => void }) {
  const comparable = comparison.groups.filter((g) => new Set(g.members.map((m) => m.paper_id)).size >= 2)
  return (
    <div className="comparison">
      <section aria-labelledby="groups-heading">
        <h2 id="groups-heading" className="card__title">
          Directly comparable results
        </h2>
        {comparable.length === 0 ? (
          <p className="notice notice--warning">
            No two papers report the same metric on the same dataset under the same evaluation protocol, so no
            results are compared head to head.
          </p>
        ) : (
          comparable.map((group) => (
            <div key={`${group.metric}-${group.dataset}-${group.protocol}`} className="table-wrap">
              <table className="data-table">
                <caption>
                  {group.metric} on {group.dataset} · {group.protocol} (values as reported, not reproduced)
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Paper</th>
                    <th scope="col">Method</th>
                    <th scope="col">Reported value</th>
                    <th scope="col">0–1 scale</th>
                  </tr>
                </thead>
                <tbody>
                  {group.members.map((m) => (
                    <tr key={m.evidence_id}>
                      <td>{comparison.matrix.find((r) => r.paper_id === m.paper_id)?.title}</td>
                      <td>{m.method ?? '—'}</td>
                      <td>
                        <button type="button" className="text-link cite" onClick={() => onCite(m.evidence_id)}>
                          {m.value}
                          {m.unit === '%' ? '%' : ''}
                        </button>
                      </td>
                      <td>{m.normalized.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))
        )}
        {comparison.not_comparable.length > 0 && (
          <p className="hint">
            {comparison.not_comparable.length} other results are listed per paper below but not compared, because their
            dataset, protocol, or unit is not known.
          </p>
        )}
      </section>

      <section aria-labelledby="matrix-heading">
        <h2 id="matrix-heading" className="card__title">
          Comparison matrix
        </h2>
        <div className="table-wrap">
          <table className="data-table data-table--matrix">
            <thead>
              <tr>
                <th scope="col">Paper</th>
                <th scope="col">Text</th>
                <th scope="col">Methods</th>
                <th scope="col">Datasets</th>
                <th scope="col">Protocol</th>
                <th scope="col">Baselines</th>
                <th scope="col">Reported results</th>
                <th scope="col">Comparability warnings</th>
              </tr>
            </thead>
            <tbody>
              {comparison.matrix.map((row) => (
                <tr key={row.paper_id}>
                  <th scope="row">
                    {row.title}
                    {row.year && <span className="hint"> ({row.year})</span>}
                  </th>
                  <td>{KIND[row.content_kind] ?? row.content_kind}</td>
                  <td>{listOrDash(row.methods.map((m) => (row.proposed_methods.includes(m) ? `${m} (proposed)` : m)))}</td>
                  <td>{listOrDash(row.datasets)}</td>
                  <td>{listOrDash(row.protocols)}</td>
                  <td>{listOrDash(row.baselines)}</td>
                  <td>
                    {row.results.length === 0
                      ? '—'
                      : row.results.map((r) => (
                          <button key={r.evidence_id} type="button" className="text-link cite result-cite" onClick={() => onCite(r.evidence_id)}>
                            {formatResult(r)}
                          </button>
                        ))}
                  </td>
                  <td>{row.warnings.length ? <ul className="cell-list">{row.warnings.map((w) => <li key={w}>{w}</li>)}</ul> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function listOrDash(items: string[]) {
  return items.length ? items.join(', ') : '—'
}
