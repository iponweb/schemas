import { getAllControllers, getControllerMeta } from '../../../lib/data'

export async function GET() {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  const controllers = getAllControllers()

  const body = {
    controllers: controllers.map(ctrl => {
      const meta = getControllerMeta(ctrl.org, ctrl.repo)
      return {
        org:           ctrl.org,
        repo:          ctrl.repo,
        name:          meta?.name ?? ctrl.repo,
        repository:    meta?.repository ?? null,
        latestVersion: ctrl.versions[0] ?? null,
        versions:      ctrl.versions,
        url:           `${base}/api/v1/${ctrl.org}/${ctrl.repo}/index.json`,
      }
    }),
  }

  return new Response(JSON.stringify(body, null, 2), {
    headers: { 'Content-Type': 'application/json' },
  })
}
