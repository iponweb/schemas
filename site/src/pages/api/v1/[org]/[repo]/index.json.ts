import type { APIRoute, GetStaticPaths } from 'astro'
import { getAllControllers, getControllerMeta } from '../../../../../lib/data'

export const getStaticPaths: GetStaticPaths = () => {
  return getAllControllers().map(ctrl => ({
    params: { org: ctrl.org, repo: ctrl.repo },
  }))
}

export const GET: APIRoute = ({ params }) => {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  const { org, repo } = params as { org: string; repo: string }
  const ctrl = getAllControllers().find(c => c.org === org && c.repo === repo)
  if (!ctrl) return new Response('Not found', { status: 404 })
  const meta = getControllerMeta(org, repo)

  const body = {
    org,
    repo,
    name:       meta?.name ?? repo,
    repository: meta?.repository ?? null,
    versions:   ctrl.versions.map(v => ({
      version: v,
      url:     `${base}/api/v1/${org}/${repo}/${v}/index.json`,
    })),
  }

  return new Response(JSON.stringify(body, null, 2), {
    headers: { 'Content-Type': 'application/json' },
  })
}
