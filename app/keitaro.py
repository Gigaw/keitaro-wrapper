"""Тонкий клиент Keitaro Admin API: https://admin-api.docs.keitaro.io/"""
import os

import httpx


class KeitaroError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _request(method: str, path: str, json: dict | None = None):
    url = f"{os.environ['KEITARO_URL'].rstrip('/')}/admin_api/v1/{path}"
    try:
        r = httpx.request(method, url, json=json, headers={"Api-Key": os.environ["KEITARO_API_KEY"]}, timeout=30)
    except httpx.HTTPError as e:
        raise KeitaroError(f"Keitaro недоступен: {e}")
    if r.is_error:
        # На 404 nginx отдаёт HTML, а не JSON
        detail = r.json() if "json" in r.headers.get("content-type", "") else r.reason_phrase
        raise KeitaroError(f"Keitaro ответил {r.status_code}: {detail}", r.status_code)
    try:
        return r.json()
    except ValueError:
        raise KeitaroError(f"Keitaro вернул не JSON (статус {r.status_code})")


def list_domains():
    return _request("GET", "domains")


def list_groups():
    return _request("GET", "groups?type=campaigns")


def list_traffic_sources():
    return _request("GET", "traffic_sources")


def list_offers():
    return _request("GET", "offers")


def get_offer(offer_id: int):
    try:
        return _request("GET", f"offers/{offer_id}")
    except KeitaroError as e:
        if e.status in (403, 404):
            raise KeitaroError(f"Оффер {offer_id} не найден или нет доступа", 404)
        raise


def create_campaign(data: dict):
    return _request("POST", "campaigns", data)


def create_stream(data: dict):
    return _request("POST", "streams", data)


def get_campaign(campaign_id: int):
    return _request("GET", f"campaigns/{campaign_id}")


def campaign_streams(campaign_id: int):
    return _request("GET", f"campaigns/{campaign_id}/streams")


def get_stream(stream_id: int):
    return _request("GET", f"streams/{stream_id}")


def update_stream_offers(stream_id: int, offers: list[dict]):
    # Keitaro заменяет весь список офферов потока на переданный (проверено на стенде)
    return _request("PUT", f"streams/{stream_id}", {"offers": offers})
