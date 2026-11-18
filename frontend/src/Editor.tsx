import { useEffect, useState } from 'react'
import { api, type Campaign, type Stream, type StreamOffer } from './api'

export default function Editor({ id }: { id: number }) {
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api<Campaign>(`/campaigns/${id}`).then(setCampaign).catch((e) => setError(e.message))
  }, [id])

  async function fetchStreams() {
    setError('')
    try {
      const r = await api<{ campaign: Campaign; warnings: string[] }>(`/campaigns/${id}/fetch`, 'POST')
      setCampaign(r.campaign)
      setWarnings(r.warnings)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  // Бэкенд возвращает изменённый поток целиком — подменяем его в списке
  const replaceStream = (s: Stream) =>
    setCampaign((c) => c && { ...c, streams: c.streams.map((x) => (x.id === s.id ? s : x)) })

  if (!campaign) return error ? <p className="error">{error}</p> : <p>Загрузка…</p>

  return (
    <>
      <a href="#/">← К списку</a>
      <h1>{campaign.name}</h1>
      <p className="muted">
        Keitaro ID {campaign.keitaro_id} · синхронизировано {formatDate(campaign.last_synced_at)}
      </p>
      <button onClick={fetchStreams}>Fetch Streams</button>
      {error && <p className="error">{error}</p>}
      {warnings.map((w) => <p key={w} className="warning">{w}</p>)}
      {campaign.streams.map((s) => <StreamCard key={s.id} stream={s} onChange={replaceStream} />)}
    </>
  )
}

function StreamCard({ stream, onChange }: { stream: Stream; onChange: (s: Stream) => void }) {
  const [error, setError] = useState('')
  const [offerId, setOfferId] = useState('')
  const [found, setFound] = useState<{ id: number; name: string } | null>(null)

  async function run(path: string, method = 'POST', body?: unknown) {
    setError('')
    try {
      onChange(await api<Stream>(path, method, body))
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    }
  }

  async function search() {
    setError('')
    setFound(null)
    try {
      setFound(await api(`/offers/${offerId}`))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function add() {
    if (await run(`/streams/${stream.id}/offers`, 'POST', { offer_id: found!.id })) {
      setFound(null)
      setOfferId('')
    }
  }

  const isOfferStream = stream.raw.schema === 'landings'
  const current = stream.offers.filter((o) => o.status !== 'removed')
  const archive = stream.offers.filter((o) => o.status === 'removed')

  return (
    <section className={`stream ${stream.dirty ? 'dirty' : ''}`}>
      <h2>
        #{stream.position} {stream.name} <span className="muted">({String(stream.raw.schema)}, Keitaro ID {stream.keitaro_id})</span>
      </h2>
      {stream.dirty && <p>Есть неопубликованные изменения</p>}

      {!isOfferStream && (
        <details>
          <summary>Настройки потока из Keitaro (не редактируются)</summary>
          <pre>{JSON.stringify({ action_type: stream.raw.action_type, action_payload: stream.raw.action_payload, filters: stream.raw.filters }, null, 2)}</pre>
        </details>
      )}

      {isOfferStream && (
        <>
          <table>
            <thead>
              <tr><th>Оффер</th><th>Вес</th><th>В Keitaro</th><th>Pin</th><th></th></tr>
            </thead>
            <tbody>
              {current.map((o) => <OfferRow key={o.id} offer={o} run={run} />)}
              {current.length === 0 && <tr><td colSpan={5} className="muted">Нет офферов</td></tr>}
            </tbody>
          </table>

          <div className="row">
            <input type="number" placeholder="ID оффера" value={offerId} onChange={(e) => setOfferId(e.target.value)} />
            <button disabled={!offerId} onClick={search}>Найти</button>
            {found && (
              <>
                <span>{found.name}</span>
                <button onClick={add}>Добавить</button>
              </>
            )}
          </div>

          <div className="row">
            <button disabled={!stream.dirty} onClick={() => run(`/streams/${stream.id}/push`)}>Push to Keitaro</button>
            <button disabled={!stream.dirty} onClick={() => run(`/streams/${stream.id}/cancel`)}>Cancel</button>
          </div>

          {archive.length > 0 && (
            <>
              <h3>Архив</h3>
              <ul>
                {archive.map((o) => (
                  <li key={o.id}>
                    {o.offer_name} <span className="muted">#{o.offer_keitaro_id}</span>{' '}
                    <button onClick={() => run(`/stream-offers/${o.id}/restore`)}>Bring Back</button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  )
}

const LABELS: Record<string, string> = { pending_add: 'новый', pending_remove: 'будет удалён' }

function OfferRow({ offer, run }: { offer: StreamOffer; run: (path: string, method?: string, body?: unknown) => Promise<boolean> }) {
  const [share, setShare] = useState(String(offer.share))
  useEffect(() => setShare(String(offer.share)), [offer.share])

  const removing = offer.status === 'pending_remove'
  const pin = (pinned: boolean, value = offer.share) => run(`/stream-offers/${offer.id}`, 'PATCH', { pinned, share: value })

  return (
    <tr className={removing ? 'removing' : ''}>
      <td>
        {offer.offer_name} <span className="muted">#{offer.offer_keitaro_id}</span>
        {LABELS[offer.status] && <span className="badge">{LABELS[offer.status]}</span>}
      </td>
      <td>
        {offer.pinned ? (
          <input
            type="number" min={0} max={100} className="share" value={share}
            onChange={(e) => setShare(e.target.value)}
            onBlur={() => share !== String(offer.share) && pin(true, Number(share))}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
          />
        ) : (
          offer.share
        )}
        %
      </td>
      <td className="muted">{offer.published_share === null ? '—' : `${offer.published_share}%`}</td>
      <td>
        <input type="checkbox" disabled={removing} checked={offer.pinned} onChange={(e) => pin(e.target.checked)} />
      </td>
      <td>
        {removing ? (
          <button onClick={() => run(`/stream-offers/${offer.id}/restore`)}>Bring Back</button>
        ) : (
          <button onClick={() => run(`/stream-offers/${offer.id}`, 'DELETE')}>Delete</button>
        )}
      </td>
    </tr>
  )
}

function formatDate(iso: string | null) {
  return iso ? new Date(iso + 'Z').toLocaleString() : 'никогда'
}
