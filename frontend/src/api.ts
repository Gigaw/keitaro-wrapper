export type OfferStatus = 'active' | 'pending_add' | 'pending_remove' | 'removed'

export type StreamOffer = {
  id: number
  offer_keitaro_id: number
  offer_name: string
  share: number
  published_share: number | null
  pinned: boolean
  status: OfferStatus
}

export type Stream = {
  id: number
  keitaro_id: number
  name: string
  position: number
  raw: Record<string, unknown>
  last_synced_at: string | null
  dirty: boolean
  offers: StreamOffer[]
}

export type Campaign = {
  id: number
  keitaro_id: number
  name: string
  last_synced_at: string | null
  streams: Stream[]
}

export type Option = { id: number; name: string }

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const r = await fetch('/api' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await r.json().catch(() => null)
  if (!r.ok) throw new Error(errorText(data) || `Ошибка ${r.status}`)
  return data
}

// FastAPI отдаёт detail строкой (наши ошибки) или списком (ошибки валидации полей)
function errorText(data: { detail?: string | { loc: string[]; msg: string }[] } | null): string {
  const detail = data?.detail
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join('; ')
  return detail ?? ''
}
