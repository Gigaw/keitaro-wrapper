# План: обёртка над Keitaro

Документ для проверки понимания задачи. Стек обязателен: FastAPI + SQLAlchemy. Сдача: публичный GitHub с README.

## Задача своими словами
1. **Создаватор.** Форма: название, ISO-код страны, ID оффера; домен, группа и источник трафика выбираются из списков, загруженных из Keitaro. Создаёт в Keitaro кампанию и два потока:
   - позиция 1 — посетители из страны → редирект на https://google.com;
   - позиция 2 — выбранный оффер, вес 100%.
   Кампания сохраняется в нашей БД и открывается в редакторе.
2. **Редактор** (повторяет существующее решение с видео) работает с черновиками офферов в потоках. В Keitaro ничего не уходит, пока не нажат Push. Веса пересчитываются автоматически, закреплённые (pin) не меняются, удалённые офферы архивируются (soft delete).

## Факты API, проверенные на стенде
- База `/admin_api/v1`, заголовок `Api-Key`. Спецификация: https://admin-api.docs.keitaro.io/openapi.json
- Списки: `GET /domains`, `GET /groups?type=campaigns` (без `type` → 400), `GET /traffic_sources`.
- Оффер: `GET /offers/{id}`. Чужой → 403, несуществующий → 404 (HTML от nginx, не JSON).
- Кампания: `POST /campaigns`, обязательные поля `name` и `alias` (alias генерируем сами).
- Поток: `POST /streams`, `GET /campaigns/{id}/streams`, `GET|PUT /streams/{id}`.
  - Редирект: `type=regular, schema=redirect, action_type=http, action_payload=URL, filters=[{name:"country", mode:"accept", payload:["AU"]}]`.
  - Офферы: `type=regular, schema=landings, action_type=http, offers=[{offer_id, share}]`.
- `PUT /streams/{id}` с `offers` **заменяет весь список** (`[]` удаляет все офферы). Если ключа `offers` нет, офферы не меняются.
- `share` — **только целое** (33.6 → ошибка «Share must be an integer»).
- `id` связи «поток–оффер» после PUT меняется, поэтому оффер в потоке идентифицируем по `offer_id`.
- Ключу доступны: 1 домен, 1 источник, 1 оффер (18813). Многооферные сценарии проверяются только тестами с моком.

## Модель данных (SQLite + Alembic)
- **Campaign**: id, keitaro_id, name, last_synced_at.
- **Stream**: id, keitaro_id, campaign_id, name, position, raw (JSON потока целиком; фильтры и редиректы не разбираем), last_synced_at.
- **StreamOffer**: id, stream_id, offer_keitaro_id, offer_name, share, published_share (null — ещё не опубликован), pinned, status ∈ `active | pending_add | pending_remove | removed`.
- «Жёлтый» поток не хранится, а вычисляется: есть `pending_*` или `share != published_share`.

## Переходы статусов оффера
| Действие | Что происходит |
|---|---|
| Fetch | офферы из Keitaro → active, share = published_share = значение из Keitaro; наш active, которого нет в Keitaro → removed. Поток с черновиком не трогаем, возвращаем предупреждение «сначала Push или Cancel» |
| Add | новый → pending_add; если оффер есть в архиве этого потока, это Bring Back |
| Delete | active → pending_remove (share 0); pending_add → запись удаляется |
| Bring Back | removed → pending_add |
| Cancel | pending_add удаляются; pending_remove → active; у всех share = published_share и pinned = published_pinned (pin в Keitaro не хранится; его состояние на момент Push хранится у нас) |
| Push | проверка конфликта: читаем поток из Keitaro, сравниваем пары (offer_id, share) с нашими active/pending_remove + published_share; расхождение → ошибка «сделайте Fetch». Иначе `PUT offers=[active + pending_add]`, затем pending_add → active, pending_remove → removed, published_share = share |
| Pin / Unpin, изменение веса закреплённого | пересчёт весов |

После каждого Add, Delete, Bring Back и Pin веса пересчитываются.

## Алгоритм весов (чистая функция, pytest)
- Участвуют только active и pending_add.
- Закреплённые не меняются; остаток `100 − сумма закреплённых` делится поровну между незакреплёнными.
- Целые числа: остаток от деления раздаётся по 1 первым по порядку (100/3 → 34/33/33). Сумма всегда ровно 100.
- Ошибки: сумма закреплённых > 100; все закреплены, а сумма ≠ 100; остаток 0 при наличии незакреплённых.

## Эндпоинты (FastAPI)
- `GET /api/options` — домены, группы, источники для формы.
- `GET /api/offers/{id}` — поиск оффера в Keitaro.
- `POST /api/campaigns` — создаватор; `GET /api/campaigns` — список; `GET /api/campaigns/{id}` — кампания с потоками и офферами.
- `POST /api/campaigns/{id}/fetch` — Fetch Streams.
- `POST /api/streams/{id}/offers` (add / bring back), `DELETE /api/stream-offers/{id}`, `POST /api/stream-offers/{id}/restore`, `PATCH /api/stream-offers/{id}` (pin + вес).
- `POST /api/streams/{id}/push`, `POST /api/streams/{id}/cancel`.
Каждый ответ, меняющий поток, возвращает поток целиком: фронт просто перерисовывает его.

## Фронт (React + TS, Vite, `frontend/`)
Тонкий: состояние хранится на бэкенде. Две страницы:
- создаватор;
- редактор: потоки; поток с черновиком жёлтый; оффер в pending_remove серый, вес 0%; архив с кнопкой Bring Back; кнопки Add, Delete, Pin, Push, Cancel, Fetch; ошибки бэкенда показываются текстом.

## Безопасность стенда
Правило для разработки, а не ограничение в коде: на стенде создаём и меняем только кампании с префиксом `test-`. Продукт работает с любой кампанией. Чужое только читаем. Ключ хранится только в `.env`.
Тестовая кампания на стенде: `test-igor-AU` (id 214493, потоки 1322578 и 1322579).

## Тесты
- pytest: функция весов (все ветки и ошибки);
- сервисы с замоканным Keitaro: fetch (в т.ч. оффер удалён в Keitaro → removed; поток с черновиком пропущен), add/delete/bring back/cancel/push, конфликт при push.
