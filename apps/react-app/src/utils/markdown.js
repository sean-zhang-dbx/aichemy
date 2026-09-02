// Normalize markdown tables before rendering.
//
// Genie / pandas emit tables with a leading unnamed "index" column, e.g.:
//
//   |    | name        | logP   |
//   |---:|:------------|:-------|
//   |  0 | Aspirin     | 1.3101 |
//
// The empty-header index column renders as a stray blank column, and when the
// model half-strips it (dropping it from the header but not the data rows) the
// row cells shift and values land under the wrong headers. This utility strips
// the index column and pads/truncates ragged rows so every row matches the
// header's column count, which react-markdown + remark-gfm then render cleanly.

function splitRow(line) {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|')) s = s.slice(0, -1)
  // Split on pipes that are not escaped (SMILES etc. do not contain pipes,
  // but escaped pipes inside cells should not split).
  return s.split(/(?<!\\)\|/).map((c) => c.trim())
}

function isDelimiterRow(cells) {
  return cells.length > 0 && cells.every((c) => /^:?-{1,}:?$/.test(c))
}

function normalizeBlock(block) {
  let rows = block.map(splitRow)
  const header = rows[0]
  const data = rows.slice(2)

  const headerLeadEmpty = header.length >= 2 && header[0] === ''
  const dataLeadIndex =
    data.length > 0 &&
    data.every((r) => r.length >= 2 && (r[0] === '' || /^\d+$/.test(r[0])))

  if (headerLeadEmpty) {
    // Index column present consistently in all rows -> drop the first column.
    rows = rows.map((r) => r.slice(1))
  } else if (dataLeadIndex && data.every((r) => r.length > header.length)) {
    // Header was already index-stripped but the delimiter/data rows still carry
    // it -> drop leading cells from the non-header rows to align to the header.
    rows = rows.map((r, idx) =>
      idx === 0 ? r : r.length > header.length ? r.slice(r.length - header.length) : r
    )
  }

  const ncols = rows[0].length
  rows = rows.map((r, idx) => {
    if (idx === 1) {
      // Delimiter row: keep alignment markers, pad/truncate to ncols.
      const d = r.slice(0, ncols).map((c) => (c === '' ? '---' : c))
      while (d.length < ncols) d.push('---')
      return d
    }
    const rr = r.slice(0, ncols)
    while (rr.length < ncols) rr.push('')
    return rr
  })

  return rows.map((cells) => '| ' + cells.join(' | ') + ' |')
}

export function normalizeMarkdownTables(md) {
  if (typeof md !== 'string' || md.indexOf('|') === -1) return md

  const lines = md.split('\n')
  const out = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const next = lines[i + 1]
    const looksLikeHeader = line.includes('|')
    const looksLikeDelimiter =
      typeof next === 'string' && next.includes('|') && isDelimiterRow(splitRow(next))

    if (looksLikeHeader && looksLikeDelimiter) {
      const block = [line, next]
      let j = i + 2
      while (j < lines.length && lines[j].includes('|') && lines[j].trim() !== '') {
        block.push(lines[j])
        j++
      }
      out.push(...normalizeBlock(block))
      i = j
    } else {
      out.push(line)
      i++
    }
  }
  return out.join('\n')
}
