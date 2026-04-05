/** Typed fetch wrapper for our API */
export async function api<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...opts.headers as Record<string, string> },
    ...opts,
  })
  if (!resp.ok) throw new Error(`API ${resp.status}: ${await resp.text()}`)
  return resp.json()
}
