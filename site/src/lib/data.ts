import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import yaml from 'js-yaml'
import type { Controller, Resource, SchemaProperty, VersionDiff } from './types'

export interface ChangeHistoryEntry {
  version: string
  added: string[]
  removed: string[]
  changed: string[]
}

// 3 levels up from site/src/lib/ → repo root, then into schemas/
const SCHEMAS_ROOT = new URL('../../../schemas', import.meta.url).pathname

/**
 * Sort versions descending: v1.10.0 > v1.9.0 > v1.2.0
 * Handles pre-release suffixes (e.g. v1.30.0-rc.0) by placing them before the
 * same base version (rc < release).
 */
export function sortVersions(versions: string[]): string[] {
  return [...versions].sort((a, b) => {
    const parse = (v: string) => {
      const clean = v.replace(/^v/, '')
      const [base, pre] = clean.split('-', 2)
      const parts = base.split('.').map(Number)
      return { parts, pre: pre ?? null }
    }
    const va = parse(a)
    const vb = parse(b)
    for (let i = 0; i < Math.max(va.parts.length, vb.parts.length); i++) {
      const diff = (vb.parts[i] ?? 0) - (va.parts[i] ?? 0)
      if (diff !== 0) return diff
    }
    // same numeric parts — release > pre-release
    if (va.pre === null && vb.pre !== null) return -1
    if (va.pre !== null && vb.pre === null) return 1
    if (va.pre && vb.pre) return vb.pre.localeCompare(va.pre)
    return 0
  })
}

function readYaml(filePath: string): unknown {
  const content = readFileSync(filePath, 'utf-8')
  return yaml.load(content)
}

function readJsonFile(filePath: string): unknown {
  const content = readFileSync(filePath, 'utf-8')
  return JSON.parse(content)
}

function listDirs(dirPath: string): string[] {
  if (!existsSync(dirPath)) return []
  try {
    return readdirSync(dirPath, { withFileTypes: true })
      .filter(d => d.isDirectory() && !d.name.startsWith('.'))
      .map(d => d.name)
  } catch {
    return []
  }
}

export function getAllControllers(): Controller[] {
  const controllers: Controller[] = []
  const orgs = listDirs(SCHEMAS_ROOT)
  for (const org of orgs) {
    const orgPath = join(SCHEMAS_ROOT, org)
    const repos = listDirs(orgPath)
    for (const repo of repos) {
      const repoPath = join(orgPath, repo)
      const entries = listDirs(repoPath)
      // Only include entries that look like versions (start with "v" or digit)
      const versions = entries.filter(e => /^v?\d/.test(e))
      if (versions.length === 0) continue
      controllers.push({
        org,
        repo,
        slug: `${org}/${repo}`,
        versions: sortVersions(versions),
      })
    }
  }
  return controllers
}

export function getResources(org: string, repo: string, version: string): Resource[] {
  const indexPath = join(SCHEMAS_ROOT, org, repo, version, 'index.yaml')
  try {
    const data = readYaml(indexPath) as { resources: Resource[] }
    return data?.resources ?? []
  } catch {
    return []
  }
}

/**
 * controllerVersion: the release version tag (e.g. "v1.10.0"), used to locate
 *   the file under schemas/ORG/REPO/CONTROLLER_VERSION/crd/
 * apiVersion: the Kubernetes API version string (e.g. "v1", "v1beta1") used to
 *   match spec.versions[N].name inside the CRD YAML.
 */
export function getResourceSchema(
  org: string,
  repo: string,
  controllerVersion: string,
  plural: string,
  group: string,
  apiVersion?: string,
): SchemaProperty | null {
  const crdPath = join(SCHEMAS_ROOT, org, repo, controllerVersion, 'crd', `${plural}.${group}.yaml`)
  if (!existsSync(crdPath)) return null
  try {
    const crd = readYaml(crdPath) as {
      spec?: {
        versions?: Array<{ name: string; schema?: { openAPIV3Schema?: SchemaProperty } }>
      }
    }
    const crdVersions = crd?.spec?.versions ?? []
    // If apiVersion is given, match by name; otherwise return the first version's schema
    const match = apiVersion
      ? crdVersions.find(v => v.name === apiVersion)
      : crdVersions[0]
    return match?.schema?.openAPIV3Schema ?? null
  } catch {
    return null
  }
}

/**
 * For kubernetes/ built-in resources, try to retrieve the schema from the
 * json-schema/source/_definitions.json fallback. Returns null if not found.
 */
