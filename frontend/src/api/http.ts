// ── HTTP primitives ──────────────────────────────────────────────────────────

import { encode } from '@msgpack/msgpack'
import { compress } from 'zstdify'

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
  const packed = encode(body)
  const compressed = compress(packed)

  const headers: Record<string, string> = {
    'Content-Type': 'application/x-msgpack',
    'Content-Encoding': 'zstd',
  }

  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: compressed as unknown as BodyInit,
    signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res))
  return res.json() as Promise<T>
}
