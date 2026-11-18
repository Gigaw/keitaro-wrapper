from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import keitaro, service
from app.db import get_db
from app.models import Campaign, Stream, StreamOffer

app = FastAPI(title="Keitaro wrapper")


@app.exception_handler(keitaro.KeitaroError)
def keitaro_error(request: Request, e: keitaro.KeitaroError):
    # 4xx от Keitaro — проблема в запросе (показываем как есть), остальное — сбой Keitaro
    status = e.status if e.status and e.status < 500 else 502
    return JSONResponse({"detail": str(e)}, status_code=status)


def campaign_out(c: Campaign) -> dict:
    return {"id": c.id, "keitaro_id": c.keitaro_id, "name": c.name, "last_synced_at": c.last_synced_at,
            "streams": [stream_out(s) for s in c.streams]}


def stream_out(s: Stream) -> dict:
    return {
        "id": s.id, "keitaro_id": s.keitaro_id, "name": s.name, "position": s.position, "raw": s.raw,
        "last_synced_at": s.last_synced_at, "dirty": s.dirty,
        "offers": [{"id": o.id, "offer_keitaro_id": o.offer_keitaro_id, "offer_name": o.offer_name,
                    "share": o.share, "published_share": o.published_share, "pinned": o.pinned,
                    "status": o.status} for o in s.offers],
    }


def get_or_404(db: Session, model, id: int):
    obj = db.get(model, id)
    if obj is None:
        raise HTTPException(404, "Не найдено")
    return obj


@app.get("/api/options")
def options():
    pick = lambda items: [{"id": i["id"], "name": i["name"]} for i in items]
    return {"domains": pick(keitaro.list_domains()), "groups": pick(keitaro.list_groups()),
            "traffic_sources": pick(keitaro.list_traffic_sources())}


@app.get("/api/offers/{offer_id}")
def find_offer(offer_id: int):
    offer = keitaro.get_offer(offer_id)
    return {"id": offer["id"], "name": offer["name"]}


class CampaignIn(BaseModel):
    name: str = Field(min_length=1)
    country: str = Field(pattern="^[A-Z]{2}$")
    offer_id: int
    domain_id: int
    group_id: int
    traffic_source_id: int


@app.post("/api/campaigns")
def create_campaign(data: CampaignIn, db: Session = Depends(get_db)):
    campaign = service.create_campaign(db, **data.model_dump())
    db.commit()
    return campaign_out(campaign)


@app.get("/api/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    return [{"id": c.id, "keitaro_id": c.keitaro_id, "name": c.name}
            for c in db.scalars(select(Campaign).order_by(Campaign.id.desc()))]


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    return campaign_out(get_or_404(db, Campaign, campaign_id))


@app.post("/api/campaigns/{campaign_id}/fetch")
def fetch_streams(campaign_id: int, db: Session = Depends(get_db)):
    campaign = get_or_404(db, Campaign, campaign_id)
    warnings = service.fetch_streams(campaign)
    db.commit()
    return {"campaign": campaign_out(campaign), "warnings": warnings}


class AddOfferIn(BaseModel):
    offer_id: int


@app.post("/api/streams/{stream_id}/offers")
def add_offer(stream_id: int, data: AddOfferIn, db: Session = Depends(get_db)):
    stream = get_or_404(db, Stream, stream_id)
    service.add_offer(stream, data.offer_id)
    db.commit()
    return stream_out(stream)


@app.post("/api/streams/{stream_id}/push")
def push(stream_id: int, db: Session = Depends(get_db)):
    stream = get_or_404(db, Stream, stream_id)
    service.push(stream)
    db.commit()
    return stream_out(stream)


@app.post("/api/streams/{stream_id}/cancel")
def cancel(stream_id: int, db: Session = Depends(get_db)):
    stream = get_or_404(db, Stream, stream_id)
    service.cancel(stream)
    db.commit()
    return stream_out(stream)


@app.delete("/api/stream-offers/{offer_id}")
def delete_offer(offer_id: int, db: Session = Depends(get_db)):
    offer = get_or_404(db, StreamOffer, offer_id)
    stream = offer.stream
    service.delete_offer(offer)
    db.commit()
    return stream_out(stream)


@app.post("/api/stream-offers/{offer_id}/restore")
def bring_back(offer_id: int, db: Session = Depends(get_db)):
    offer = get_or_404(db, StreamOffer, offer_id)
    service.bring_back(offer)
    db.commit()
    return stream_out(offer.stream)


class PinIn(BaseModel):
    pinned: bool
    share: int | None = None


@app.patch("/api/stream-offers/{offer_id}")
def pin(offer_id: int, data: PinIn, db: Session = Depends(get_db)):
    offer = get_or_404(db, StreamOffer, offer_id)
    service.set_pin(offer, data.pinned, data.share)
    db.commit()
    return stream_out(offer.stream)