export function getResourceSchemaFromDefinitions(
  org: string,
  repo: string,
  version: string,
  kind: string,
  group: string,
): SchemaProperty | null {
  const defPath = join(SCHEMAS_ROOT, org, repo, version, 'json-schema', 'source', '_definitions.json')
  if (!existsSync(defPath)) return null
  try {
    const defs = readJsonFile(defPath) as { definitions?: Record<string, SchemaProperty> }
    if (!defs.definitions) return null
    // Build a key like "io.k8s.api.core.v1.ConfigMap" by searching definitions
    // keys that end with the kind (case-sensitive)
    const entries = Object.entries(defs.definitions)
    const match = entries.find(([key]) => {
      const parts = key.split('.')
      return parts[parts.length - 1] === kind
    })
    return match ? match[1] : null
  } catch {
    return null
  }
}

export function getDefinitions(
  org: string,
  repo: string,
  version: string,
): Record<string, SchemaProperty> {
  const defPath = join(SCHEMAS_ROOT, org, repo, version, 'json-schema', 'source', '_definitions.json')
  if (!existsSync(defPath)) return {}
  try {
    const defs = readJsonFile(defPath) as { definitions?: Record<string, SchemaProperty> }
    return defs.definitions ?? {}
  } catch {
    return {}
  }
}

export function getVersionDiff(
  org: string,
  repo: string,
  versionNew: string,
  versionOld: string,
): VersionDiff {
  const newResources = getResources(org, repo, versionNew)
  const oldResources = getResources(org, repo, versionOld)

  const toKey = (r: Resource) => `${r.group}/${r.kind}`

  const oldMap = new Map(oldResources.map(r => [toKey(r), r]))
  const newMap = new Map(newResources.map(r => [toKey(r), r]))

  const added = newResources.filter(r => !oldMap.has(toKey(r)))
  const removed = oldResources.filter(r => !newMap.has(toKey(r)))

  const changed: VersionDiff['changed'] = []
  for (const newR of newResources) {
    const oldR = oldMap.get(toKey(newR))
    if (!oldR) continue

    const getTopLevelFields = (r: Resource, controllerVersion: string): Set<string> => {
      const schema = getResourceSchema(org, repo, controllerVersion, r.plural, r.group, r.version)
      const specProps = schema?.properties?.spec?.properties ?? {}
      return new Set(Object.keys(specProps))
    }

    try {
      const newFields = getTopLevelFields(newR, versionNew)
      const oldFields = getTopLevelFields(oldR, versionOld)
      const addedFields = [...newFields].filter(f => !oldFields.has(f))
      const removedFields = [...oldFields].filter(f => !newFields.has(f))

      if (addedFields.length > 0 || removedFields.length > 0) {
        changed.push({ resource: newR, addedFields, removedFields })
      }
    } catch {
      // skip
    }
  }

  return { added, removed, changed }
}

/**
 * Given a sorted-newest-first list of versions, return one representative
 * version per MAJOR.MINOR (the highest patch for that minor).
 */
export function latestPatchPerMinor(versions: string[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const v of versions) {
    const clean = v.replace(/^v/, '').split('-')[0]
    const parts = clean.split('.')
    const minor = `v${parts[0]}.${parts[1]}`
    if (!seen.has(minor)) {
      seen.add(minor)
      result.push(v)
    }
  }
  return result
}

/**
 * Recursively flatten a schema into a map of path -> {type, description}.
 * Only paths with non-empty prefix are added (the root itself is skipped).
 */
function flattenSchemaToMap(
  schema: SchemaProperty,
  definitions: Record<string, SchemaProperty>,
  prefix = '',
  visited = new Set<string>(),
  depth = 0,
  maxDepth = 8,
): Map<string, { type: string; description: string }> {
  const result = new Map<string, { type: string; description: string }>()
  if (depth >= maxDepth) return result

  // Resolve $ref
  let resolved = schema
  if (schema.$ref) {
    const key = schema.$ref.replace('#/definitions/', '')
    if (visited.has(key)) return result
    const def = definitions[key]
    if (!def) return result
    resolved = def
    visited = new Set(visited)
    visited.add(key)
  }

  // Add this node if we have a prefix
  if (prefix !== '') {
    result.set(prefix, {
      type: resolved.type ?? '',
      description: resolved.description ?? '',
    })
  }

  // Recurse into properties
  if (resolved.properties) {
    for (const [key, child] of Object.entries(resolved.properties)) {
      const childPath = prefix === '' ? key : `${prefix}.${key}`
      const sub = flattenSchemaToMap(child, definitions, childPath, visited, depth + 1, maxDepth)
      for (const [k, v] of sub) result.set(k, v)
    }
  }

  // Recurse into items (arrays)
  if (resolved.items) {
    const childPath = prefix === '' ? '[]' : `${prefix}[]`
    const sub = flattenSchemaToMap(resolved.items, definitions, childPath, visited, depth + 1, maxDepth)
    for (const [k, v] of sub) result.set(k, v)
  }

  return result
}

