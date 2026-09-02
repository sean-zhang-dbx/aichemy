import { describe, expect, it } from 'vitest'
import { normalizeMarkdownTables } from '../utils/markdown.js'

// A table row's cells (outer pipes stripped, trimmed).
function cells(line) {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|')) s = s.slice(0, -1)
  return s.split('|').map((c) => c.trim())
}

function tableRows(md) {
  return md.split('\n').filter((l) => l.includes('|'))
}

describe('normalizeMarkdownTables', () => {
  it('strips a pandas leading index column present in every row', () => {
    const md = [
      '|    | name                 | logP   |   hydrogen_bond_donors |   hydrogen_bond_acceptors |',
      '|---:|:---------------------|:-------|-----------------------:|--------------------------:|',
      '|  0 | Acetylsalicylic acid | 1.3101 |                      1 |                         3 |',
    ].join('\n')

    const rows = tableRows(normalizeMarkdownTables(md))
    expect(cells(rows[0])).toEqual([
      'name',
      'logP',
      'hydrogen_bond_donors',
      'hydrogen_bond_acceptors',
    ])
    // Values land under the correct headers: HBD=1, HBA=3, index "0" gone.
    expect(cells(rows[2])).toEqual(['Acetylsalicylic acid', '1.3101', '1', '3'])
    expect(rows.every((r) => cells(r).length === 4)).toBe(true)
  })

  it('realigns when the header was index-stripped but data rows still carry the index', () => {
    const md = [
      '| name | logP | hydrogen_bond_donors | hydrogen_bond_acceptors |',
      '|---:|:---|---:|---:|---:|',
      '| 0 | Acetylsalicylic acid | 1.3101 | 1 | 3 |',
    ].join('\n')

    const rows = tableRows(normalizeMarkdownTables(md))
    expect(cells(rows[0])).toEqual([
      'name',
      'logP',
      'hydrogen_bond_donors',
      'hydrogen_bond_acceptors',
    ])
    expect(cells(rows[2])).toEqual(['Acetylsalicylic acid', '1.3101', '1', '3'])
  })

  it('pads a data row that is missing trailing cells', () => {
    const md = ['| a | b | c |', '|---|---|---|', '| 1 | 2 |'].join('\n')
    const rows = tableRows(normalizeMarkdownTables(md))
    expect(cells(rows[2])).toEqual(['1', '2', ''])
  })

  it('leaves a well-formed table with real headers intact', () => {
    const md = ['| a | b |', '|---|---|', '| 1 | 2 |'].join('\n')
    const rows = tableRows(normalizeMarkdownTables(md))
    expect(cells(rows[0])).toEqual(['a', 'b'])
    expect(cells(rows[2])).toEqual(['1', '2'])
  })

  it('returns non-table content unchanged', () => {
    const md = '# Heading\n\nSome **bold** text with a | pipe in prose.\n\n- bullet'
    expect(normalizeMarkdownTables(md)).toBe(md)
  })

  it('handles content with no pipes at all', () => {
    expect(normalizeMarkdownTables('just text')).toBe('just text')
    expect(normalizeMarkdownTables('')).toBe('')
  })
})
