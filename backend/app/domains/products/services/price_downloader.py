import abc
import csv
import datetime
import io
import logging
import re
import zipfile
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field

from app.models.store import Store

logger = logging.getLogger(__name__)

PRICE_DOWNLOAD_RETRIES = 3
PRICE_DOWNLOAD_TIMEOUT = httpx.Timeout(180.0, connect=10.0)


class StorePriceCsvNotFound(ValueError):
    pass


class BasePriceDownloader(abc.ABC):
    def __init__(self):
        self._downloaded_prices = None

    @property
    def has_price_files(self) -> bool:
        return self._downloaded_prices is not None and bool(self._downloaded_prices)

    @abc.abstractmethod
    def download_prices_list(self, date: datetime.date) -> None: ...

    @abc.abstractmethod
    def download_price_csv_for_store(self, store: Store) -> csv.DictReader: ...


class SparkPriceListItem(BaseModel):
    name: str
    url: str = Field(alias="URL")


class SparkPriceListResponse(BaseModel):
    files: list[SparkPriceListItem]
    count: int


class LidlPriceListItem(BaseModel):
    date: datetime.date
    url: str


class KauflandPriceListItem(BaseModel):
    label: str
    path: str

    @property
    def url(self) -> str:
        return urljoin(KauflandPriceDownloader.prices_base_url, self.path)


class LidlPriceArchive(BaseModel):
    files: list[str]
    archive_content: bytes


def _get_with_retries(client: httpx.Client, url: str) -> httpx.Response:
    for attempt in range(1, PRICE_DOWNLOAD_RETRIES + 1):
        try:
            return client.get(url)
        except httpx.TransportError:
            if attempt == PRICE_DOWNLOAD_RETRIES:
                raise
            logger.warning(
                "Transient error while downloading %s, retrying (%s/%s).",
                url,
                attempt,
                PRICE_DOWNLOAD_RETRIES,
                exc_info=True,
            )
    raise RuntimeError("unreachable")


class SparPriceDownloader(BasePriceDownloader):
    def download_prices_list(self, date: datetime.date) -> None:
        with httpx.Client(timeout=PRICE_DOWNLOAD_TIMEOUT) as client:
            date_str = date.strftime("%Y%m%d")
            response = _get_with_retries(
                client,
                f"https://www.spar.hr/datoteke_cjenici/Cjenik{date_str}.json",
            )
            response.raise_for_status()
            price_list_response = SparkPriceListResponse.model_validate_json(
                response.text
            )
            self._downloaded_prices = price_list_response.files

    def download_price_csv_for_store(self, store: Store) -> csv.DictReader:
        if self._downloaded_prices is None:
            raise RuntimeError(
                "Price list not downloaded yet. Call download_prices_list first."
            )
        if not self._downloaded_prices:
            raise StorePriceCsvNotFound("No price CSV files are available.")
        price_list_item = next(
            (
                price_list_item
                for price_list_item in self._downloaded_prices
                if price_list_item.name.startswith(store.prefix)
            ),
            None,
        )
        if not price_list_item:
            raise StorePriceCsvNotFound(
                f"Price list for store with prefix {store.prefix} not found."
            )
        with httpx.Client(timeout=PRICE_DOWNLOAD_TIMEOUT) as client:
            response = _get_with_retries(client, price_list_item.url)
            response.raise_for_status()
            # Spar CSV files are Windows-1250 encoded and semicolon-delimited.
            csv_text = response.content.decode("cp1250")
            reader = csv.DictReader(csv_text.splitlines(), delimiter=";")
        return reader