/**
 * Build the change history for a resource across minor versions.
 */
export function getChangeHistory(
  org: string,
  repo: string,
  allVersions: string[],
  plural: string,
  group: string,
  apiVersion: string,
  kind: string,
): ChangeHistoryEntry[] {
  const minorVersions = latestPatchPerMinor(allVersions)
  const result: ChangeHistoryEntry[] = []

  for (let i = 0; i < minorVersions.length - 1; i++) {
    const vNew = minorVersions[i]
    const vOld = minorVersions[i + 1]

    try {
      const isKubernetes = org === 'kubernetes' && repo === 'kubernetes'

      let schemNew: SchemaProperty | null = null
      let schemOld: SchemaProperty | null = null
      let defsNew: Record<string, SchemaProperty> = {}
      let defsOld: Record<string, SchemaProperty> = {}

      if (!isKubernetes) {
        schemNew = getResourceSchema(org, repo, vNew, plural, group, apiVersion)
        schemOld = getResourceSchema(org, repo, vOld, plural, group, apiVersion)
        if (!schemNew && !schemOld) continue
        if (!schemNew || !schemOld) continue
      } else {
        defsNew = getDefinitions(org, repo, vNew)
        defsOld = getDefinitions(org, repo, vOld)
        schemNew = getResourceSchemaFromDefinitions(org, repo, vNew, kind, group)
        schemOld = getResourceSchemaFromDefinitions(org, repo, vOld, kind, group)
        if (!schemNew || !schemOld) continue
      }

      const flatNew = flattenSchemaToMap(schemNew, defsNew)
      const flatOld = flattenSchemaToMap(schemOld, defsOld)

      const added: string[] = []
      const removed: string[] = []
      const changed: string[] = []

      for (const [key, valNew] of flatNew) {
        if (!flatOld.has(key)) {
          added.push(key)
        } else {
          const valOld = flatOld.get(key)!
          if (valOld.description !== valNew.description) {
            changed.push(key)
          }
        }
      }

      for (const key of flatOld.keys()) {
        if (!flatNew.has(key)) {
          removed.push(key)
        }
      }

      if (added.length > 0 || removed.length > 0 || changed.length > 0) {
        result.push({ version: vNew, added, removed, changed })
      }
    } catch {
      // skip this pair
    }
  }

  return result
}

/**
 * Returns local icon info for a controller, or null if none found.
 * Checks for icon.svg first, then icon.png.
 * For SVG: returns { type: 'svg', content: string } (inline SVG markup).
 * For PNG: returns { type: 'img', src: string } (base64 data URI).
 */
const SCHEMAS_GITHUB = 'https://github.com/iponweb/schemas/blob/main/schemas'

/**
 * Returns the controller's repository URL from schemas/ORG/REPO/index.yaml, or null.
 */
export function getControllerMeta(org: string, repo: string): { name?: string; repository?: string } | null {
  const p = join(SCHEMAS_ROOT, org, repo, 'index.yaml')
  if (!existsSync(p)) return null
  try {
    return yaml.load(readFileSync(p, 'utf-8')) as { name?: string; repository?: string }
  } catch {
    return null
  }
}

/**
 * Returns GitHub UI links for files that exist in a given version directory.
 */
export function getVersionAssets(org: string, repo: string, version: string): {
  openapiSource: string | null
  openapiLive: string | null
  jsonSchemaSource: string | null
  jsonSchemaLive: string | null
  githubTree: string
} {
  const base = join(SCHEMAS_ROOT, org, repo, version)
  const gh = `${SCHEMAS_GITHUB}/${org}/${repo}/${version}`

  const check = (rel: string) =>
    existsSync(join(base, rel)) ? `${gh}/${rel}` : null

  return {
    openapiSource:    check('openapi/source.json'),
    openapiLive:      check('openapi/live.json'),
    jsonSchemaSource: check('json-schema/source/_definitions.json'),
    jsonSchemaLive:   check('json-schema/live/_definitions.json'),
    githubTree:       `https://github.com/iponweb/schemas/tree/main/schemas/${org}/${repo}/${version}`,
  }
}

