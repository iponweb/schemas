import type { APIRoute, GetStaticPaths } from 'astro'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { getAllControllers, getResources } from '../../../../../../lib/data'

const SCHEMAS_ROOT   = new URL('../../../../../../../../schemas', import.meta.url).pathname
const SCHEMAS_GITHUB = 'https://raw.githubusercontent.com/iponweb/schemas/main/schemas'

function ghCheck(base: string, gh: string, rel: string): string | null {
  return existsSync(join(base, rel)) ? `${gh}/${rel}` : null
}

function schemaFile(kind: string, group: string, apiVersion: string): string {
  const k = kind.toLowerCase()
  const gp = group ? group.split('.')[0] : null
  return gp ? `${k}-${gp}-${apiVersion}.json` : `${k}-${apiVersion}.json`
}

export const getStaticPaths: GetStaticPaths = () => {
  const paths = []
  for (const ctrl of getAllControllers()) {
    for (const version of ctrl.versions) {
      paths.push({ params: { org: ctrl.org, repo: ctrl.repo, version } })
    }
  }
  return paths
}

export const GET: APIRoute = ({ params }) => {
  const { org, repo, version } = params as { org: string; repo: string; version: string }
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')

  const fsBase = join(SCHEMAS_ROOT, org, repo, version)
  const gh     = `${SCHEMAS_GITHUB}/${org}/${repo}/${version}`
  const check  = (rel: string) => ghCheck(fsBase, gh, rel)

  const definitionsSource = check('json-schema/source/_definitions.json')
  const definitionsLive   = check('json-schema/live/_definitions.json')

  const resources = getResources(org, repo, version).map(r => {
    const sf = schemaFile(r.kind, r.group, r.version)
    const entry: Record<string, unknown> = {
      kind:    r.kind,
      group:   r.group,
      version: r.version,
      plural:  r.plural,
      scope:   r.scope,
    }
    if (r.shortNames?.length)    entry.shortNames   = r.shortNames
    if (r.definitionKey)         entry.definitionKey = r.definitionKey
    if (r.userManaged === false)  entry.userManaged  = false

    entry.urls = {
      schemaSource: check(`json-schema/source/${sf}`),
      schemaLive:   check(`json-schema/live/${sf}`),
      crd:          r.group ? check(`crd/${r.plural}.${r.group}.yaml`) : null,
    }
    return entry
  })

  const body = {
    org,
    repo,
    version,
    url:              `${base}/api/v1/${org}/${repo}/${version}/index.json`,
    crdsBundle:       check('crds.yaml'),
    openapiSource:    check('openapi/source.json'),
    openapiLive:      check('openapi/live.json'),
    definitionsSource,
    definitionsLive,
    resources,
  }

  return new Response(JSON.stringify(body, null, 2), {
    headers: { 'Content-Type': 'application/json' },
  })
}