class KauflandPriceDownloader(BasePriceDownloader):
    prices_base_url = "https://www.kaufland.hr"
    price_list_url = f"{prices_base_url}/akcije-novosti/popis-mpc.assetSearch.id=assetList_1599847924.json"

    def download_prices_list(self, date: datetime.date) -> None:
        with httpx.Client(timeout=PRICE_DOWNLOAD_TIMEOUT) as client:
            response = _get_with_retries(client, self.price_list_url)
            response.raise_for_status()
            price_list_items = [
                KauflandPriceListItem.model_validate(item) for item in response.json()
            ]
        date_str = date.strftime("%d%m%Y")
        self._downloaded_prices = [
            item for item in price_list_items if date_str in item.label.replace(" ", "")
        ]

    def download_price_csv_for_store(self, store: Store) -> csv.DictReader:
        if self._downloaded_prices is None:
            raise RuntimeError(
                "Price list not downloaded yet. Call download_prices_list first."
            )
        if not self._downloaded_prices:
            raise StorePriceCsvNotFound("No price CSV files are available.")
        price_list_item = next(
            (
                item
                for item in self._downloaded_prices
                if self._matches_store(item.label, store)
            ),
            None,
        )
        if not price_list_item:
            raise StorePriceCsvNotFound(
                f"Price list for store with prefix {store.prefix} or code {store.store_code} not found."
            )
        with httpx.Client(timeout=PRICE_DOWNLOAD_TIMEOUT) as client:
            response = _get_with_retries(client, price_list_item.url)
            response.raise_for_status()
            csv_text = response.content.decode("utf-8-sig")
        return csv.DictReader(csv_text.splitlines(), delimiter="\t")

    @staticmethod
    def _matches_store(label: str, store: Store) -> bool:
        normalized_label = label.replace(" ", "")
        if store.prefix and normalized_label.startswith(store.prefix.replace(" ", "")):
            return True
        return f"_{store.store_code}_" in normalized_label


class LidlPriceDownloader(BasePriceDownloader):
    prices_page_url = "https://tvrtka.lidl.hr/cijene"
    _price_link_pattern = re.compile(r"href=[\"']([^\"']+\.zip)[\"']", re.IGNORECASE)
    _date_pattern = re.compile(r"(\d{2})[._](\d{2})[._](\d{4})")

    @property
    def has_price_files(self) -> bool:
        if self._downloaded_prices is None:
            return False
        archive = LidlPriceArchive.model_validate(self._downloaded_prices)
        return bool(archive.files)

    def download_prices_list(self, date: datetime.date) -> None:
        with httpx.Client(
            follow_redirects=True,
            timeout=PRICE_DOWNLOAD_TIMEOUT,
        ) as client:
            response = _get_with_retries(client, self.prices_page_url)
            response.raise_for_status()
            price_list_items = self._parse_price_list(response.text)
            price_list_item = next(
                (item for item in price_list_items if item.date == date),
                None,
            )
            if not price_list_item:
                raise ValueError(f"Lidl price archive for date {date} not found.")

            archive_response = _get_with_retries(client, price_list_item.url)
            archive_response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
                files = [
                    info.filename for info in archive.infolist() if not info.is_dir()
                ]
            self._downloaded_prices = LidlPriceArchive(
                files=files,
                archive_content=archive_response.content,
            )

    def download_price_csv_for_store(self, store: Store) -> csv.DictReader:
        if self._downloaded_prices is None:
            raise RuntimeError(
                "Price list not downloaded yet. Call download_prices_list first."
            )
        archive = LidlPriceArchive.model_validate(self._downloaded_prices)
        store_file = self._find_store_file(archive.files, store)
        if not store_file:
            raise StorePriceCsvNotFound(
                f"Price list for store with prefix {store.prefix} or code {store.store_code} not found."
            )

        with zipfile.ZipFile(io.BytesIO(archive.archive_content)) as zip_archive:
            csv_text = zip_archive.read(store_file).decode("cp1250")
        return csv.DictReader(csv_text.splitlines(), delimiter=",")

    def _parse_price_list(self, html: str) -> list[LidlPriceListItem]:
        price_list_items = []
        for match in self._price_link_pattern.finditer(html):
            url = urljoin(self.prices_page_url, match.group(1))
            date_match = self._date_pattern.search(url)
            if not date_match:
                continue
            day, month, year = date_match.groups()
            price_list_items.append(
                LidlPriceListItem(
                    date=datetime.date(int(year), int(month), int(day)),
                    url=url,
                )
            )
        return price_list_items

    def _find_store_file(self, files: list[str], store: Store) -> str | None:
        if store.prefix:
            store_file = next(
                (file for file in files if file.startswith(store.prefix)),
                None,
            )
            if store_file:
                return store_file

        store_code_prefix = f"Supermarket {store.store_code}_"
        return next(
            (file for file in files if file.startswith(store_code_prefix)),
            None,
        )
