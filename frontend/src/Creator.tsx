import { useEffect, useState } from 'react'
import { api, type Campaign, type Option } from './api'

type Options = { domains: Option[]; groups: Option[]; traffic_sources: Option[] }

export default function Creator() {
  const [options, setOptions] = useState<Options | null>(null)
  const [campaigns, setCampaigns] = useState<(Option & { keitaro_id: number })[]>([])
  const [form, setForm] = useState({ name: '', country: '', offer_id: '', domain_id: '', group_id: '', traffic_source_id: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<Options>('/options').then(setOptions).catch((e) => setError(e.message))
    api<(Option & { keitaro_id: number })[]>('/campaigns').then(setCampaigns).catch((e) => setError(e.message))
  }, [])

  const set = (field: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [field]: e.target.value })

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const campaign = await api<Campaign>('/campaigns', 'POST', {
        name: form.name,
        country: form.country.toUpperCase(),
        offer_id: Number(form.offer_id),
        domain_id: Number(form.domain_id),
        group_id: Number(form.group_id),
        traffic_source_id: Number(form.traffic_source_id),
      })
      location.hash = `#/campaigns/${campaign.id}`
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const [importId, setImportId] = useState('')
  const [importError, setImportError] = useState('')

  async function importCampaign(e: React.FormEvent) {
    e.preventDefault()
    setImportError('')
    try {
      const campaign = await api<Campaign>('/campaigns/import', 'POST', { keitaro_id: Number(importId) })
      location.hash = `#/campaigns/${campaign.id}`
    } catch (e) {
      setImportError((e as Error).message)
    }
  }

  const select = (field: 'domain_id' | 'group_id' | 'traffic_source_id', items: Option[] = []) => (
    <select required value={form[field]} onChange={set(field)}>
      <option value="">— выберите —</option>
      {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
    </select>
  )

  return (
    <div className="grid">
      <section className="card">
        <h1>Новая кампания</h1>
        <p className="muted">Создаст кампанию и два потока: гео → google.com и оффер со 100%.</p>
        <form onSubmit={submit} className="form">
          <label>Название<input required value={form.name} onChange={set('name')} placeholder="test-my-campaign" /></label>
          <label>
            Страна <span className="hint">ISO-код из двух букв</span>
            <input required value={form.country} onChange={set('country')} placeholder="AU" maxLength={2} />
          </label>
          <label>ID оффера<input required type="number" value={form.offer_id} onChange={set('offer_id')} placeholder="18813" /></label>
          <label>Домен{select('domain_id', options?.domains)}</label>
          <label>Группа{select('group_id', options?.groups)}</label>
          <label>Источник трафика{select('traffic_source_id', options?.traffic_sources)}</label>
          <button className="primary" disabled={busy || !options}>{busy ? 'Создаю…' : 'Создать в Keitaro'}</button>
          {error && <p className="error">{error}</p>}
        </form>
      </section>

      <section className="card">
        <h2>Открыть кампанию из Keitaro</h2>
        <form onSubmit={importCampaign} className="toolbar">
          <input required type="number" placeholder="ID кампании в Keitaro" value={importId}
            onChange={(e) => setImportId(e.target.value)} />
          <button className="primary">Открыть</button>
        </form>
        {importError && <p className="error">{importError}</p>}

        <h2 style={{ marginTop: 24 }}>Кампании</h2>
        {campaigns.length === 0 && <p className="muted">Пока нет — создайте первую.</p>}
        <ul className="campaigns">
          {campaigns.map((c) => (
            <li key={c.id}>
              <a href={`#/campaigns/${c.id}`}>{c.name}<span className="muted">Keitaro #{c.keitaro_id}</span></a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
