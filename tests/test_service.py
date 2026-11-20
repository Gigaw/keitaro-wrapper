import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import keitaro, service
from app.models import ACTIVE, PENDING_ADD, PENDING_REMOVE, REMOVED, Base, Campaign

OFFER_NAMES = {1: "Offer A", 2: "Offer B", 3: "Offer C", 4: "Offer D"}


class FakeKeitaro:
    """Keitaro в памяти: одна кампания 10, поток 100 с офферами и редирект-поток 99."""

    def __init__(self, monkeypatch):
        self.streams = {
            99: {"id": 99, "name": "Geo AU", "position": 1, "schema": "redirect", "offers": [],
                 "filters": [{"name": "country", "mode": "accept", "payload": ["AU"]}]},
            100: {"id": 100, "name": "Offers", "position": 2, "schema": "landings",
                  "offers": [{"offer_id": i, "share": s, "state": "active"} for i, s in [(1, 34), (2, 33), (3, 33)]]},
        }
        self.pushed = []
        monkeypatch.setattr(keitaro, "list_offers", lambda: [{"id": k, "name": v} for k, v in OFFER_NAMES.items()])
        monkeypatch.setattr(keitaro, "get_offer", self.get_offer)
        monkeypatch.setattr(keitaro, "campaign_streams", lambda cid: list(self.streams.values()))
        monkeypatch.setattr(keitaro, "get_campaign", lambda cid: {"id": cid, "name": "existing"})
        monkeypatch.setattr(keitaro, "get_stream", lambda sid: self.streams[sid])
        monkeypatch.setattr(keitaro, "update_stream_offers", self.update_stream_offers)

    def get_offer(self, offer_id):
        if offer_id not in OFFER_NAMES:
            raise keitaro.KeitaroError("not found", 404)
        return {"id": offer_id, "name": OFFER_NAMES[offer_id]}

    def update_stream_offers(self, sid, offers):
        self.pushed.append(offers)
        self.streams[sid] = {**self.streams[sid], "offers": offers}
        return self.streams[sid]


@pytest.fixture
def fake(monkeypatch):
    return FakeKeitaro(monkeypatch)


@pytest.fixture
def campaign(fake):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        c = Campaign(keitaro_id=10, name="test-c")
        db.add(c)
        service.fetch_streams(c)
        db.commit()
        yield c


def offers_stream(c):
    return next(s for s in c.streams if s.keitaro_id == 100)


def state(stream):
    """{offer_id: (status, share)} — удобно сравнивать целиком."""
    return {o.offer_keitaro_id: (o.status, o.share) for o in stream.offers}


def by_id(stream, offer_id):
    return next(o for o in stream.offers if o.offer_keitaro_id == offer_id)


def test_fetch_stores_all_streams_and_offers(campaign):
    assert [s.name for s in campaign.streams] == ["Geo AU", "Offers"]
    assert campaign.streams[0].raw["filters"][0]["payload"] == ["AU"]
    s = offers_stream(campaign)
    assert state(s) == {1: (ACTIVE, 34), 2: (ACTIVE, 33), 3: (ACTIVE, 33)}
    assert by_id(s, 1).offer_name == "Offer A"
    assert not s.dirty


def test_add_offer_recalculates_to_25(campaign):
    s = offers_stream(campaign)
    service.add_offer(s, 4)
    assert state(s) == {1: (ACTIVE, 25), 2: (ACTIVE, 25), 3: (ACTIVE, 25), 4: (PENDING_ADD, 25)}
    assert s.dirty


def test_add_unknown_offer_fails(campaign):
    with pytest.raises(keitaro.KeitaroError):
        service.add_offer(offers_stream(campaign), 999)


def test_add_offer_to_redirect_stream_fails(campaign):
    with pytest.raises(HTTPException):
        service.add_offer(campaign.streams[0], 4)


def test_pin_keeps_share(campaign):
    s = offers_stream(campaign)
    service.set_pin(by_id(s, 1), True, 25)
    assert state(s) == {1: (ACTIVE, 25), 2: (ACTIVE, 38), 3: (ACTIVE, 37)}
    service.add_offer(s, 4)
    assert state(s)[1] == (ACTIVE, 25)
    assert [state(s)[i][1] for i in (2, 3, 4)] == [25, 25, 25]
    service.delete_offer(by_id(s, 2))
    assert state(s) == {1: (ACTIVE, 25), 2: (PENDING_REMOVE, 0), 3: (ACTIVE, 38), 4: (PENDING_ADD, 37)}


def test_pin_over_100_fails(campaign):
    s = offers_stream(campaign)
    service.set_pin(by_id(s, 1), True, 60)
    with pytest.raises(HTTPException):
        service.set_pin(by_id(s, 2), True, 50)


def test_delete_active_and_pending_add(campaign):
    s = offers_stream(campaign)
    service.add_offer(s, 4)
    service.delete_offer(by_id(s, 4))  # черновик просто исчезает
    assert 4 not in state(s)
    service.delete_offer(by_id(s, 1))
    assert state(s) == {1: (PENDING_REMOVE, 0), 2: (ACTIVE, 50), 3: (ACTIVE, 50)}


