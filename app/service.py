"""Логика создаватора и редактора. Функции меняют объекты в сессии; commit делает вызывающий код."""
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import keitaro
from app.models import ACTIVE, LIVE, PENDING_ADD, PENDING_REMOVE, REMOVED, Campaign, Stream, StreamOffer
from app.weights import WeightError, distribute


def create_campaign(db: Session, name: str, country: str, offer_id: int,
                    domain_id: int, group_id: int, traffic_source_id: int) -> Campaign:
    keitaro.get_offer(offer_id)  # проверяем оффер до того, как что-то создать
    kc = keitaro.create_campaign({
        "name": name,
        "alias": secrets.token_hex(6),  # обязателен в API, в URL кампании
        "domain_id": domain_id,
        "group_id": group_id,
        "traffic_source_id": traffic_source_id,
    })
    # shortcut: если поток не создастся, кампания останется в Keitaro без потоков; при частых сбоях — удалять её
    keitaro.create_stream({
        "campaign_id": kc["id"], "type": "regular", "name": f"Geo {country} -> Google", "position": 1,
        "schema": "redirect", "action_type": "http", "action_payload": "https://google.com",
        "filters": [{"name": "country", "mode": "accept", "payload": [country]}],
    })
    keitaro.create_stream({
        "campaign_id": kc["id"], "type": "regular", "name": "Offers", "position": 2,
        "schema": "landings", "action_type": "http",
        "offers": [{"offer_id": offer_id, "share": 100}],
    })
    campaign = Campaign(keitaro_id=kc["id"], name=kc["name"])
    db.add(campaign)
    db.commit()  # кампания уже есть в Keitaro: сохраняем её, даже если Fetch ниже упадёт
    fetch_streams(campaign)
    return campaign


def fetch_streams(campaign: Campaign) -> list[str]:
    """Загружает потоки из Keitaro. Потоки с черновиком не трогает. Возвращает предупреждения."""
    names = {o["id"]: o["name"] for o in keitaro.list_offers()}
    ours = {s.keitaro_id: s for s in campaign.streams}
    now = datetime.now(UTC)
    warnings = []
    for ks in keitaro.campaign_streams(campaign.keitaro_id):
        stream = ours.get(ks["id"])
        if stream is None:
            stream = Stream(keitaro_id=ks["id"])
            campaign.streams.append(stream)
        elif stream.dirty:
            warnings.append(f"Поток «{stream.name}» не обновлён: есть неопубликованные изменения, сначала Push или Cancel")
            continue
        stream.name, stream.position, stream.raw, stream.last_synced_at = ks["name"], ks["position"], ks, now
        _sync_offers(stream, ks["offers"], names)
    campaign.last_synced_at = now
    return warnings


def _sync_offers(stream: Stream, keitaro_offers: list[dict], names: dict[int, str]) -> None:
    """Приводит офферы потока к состоянию Keitaro. Офферов, которых там нет, переносит в архив."""
    ours = {o.offer_keitaro_id: o for o in stream.offers}
    for ko in keitaro_offers:
        offer = ours.pop(ko["offer_id"], None)
        if offer is None:
            offer = StreamOffer(offer_keitaro_id=ko["offer_id"], pinned=False, published_pinned=False)
            stream.offers.append(offer)
        offer.offer_name = names.get(ko["offer_id"]) or offer.offer_name or f"Offer {ko['offer_id']}"
        offer.status, offer.from_archive = ACTIVE, False
        offer.share = offer.published_share = ko["share"]
    for offer in ours.values():
        if offer.status != REMOVED:
            _archive(offer)


def _archive(offer: StreamOffer) -> None:
    offer.status, offer.share, offer.published_share = REMOVED, 0, None
    offer.pinned = offer.published_pinned = offer.from_archive = False


def _recalc(stream: Stream) -> None:
    live = [o for o in stream.offers if o.status in LIVE]
    try:
        shares = distribute([o.share if o.pinned else None for o in live])
    except WeightError as e:
        raise HTTPException(400, str(e))
    for offer, share in zip(live, shares):
        offer.share = share


