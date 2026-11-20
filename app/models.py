from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Статусы оффера в потоке
ACTIVE = "active"  # опубликован в Keitaro
PENDING_ADD = "pending_add"  # добавлен в черновике, в Keitaro его ещё нет
PENDING_REMOVE = "pending_remove"  # удалён в черновике, в Keitaro он ещё есть
REMOVED = "removed"  # архив: в Keitaro его нет
LIVE = (ACTIVE, PENDING_ADD)  # офферы, которые участвуют в весах и уйдут в Keitaro при Push


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str]
    last_synced_at: Mapped[datetime | None]

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign", order_by="Stream.position", cascade="all, delete-orphan"
    )


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(unique=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    name: Mapped[str]
    position: Mapped[int]
    raw: Mapped[dict] = mapped_column(JSON)  # поток из Keitaro как есть; фильтры и редиректы не разбираем
    last_synced_at: Mapped[datetime | None]

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream", order_by="StreamOffer.id", cascade="all, delete-orphan"
    )

    @property
    def dirty(self) -> bool:
        """Есть неопубликованные изменения (поток подсвечивается жёлтым)."""
        return any(o.status in (PENDING_ADD, PENDING_REMOVE) or o.share != o.published_share
                   or o.pinned != o.published_pinned
                   for o in self.offers if o.status != REMOVED)


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_keitaro_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id"))
    offer_keitaro_id: Mapped[int]
    offer_name: Mapped[str]
    share: Mapped[int]  # вес в черновике
    published_share: Mapped[int | None]  # вес в Keitaro; None, если оффера там нет
    pinned: Mapped[bool] = mapped_column(default=False)
    published_pinned: Mapped[bool] = mapped_column(default=False, server_default="0")  # pin на момент Push; к нему откатывает Cancel
    status: Mapped[str] = mapped_column(String(20))
    # pending_add, вернувшийся из архива: Cancel/Delete возвращают его в архив, а не удаляют запись
    from_archive: Mapped[bool] = mapped_column(default=False, server_default="0")

    stream: Mapped[Stream] = relationship(back_populates="offers")
