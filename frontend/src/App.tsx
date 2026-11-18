import { useEffect, useState } from 'react'
import Creator from './Creator'
import Editor from './Editor'

// Две страницы, поэтому роутер не нужен: #/campaigns/5 — редактор, всё остальное — создаватор
export default function App() {
  const [hash, setHash] = useState(location.hash)
  useEffect(() => {
    const onChange = () => setHash(location.hash)
    addEventListener('hashchange', onChange)
    return () => removeEventListener('hashchange', onChange)
  }, [])

  const match = hash.match(/^#\/campaigns\/(\d+)$/)
  return <main>{match ? <Editor id={Number(match[1])} /> : <Creator />}</main>
}
