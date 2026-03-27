import { useState } from 'react'

export interface ChangeHistoryEntry {
  version: string
  added: string[]
  removed: string[]
  changed: string[]
}

interface ChangeHistoryProps {
  history: ChangeHistoryEntry[]
  label: string
}

function extractMinor(version: string): string {
  const clean = version.replace(/^v/, '').split('-')[0]
  const parts = clean.split('.')
  return `v${parts[0]}.${parts[1]}`
}

export default function ChangeHistory({ history, label }: ChangeHistoryProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  function toggle(idx: number) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  return (
    <div className="bg-white border border-zinc-200 rounded-xl shadow-sm overflow-hidden">
      <div className="bg-zinc-50 border-b border-zinc-200 px-6 py-4">
        <h2 className="text-base font-semibold text-zinc-700">Change History</h2>
      </div>
      <div className="divide-y divide-zinc-100">
        {history.map((entry, idx) => {
          const isOpen = expanded.has(idx)
          const minor = extractMinor(entry.version)
          const addedCount = entry.added.length
          const removedCount = entry.removed.length
          const changedCount = entry.changed.length

          return (
            <div key={entry.version}>
              <button
                type="button"
                onClick={() => toggle(idx)}
                className="w-full flex items-center gap-3 px-6 py-3 text-left hover:bg-zinc-50 transition-colors"
              >
                <span className="text-zinc-400 text-xs w-3 flex-shrink-0">
                  {isOpen ? '▼' : '▶'}
                </span>
                <span className="text-sm font-mono font-medium text-zinc-700">
                  {label} {minor}
                </span>
                <span className="flex items-center gap-2 ml-2">
                  {addedCount > 0 && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                      +{addedCount}
                    </span>
                  )}
                  {removedCount > 0 && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
                      -{removedCount}
                    </span>
                  )}
                  {changedCount > 0 && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                      ~{changedCount}
                    </span>
                  )}
                </span>
              </button>

              {isOpen && (
                <div className="px-6 pb-4 space-y-4 bg-zinc-50 border-t border-zinc-100">
                  {addedCount > 0 && (
                    <div className="pt-3">
                      <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
                        {addedCount} {addedCount === 1 ? 'property' : 'properties'} added
                      </p>
                      <ul className="space-y-0.5">
                        {entry.added.map(path => (
                          <li key={path} className="font-mono text-sm text-emerald-600">{path}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {removedCount > 0 && (
                    <div className={addedCount > 0 ? '' : 'pt-3'}>
                      <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
                        {removedCount} {removedCount === 1 ? 'property' : 'properties'} removed
                      </p>
                      <ul className="space-y-0.5">
                        {entry.removed.map(path => (
                          <li key={path} className="font-mono text-sm text-rose-600">{path}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {changedCount > 0 && (
                    <div className={(addedCount > 0 || removedCount > 0) ? '' : 'pt-3'}>
                      <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
                        {changedCount} {changedCount === 1 ? 'property' : 'properties'} changed description
                      </p>
                      <ul className="space-y-0.5">
                        {entry.changed.map(path => (
                          <li key={path} className="font-mono text-sm text-amber-600">{path}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
