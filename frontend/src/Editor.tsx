import { useEffect, useState } from 'react'
import { api, type Campaign, type Stream, type StreamOffer } from './api'

export default function Editor({ id }: { id: number }) {
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<Campaign>(`/campaigns/${id}`).then(setCampaign).catch((e) => setError(e.message))
  }, [id])

  async function fetchStreams() {
    setError('')
    setBusy(true)
    try {
      const r = await api<{ campaign: Campaign; warnings: string[] }>(`/campaigns/${id}/fetch`, 'POST')
      setCampaign(r.campaign)
      setWarnings(r.warnings)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  // Бэкенд возвращает изменённый поток целиком — подменяем его в списке
  const replaceStream = (s: Stream) => {
    setCampaign((c) => c && { ...c, streams: c.streams.map((x) => (x.id === s.id ? s : x)) })
    setWarnings([]) // предупреждения Fetch относились к прошлому состоянию потоков
  }

  if (!campaign) return error ? <p className="error">{error}</p> : <p className="muted">Загрузка…</p>

  return (
    <>
      <a href="#/" className="back">← Все кампании</a>
      <section className="card">
        <div className="header">
          <div>
            <h1>{campaign.name}</h1>
            <span className="muted">
              Keitaro #{campaign.keitaro_id} · синхронизировано {formatDate(campaign.last_synced_at)}
            </span>
          </div>
          <button className="primary" disabled={busy} onClick={fetchStreams}>
            {busy ? 'Загружаю…' : 'Fetch Streams'}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        {warnings.map((w) => <p key={w} className="warning">{w}</p>)}
      </section>
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

  const raw = stream.raw as { schema?: string; action_payload?: string; filters?: { name: string; mode: string; payload: unknown }[] }
  const isOfferStream = raw.schema === 'landings'
  const current = stream.offers.filter((o) => o.status !== 'removed')
  const archive = stream.offers.filter((o) => o.status === 'removed')

  return (
    <section className={`card stream ${stream.dirty ? 'dirty' : ''}`}>
      <div className="stream-head">
        <span className="pos">#{stream.position}</span>
        <h2>{stream.name}</h2>
        <span className="tag">{raw.schema}</span>
        <span className="muted">Keitaro #{stream.keitaro_id}</span>
        {stream.dirty && <span className="tag dirty">не опубликовано</span>}
      </div>

      {!isOfferStream && (
        <>
          <div className="redirect">
            {raw.filters?.map((f, i) => (
              <span key={i}>Фильтр: <b>{f.name}</b> {f.mode === 'accept' ? '=' : '≠'} {JSON.stringify(f.payload)}</span>
            ))}
            {raw.action_payload && <span>Действие: → <a href={raw.action_payload}>{raw.action_payload}</a></span>}
          </div>
          <details>
            <summary>JSON потока из Keitaro (не редактируется)</summary>
            <pre>{JSON.stringify(stream.raw, null, 2)}</pre>
          </details>
        </>
      )}

      {isOfferStream && (
        <>
          <table>
            <thead>
              <tr><th>Оффер</th><th>Вес</th><th>В Keitaro</th><th>Pin</th><th></th></tr>
            </thead>
            <tbody>
              {current.map((o) => <OfferRow key={o.id} offer={o} run={run} />)}
              {current.length === 0 && <tr><td colSpan={5} className="muted">В потоке нет офферов</td></tr>}
            </tbody>
          </table>

          <div className="toolbar">
            <input type="number" placeholder="ID оффера" value={offerId}
              onChange={(e) => { setOfferId(e.target.value); setFound(null) }} onKeyDown={(e) => e.key === 'Enter' && offerId && search()} />
            <button disabled={!offerId} onClick={search}>Найти</button>
            {found && (
              <>
                <span className="found">{found.name}</span>
                <button className="primary" onClick={add}>Добавить</button>
              </>
            )}
            <span className="spacer" />
            <button disabled={!stream.dirty} onClick={() => run(`/streams/${stream.id}/cancel`)}>Cancel</button>
            <button className="primary" disabled={!stream.dirty} onClick={() => run(`/streams/${stream.id}/push`)}>
              Push to Keitaro
            </button>
          </div>

          {archive.length > 0 && (
            <>
              <h3>Архив</h3>
              <ul className="archive">
                {archive.map((o) => (
                  <li key={o.id}>
                    <span>{o.offer_name} <span className="muted">#{o.offer_keitaro_id}</span></span>
                    <button className="small" onClick={() => run(`/stream-offers/${o.id}/restore`)}>Bring Back</button>
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

const LABELS: Record<string, [string, string]> = {
  pending_add: ['новый', 'new'],
  pending_remove: ['будет удалён', 'removing'],
}

function OfferRow({ offer, run }: { offer: StreamOffer; run: (path: string, method?: string, body?: unknown) => Promise<boolean> }) {
  const [share, setShare] = useState(String(offer.share))
  useEffect(() => setShare(String(offer.share)), [offer.share])

  const removing = offer.status === 'pending_remove'
  const label = LABELS[offer.status]
  const pin = (pinned: boolean, value = offer.share) => run(`/stream-offers/${offer.id}`, 'PATCH', { pinned, share: value })

  async function savePinnedShare() {
    if (share === String(offer.share)) return
    // Пустое поле или отказ бэкенда — возвращаем в поле настоящий вес
    if (share.trim() === '' || !(await pin(true, Number(share)))) setShare(String(offer.share))
  }

  return (
    <tr className={removing ? 'removing' : ''}>
      <td>
        <span className="offer-name">{offer.offer_name}</span> <span className="muted">#{offer.offer_keitaro_id}</span>
        {label && <> <span className={`tag ${label[1]}`}>{label[0]}</span></>}
      </td>
      <td>
        <div className="weight">
          <div className="bar"><div style={{ width: `${offer.share}%` }} /></div>
          {offer.pinned ? (
            <input
              type="number" min={0} max={100} className="share" value={share}
              onChange={(e) => setShare(e.target.value)}
              onBlur={savePinnedShare}
              onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            />
          ) : (
            <b>{offer.share}%</b>
          )}
        </div>
      </td>
      <td className={offer.published_share !== offer.share ? 'changed' : 'muted'}>
        {offer.published_share === null ? '—' : `${offer.published_share}%`}
      </td>
      <td>
        <label className="pin">
          <input type="checkbox" disabled={removing} checked={offer.pinned} onChange={(e) => pin(e.target.checked)} />
          {offer.pinned && '📌'}
        </label>
      </td>
      <td>
        {removing ? (
          <button className="small" onClick={() => run(`/stream-offers/${offer.id}/restore`)}>Bring Back</button>
        ) : (
          <button className="small danger" onClick={() => run(`/stream-offers/${offer.id}`, 'DELETE')}>Delete</button>
        )}
      </td>
    </tr>
  )
}

function formatDate(iso: string | null) {
  return iso ? new Date(iso + 'Z').toLocaleString() : 'никогда'
}