def add_offer(stream: Stream, offer_id: int) -> None:
    if stream.raw.get("schema") != "landings":
        raise HTTPException(400, "В этот поток нельзя добавлять офферы: он не отправляет на офферы")
    existing = next((o for o in stream.offers if o.offer_keitaro_id == offer_id), None)
    if existing is None:
        offer = keitaro.get_offer(offer_id)
        stream.offers.append(StreamOffer(offer_keitaro_id=offer_id, offer_name=offer["name"], share=0,
                                         published_share=None, pinned=False, published_pinned=False,
                                         status=PENDING_ADD))
    elif existing.status in (REMOVED, PENDING_REMOVE):
        return bring_back(existing)
    else:
        raise HTTPException(400, f"Оффер {offer_id} уже есть в потоке")
    _recalc(stream)


def delete_offer(offer: StreamOffer) -> None:
    stream = offer.stream
    if offer.status == PENDING_ADD:
        _drop_pending_add(offer)
    elif offer.status == ACTIVE:
        offer.status, offer.share, offer.pinned = PENDING_REMOVE, 0, False
    else:
        raise HTTPException(400, "Оффер уже удалён")
    _recalc(stream)


def bring_back(offer: StreamOffer) -> None:
    if offer.status == REMOVED:
        offer.status, offer.from_archive = PENDING_ADD, True
    elif offer.status == PENDING_REMOVE:
        _revert(offer)
    else:
        raise HTTPException(400, "Оффер не удалён")
    _recalc(offer.stream)


def set_pin(offer: StreamOffer, pinned: bool, share: int | None) -> None:
    if offer.status not in LIVE:
        raise HTTPException(400, "Закрепить можно только оффер в потоке")
    if share is not None:
        if not 0 <= share <= 100:
            raise HTTPException(400, "Вес должен быть от 0 до 100")
        offer.share = share
    offer.pinned = pinned
    _recalc(offer.stream)


def cancel(stream: Stream) -> None:
    for offer in list(stream.offers):
        if offer.status == PENDING_ADD:
            _drop_pending_add(offer)
            continue
        if offer.status in (ACTIVE, PENDING_REMOVE):
            _revert(offer)


def _drop_pending_add(offer: StreamOffer) -> None:
    if offer.from_archive:
        _archive(offer)
    else:
        offer.stream.offers.remove(offer)  # новый оффер: в Keitaro его не было, хранить нечего


def _revert(offer: StreamOffer) -> None:
    """Возвращает опубликованный оффер к состоянию последнего Push/Fetch."""
    offer.status, offer.share, offer.pinned = ACTIVE, offer.published_share, offer.published_pinned


def push(stream: Stream) -> None:
    current = keitaro.get_stream(stream.keitaro_id)
    theirs = {o["offer_id"]: o["share"] for o in current["offers"]}
    published = {o.offer_keitaro_id: o.published_share for o in stream.offers if o.status in (ACTIVE, PENDING_REMOVE)}
    if theirs != published:
        raise HTTPException(409, "Поток изменили в Keitaro после последнего Fetch. "
                                 "Нажмите Cancel, затем Fetch Streams и повторите изменения.")
    _recalc(stream)  # страховка: веса могли разъехаться при параллельных запросах
    live = [o for o in stream.offers if o.status in LIVE]
    # Сохраняем state офферов в Keitaro (например, disabled), чтобы Push его не сбросил
    states = {o["offer_id"]: o["state"] for o in current["offers"]}
    updated = keitaro.update_stream_offers(stream.keitaro_id, [
        {"offer_id": o.offer_keitaro_id, "share": o.share, "state": states.get(o.offer_keitaro_id, "active")}
        for o in live
    ])
    stream.raw, stream.last_synced_at = updated, datetime.now(UTC)
    _sync_offers(stream, updated["offers"], {})
    for offer in stream.offers:
        offer.published_pinned = offer.pinned
