// ── HTTP primitives ──────────────────────────────────────────────────────────

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Extract a human-readable error detail from a failed response. */
async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json()
    if (
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string'
    ) {
      return body.detail
    }
  } catch { /* non-JSON error body */ }
  return `Request failed (${res.status})`
}

export async function request<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal })
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res))
  return res.json() as Promise<T>
}

export async function postRequest<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const bodyString = JSON.stringify(body)
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }

  let reqBody: BodyInit = bodyString
  try {
    const stream = new Blob([bodyString]).stream().pipeThrough(new CompressionStream('gzip'))
    reqBody = await new Response(stream).arrayBuffer()
    headers['Content-Encoding'] = 'gzip'
  } catch {
    // Fallback if CompressionStream is not available
  }

  const res = await fetch(url, { method: 'POST', headers, body: reqBody, signal })
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res))
  return res.json() as Promise<T>
}
