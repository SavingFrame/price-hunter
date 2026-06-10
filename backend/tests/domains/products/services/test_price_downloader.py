import httpx
import pytest

from app.domains.products.retailers import RetailerEnum
from app.domains.products.services import price_downloader
from app.domains.products.services.price_downloader import (
    KauflandPriceDownloader,
    LidlPriceArchive,
    LidlPriceDownloader,
    StorePriceCsvNotFound,
)
from app.domains.products.stores import Store


def make_kaufland_store() -> Store:
    return Store(
        retailer_id=RetailerEnum.KAUFLAND.value.id,
        store_code="5930",
        name="Kaufland Jablanska 80",
        prefix="Hipermarket_Jablanska_ulica_br_80_Zagreb_5930_",
    )


def test_kaufland_store_match_allows_spaces_around_date_in_label():
    label = "Hipermarket_Jablanska_ulica_br_80_Zagreb_5930_ 13032026 _7-30.csv"

    assert KauflandPriceDownloader._matches_store(label, make_kaufland_store())


def test_kaufland_store_match_falls_back_to_store_code():
    label = "Hipermarket_Jablanska_ulica_br_80_Zagreb_5930_13032026_7-30.csv"
    store = make_kaufland_store()
    store.prefix = ""

    assert KauflandPriceDownloader._matches_store(label, store)


class FailingOnceClient:
    def __init__(self):
        self.calls = 0

    def get(self, url: str):
        self.calls += 1
        if self.calls == 1:
            raise httpx.RemoteProtocolError(
                "peer closed connection without sending complete message body"
            )
        return httpx.Response(200, request=httpx.Request("GET", url))


def test_get_with_retries_retries_incomplete_response_body():
    client = FailingOnceClient()

    response = price_downloader._get_with_retries(
        client, "https://example.com/file.zip"
    )

    assert response.status_code == 200
    assert client.calls == 2


class AlwaysFailingClient:
    def __init__(self):
        self.calls = 0

    def get(self, url: str):
        self.calls += 1
        raise httpx.ReadTimeout("The read operation timed out")


def test_get_with_retries_raises_after_retry_limit():
    client = AlwaysFailingClient()

    with pytest.raises(httpx.ReadTimeout):
        price_downloader._get_with_retries(client, "https://example.com/file.zip")

    assert client.calls == price_downloader.PRICE_DOWNLOAD_RETRIES


def test_kaufland_empty_price_list_is_downloaded_but_has_no_files():
    downloader = KauflandPriceDownloader()
    downloader._downloaded_prices = []

    assert not downloader.has_price_files
    with pytest.raises(StorePriceCsvNotFound, match="No price CSV files"):
        downloader.download_price_csv_for_store(make_kaufland_store())


def test_lidl_missing_store_file_raises_store_not_found():
    downloader = LidlPriceDownloader()
    downloader._downloaded_prices = LidlPriceArchive(
        files=["Supermarket 209_Risnjačka ulica_1_10000_Zagreb_1_26.04.2026_7.15h.csv"],
        archive_content=b"not used",
    )
    store = Store(
        retailer_id=RetailerEnum.LIDL.value.id,
        store_code="250",
        name="Lidl Ljubljanska avenija",
        prefix="Supermarket 250_Ljubljanska avenija_2_10090_Zagreb_",
    )

    assert downloader.has_price_files
    with pytest.raises(StorePriceCsvNotFound, match="Supermarket 250"):
        downloader.download_price_csv_for_store(store)
