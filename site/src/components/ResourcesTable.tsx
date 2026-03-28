import { useState } from 'react'
import type { Resource } from '../lib/types'

interface Props {
  resources: Resource[]
  base: string
  org: string
  repo: string
  version: string
}

export default function ResourcesTable({ resources, base, org, repo, version }: Props) {
  const hasUserManagedData = resources.some(r => r.userManaged === false)
  const [hideSystem, setHideSystem] = useState(false)

  const displayed = hideSystem ? resources.filter(r => r.userManaged !== false) : resources
  const systemCount = resources.filter(r => r.userManaged === false).length

  return (
    <div>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-zinc-800">
          Resources
          <span class="text-sm font-normal text-zinc-400 ml-2">({displayed.length})</span>
        </h2>
        {hasUserManagedData && (
          <label class="flex items-center gap-2 text-sm text-zinc-500 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={hideSystem}
              onChange={e => setHideSystem(e.target.checked)}
              class="rounded border-zinc-300 text-violet-600 focus:ring-violet-500"
            />
            Hide system resources
            {!hideSystem && systemCount > 0 && (
              <span class="text-xs text-zinc-400">({systemCount} total)</span>
            )}
          </label>
        )}
      </div>

      {resources.length === 0 ? (
        <div class="bg-zinc-50 border border-zinc-200 rounded-xl p-8 text-center text-zinc-400">
          No resources found for this version
        </div>
      ) : displayed.length === 0 ? (
        <div class="bg-zinc-50 border border-zinc-200 rounded-xl p-8 text-center text-zinc-400">
          All resources are hidden. Uncheck "Hide system resources" to see them.
        </div>
      ) : (
        <div class="bg-white border border-zinc-200 rounded-xl shadow-sm overflow-hidden">
          <table class="w-full text-sm">
            <thead class="bg-zinc-50 border-b border-zinc-200">
              <tr>
                <th class="text-left px-4 py-3 font-semibold text-zinc-600">Kind</th>
                <th class="text-left px-4 py-3 font-semibold text-zinc-600 hidden sm:table-cell">Group</th>
                <th class="text-left px-4 py-3 font-semibold text-zinc-600 hidden md:table-cell">API Version</th>
                <th class="text-left px-4 py-3 font-semibold text-zinc-600">Scope</th>
                <th class="text-left px-4 py-3 font-semibold text-zinc-600 hidden lg:table-cell">Short Names</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-zinc-100">
              {displayed.map(resource => {
                const isSystem = resource.userManaged === false
                return (
                  <tr
                    key={`${resource.group}/${resource.version}/${resource.kind}`}
                    class={`hover:bg-zinc-50 transition-colors ${isSystem ? 'opacity-60' : ''}`}
                  >
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-2">
                        <a
                          href={`${base}/${org}/${repo}/${version}/${resource.group || 'core'}/${resource.kind}/`}
                          class="font-mono font-semibold text-violet-700 hover:text-violet-900 transition-colors"
                        >
                          {resource.kind}
                        </a>
                        {isSystem && (
                          <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-zinc-100 text-zinc-500 border border-zinc-200">
                            system
                          </span>
                        )}
                      </div>
                      {resource.shortNames && resource.shortNames.length > 0 && (
                        <div class="flex flex-wrap gap-1 mt-1 sm:hidden">
                          {resource.shortNames.map(sn => (
                            <span key={sn} class="text-xs font-mono bg-zinc-100 text-zinc-500 px-1.5 py-0.5 rounded">
                              {sn}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td class="px-4 py-3 hidden sm:table-cell">
                      <span class="font-mono text-xs text-zinc-500">
                        {resource.group || <span class="text-zinc-300 italic">core</span>}
                      </span>
                    </td>
                    <td class="px-4 py-3 hidden md:table-cell">
                      <span class="font-mono text-xs text-zinc-500">
                        {resource.group ? `${resource.group}/${resource.version}` : resource.version}
                      </span>
                    </td>
                    <td class="px-4 py-3">
                      <span class={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        resource.scope === 'Namespaced'
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-amber-100 text-amber-700'
                      }`}>
                        {resource.scope}
                      </span>
                    </td>
                    <td class="px-4 py-3 hidden lg:table-cell">
                      <div class="flex flex-wrap gap-1">
                        {resource.shortNames?.map(sn => (
                          <span key={sn} class="text-xs font-mono bg-zinc-100 text-zinc-500 px-1.5 py-0.5 rounded">
                            {sn}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