/**
 * Finds the definition key for a kind within a _definitions.json file.
 * Searches by matching the last segment of the key (the Kind name).
 * When multiple keys match (same kind in different groups), prefers the one
 * whose group segment matches the resource's group first segment.
 */
function findDefinitionKey(defsPath: string, kind: string, group: string): string | null {
  if (!existsSync(defsPath)) return null
  try {
    const defs = readJsonFile(defsPath) as { definitions?: Record<string, unknown> }
    if (!defs.definitions) return null
    const entries = Object.keys(defs.definitions)
    const candidates = entries.filter(key => key.split('.').at(-1) === kind)
    if (candidates.length === 0) return null
    if (candidates.length === 1) return candidates[0]
    // Prefer the key whose reversed-group prefix matches the resource group
    const groupPrefix = group ? group.split('.')[0] : null
    if (groupPrefix) {
      const preferred = candidates.find(k => k.startsWith(groupPrefix + '.'))
      if (preferred) return preferred
    }
    return candidates[0]
  } catch {
    return null
  }
}

/**
 * Returns GitHub UI links for files relevant to a specific resource kind.
 * JSON schema filename convention from openapi2jsonschema:
 *   core group:     {kind}-{version}.json
 *   non-core group: {kind}-{groupFirstSegment}-{version}.json
 * where kind and groupFirstSegment are lowercased.
 */
export function getResourceAssets(
  org: string,
  repo: string,
  version: string,
  kind: string,
  group: string,
  apiVersion: string,
  plural: string,
): {
  jsonSchemaSource:   string | null
  jsonSchemaLive:     string | null
  jsonSchemaFile:     string
  definitionsSource:  string | null
  definitionsLive:    string | null
  definitionKey:      string | null
  crdFile:            string | null
  githubTree:         string
} {
  const base = join(SCHEMAS_ROOT, org, repo, version)
  const gh   = `${SCHEMAS_GITHUB}/${org}/${repo}/${version}`

  const kindLower = kind.toLowerCase()
  const groupPrefix = group ? group.split('.')[0] : null
  const schemaFile = groupPrefix
    ? `${kindLower}-${groupPrefix}-${apiVersion}.json`
    : `${kindLower}-${apiVersion}.json`

  const check = (rel: string) =>
    existsSync(join(base, rel)) ? `${gh}/${rel}` : null

  // Prefer the pre-computed key from index.yaml (written by generate.py),
  // fall back to scanning _definitions.json at build time.
  const indexPath = join(SCHEMAS_ROOT, org, repo, version, 'index.yaml')
  let definitionKey: string | null = null
  if (existsSync(indexPath)) {
    try {
      const idx = readYaml(indexPath) as { resources?: Array<{ kind: string; group: string; definitionKey?: string }> }
      const match = idx?.resources?.find(r => r.kind === kind && (r.group ?? '') === (group ?? ''))
      definitionKey = match?.definitionKey ?? null
    } catch { /* ignore */ }
  }
  if (!definitionKey) {
    const defSourcePath = join(base, 'json-schema', 'source', '_definitions.json')
    const defLivePath   = join(base, 'json-schema', 'live', '_definitions.json')
    definitionKey = findDefinitionKey(defSourcePath, kind, group)
      ?? findDefinitionKey(defLivePath, kind, group)
  }

  return {
    jsonSchemaSource:  check(`json-schema/source/${schemaFile}`),
    jsonSchemaLive:    check(`json-schema/live/${schemaFile}`),
    jsonSchemaFile:    schemaFile,
    definitionsSource: check('json-schema/source/_definitions.json'),
    definitionsLive:   check('json-schema/live/_definitions.json'),
    definitionKey,
    crdFile:           group ? check(`crd/${plural}.${group}.yaml`) : null,
    githubTree:        `https://github.com/iponweb/schemas/tree/main/schemas/${org}/${repo}/${version}`,
  }
}

export function getControllerIconFile(
  org: string,
  repo: string,
): { type: 'svg'; content: string } | { type: 'img'; src: string } | null {
  const dir = join(SCHEMAS_ROOT, org, repo)
  const svgPath = join(dir, 'icon.svg')
  const pngPath = join(dir, 'icon.png')
  if (existsSync(svgPath)) {
    return { type: 'svg', content: readFileSync(svgPath, 'utf-8') }
  }
  if (existsSync(pngPath)) {
    const data = readFileSync(pngPath).toString('base64')
    return { type: 'img', src: `data:image/png;base64,${data}` }
  }
  return null
}