def test_cancel_reverts_everything(campaign):
    s = offers_stream(campaign)
    service.add_offer(s, 4)
    service.delete_offer(by_id(s, 1))
    service.cancel(s)
    assert state(s) == {1: (ACTIVE, 34), 2: (ACTIVE, 33), 3: (ACTIVE, 33)}
    assert not s.dirty


def test_push_then_bring_back(campaign, fake):
    s = offers_stream(campaign)
    service.delete_offer(by_id(s, 1))
    service.add_offer(s, 4)
    service.push(s)
    assert fake.pushed[-1] == [{"offer_id": i, "share": sh, "state": "active"} for i, sh in [(2, 34), (3, 33), (4, 33)]]
    assert state(s) == {1: (REMOVED, 0), 2: (ACTIVE, 34), 3: (ACTIVE, 33), 4: (ACTIVE, 33)}
    assert not s.dirty

    service.bring_back(by_id(s, 1))
    assert state(s) == {1: (PENDING_ADD, 25), 2: (ACTIVE, 25), 3: (ACTIVE, 25), 4: (ACTIVE, 25)}
    service.push(s)
    assert state(s)[1] == (ACTIVE, 25)


def test_push_detects_conflict(campaign, fake):
    s = offers_stream(campaign)
    service.add_offer(s, 4)
    fake.streams[100]["offers"][0]["share"] = 50  # кто-то поменял вес прямо в Keitaro
    with pytest.raises(HTTPException) as e:
        service.push(s)
    assert e.value.status_code == 409
    assert fake.pushed == []


def test_fetch_archives_offer_removed_in_keitaro(campaign, fake):
    fake.streams[100]["offers"] = [{"offer_id": 2, "share": 100, "state": "active"}]
    service.fetch_streams(campaign)
    s = offers_stream(campaign)
    assert state(s) == {1: (REMOVED, 0), 2: (ACTIVE, 100), 3: (REMOVED, 0)}


def test_fetch_skips_dirty_stream(campaign, fake):
    s = offers_stream(campaign)
    service.add_offer(s, 4)
    fake.streams[100]["offers"] = []
    warnings = service.fetch_streams(campaign)
    assert len(warnings) == 1
    assert state(s)[4] == (PENDING_ADD, 25)
    assert state(s)[1] == (ACTIVE, 25)


def test_cancel_reverts_pin(campaign):
    s = offers_stream(campaign)
    service.set_pin(by_id(s, 3), True, 25)
    service.cancel(s)
    assert state(s) == {1: (ACTIVE, 34), 2: (ACTIVE, 33), 3: (ACTIVE, 33)}
    assert not by_id(s, 3).pinned
    service.add_offer(s, 4)
    assert [state(s)[i][1] for i in (1, 2, 3, 4)] == [25, 25, 25, 25]


def test_pin_survives_push_and_delete_cancel(campaign):
    s = offers_stream(campaign)
    service.set_pin(by_id(s, 3), True, 25)
    service.push(s)
    service.delete_offer(by_id(s, 3))
    assert state(s) == {1: (ACTIVE, 50), 2: (ACTIVE, 50), 3: (PENDING_REMOVE, 0)}
    service.bring_back(by_id(s, 3))
    assert state(s) == {1: (ACTIVE, 38), 2: (ACTIVE, 37), 3: (ACTIVE, 25)}
    assert by_id(s, 3).pinned
    service.delete_offer(by_id(s, 3))
    service.cancel(s)
    assert state(s) == {1: (ACTIVE, 38), 2: (ACTIVE, 37), 3: (ACTIVE, 25)}
    assert by_id(s, 3).pinned and not s.dirty


def test_push_refuses_broken_weights(campaign, fake):
    s = offers_stream(campaign)
    service.add_offer(s, 4)
    by_id(s, 4).share = 50  # как после гонки двух параллельных запросов
    with pytest.raises(HTTPException):
        service.push(s)
    assert fake.pushed == []


def test_pin_without_share_change_is_a_draft(campaign, fake):
    s = offers_stream(campaign)
    service.set_pin(by_id(s, 3), True, None)  # закрепили на текущих 33%
    assert s.dirty
    service.push(s)
    assert not s.dirty
    service.add_offer(s, 4)
    service.cancel(s)
    assert by_id(s, 3).pinned
    assert state(s) == {1: (ACTIVE, 34), 2: (ACTIVE, 33), 3: (ACTIVE, 33)}


def test_cancel_and_delete_return_brought_back_offer_to_archive(campaign):
    s = offers_stream(campaign)
    service.delete_offer(by_id(s, 1))
    service.push(s)
    service.bring_back(by_id(s, 1))
    service.cancel(s)
    assert state(s)[1] == (REMOVED, 0)
    service.bring_back(by_id(s, 1))
    service.delete_offer(by_id(s, 1))
    assert state(s)[1] == (REMOVED, 0)
    assert not s.dirty


def test_import_existing_campaign_is_idempotent(fake):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        imported = service.import_campaign(db, 77)
        db.commit()
        assert imported.name == "existing"
        assert state(offers_stream(imported)) == {1: (ACTIVE, 34), 2: (ACTIVE, 33), 3: (ACTIVE, 33)}
        assert service.import_campaign(db, 77) is imported
