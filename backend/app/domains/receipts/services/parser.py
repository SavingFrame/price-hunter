import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import ClassVar

from pypdf import PdfReader


@dataclass(frozen=True)
class ParsedReceiptItem:
    line_number: int
    raw_name: str
    normalized_raw_name: str
    quantity: Decimal
    unit_of_measure: str | None
    unit_price_eur: Decimal | None
    line_total_eur: Decimal


@dataclass(frozen=True)
class ParsedReceipt:
    purchase_datetime: datetime | None
    total_eur: Decimal | None
    raw_text: str
    items: list[ParsedReceiptItem]


class ReceiptParserError(Exception):
    pass


class UnsupportedReceiptParserError(ReceiptParserError):
    pass


class ReceiptParser(ABC):
    retailer_keys: ClassVar[set[str]]

    async def parse(self, content: bytes) -> ParsedReceipt:
        raw_text = self.extract_pdf_text(content)
        return self.parse_text(raw_text)

    @abstractmethod
    def parse_text(self, raw_text: str) -> ParsedReceipt:
        pass

    def extract_pdf_text(self, content: bytes) -> str:
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def normalize_receipt_name(self, value: str) -> str:
        return self.normalize_spaces(value).lower()

    def normalize_spaces(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    def parse_decimal(self, value: str) -> Decimal:
        return Decimal(value.replace(".", "").replace(",", "."))


class SparReceiptParser(ReceiptParser):
    retailer_keys = {"spar", "interspar"}

    _purchase_datetime_pattern = re.compile(
        r"Vaša\s+kupnja\s+dana\s+"
        r"(?P<date>\d{2}\.\d{2}\.\d{4}\.)\s+u\s+"
        r"(?P<time>\d{2}:\d{2})\s+sati",
        re.IGNORECASE,
    )
    _total_pattern = re.compile(r"^UKUPNO\s+(?P<total>\d+[,]\d{2})$", re.IGNORECASE)
    _count_item_pattern = re.compile(
        r"^(?P<quantity>\d+)\s*x\s*"
        r"(?P<unit_price>\d+[,]\d{2})\s+"
        r"(?P<line_total>\d+[,]\d{2})\s+[A-Z]$",
    )
    _weighted_item_pattern = re.compile(
        r"^(?P<quantity>\d+[,]\d{3})\s*"
        r"(?P<unit>kg)\(N\)\s*x\s*"
        r"(?P<unit_price>\d+[,]\d{2})\s*EUR/kg\s+"
        r"(?P<line_total>\d+[,]\d{2})\s+[A-Z]$",
        re.IGNORECASE,
    )

    def parse_text(self, raw_text: str) -> ParsedReceipt:
        lines = self._normalize_lines(raw_text)
        purchase_datetime = self._parse_purchase_datetime(lines)
        total_eur = self._parse_total(lines)
        items = self._parse_items(lines)

        return ParsedReceipt(
            purchase_datetime=purchase_datetime,
            total_eur=total_eur,
            raw_text=raw_text,
            items=items,
        )

    def _normalize_lines(self, raw_text: str) -> list[str]:
        return [
            line
            for line in (self.normalize_spaces(line) for line in raw_text.splitlines())
            if line
        ]

    def _parse_purchase_datetime(self, lines: list[str]) -> datetime | None:
        for line in lines:
            match = self._purchase_datetime_pattern.search(line)
            if match is None:
                continue
            return datetime.strptime(
                f"{match.group('date')} {match.group('time')}",
                "%d.%m.%Y. %H:%M",
            )
        return None

    def _parse_total(self, lines: list[str]) -> Decimal | None:
        for line in lines:
            match = self._total_pattern.match(line)
            if match is not None:
                return self.parse_decimal(match.group("total"))
        return None

    def _parse_items(self, lines: list[str]) -> list[ParsedReceiptItem]:
        start_index = self._find_items_start(lines)
        end_index = self._find_items_end(lines, start_index)
        body = lines[start_index:end_index]

        items: list[ParsedReceiptItem] = []
        pending_name: str | None = None

        for line in body:
            if self._should_skip_item_body_line(line):
                continue

            count_match = self._count_item_pattern.match(line)
            weighted_match = self._weighted_item_pattern.match(line)

            if count_match is not None and pending_name is not None:
                items.append(
                    self._build_item_from_match(
                        line_number=len(items) + 1,
                        raw_name=pending_name,
                        quantity=count_match.group("quantity"),
                        unit_of_measure="kom",
                        unit_price_eur=count_match.group("unit_price"),
                        line_total_eur=count_match.group("line_total"),
                    ),
                )
                pending_name = None
                continue

            if weighted_match is not None and pending_name is not None:
                items.append(
                    self._build_item_from_match(
                        line_number=len(items) + 1,
                        raw_name=pending_name,
                        quantity=weighted_match.group("quantity"),
                        unit_of_measure=weighted_match.group("unit").lower(),
                        unit_price_eur=weighted_match.group("unit_price"),
                        line_total_eur=weighted_match.group("line_total"),
                    ),
                )
                pending_name = None
                continue

            pending_name = re.sub(r"\s+EUR$", "", line).strip()

        return items

    def _find_items_start(self, lines: list[str]) -> int:
        for index, line in enumerate(lines):
            if line.startswith("Vaša kupnja"):
                return index + 1
        raise ReceiptParserError("Could not find SPAR receipt item section")

    def _find_items_end(self, lines: list[str], start_index: int) -> int:
        for index in range(start_index, len(lines)):
            if lines[index].startswith("UKUPNO"):
                return index
        raise ReceiptParserError("Could not find SPAR receipt total line")

    def _should_skip_item_body_line(self, line: str) -> bool:
        return line.startswith("---") or line == "EUR"

    def _build_item_from_match(
        self,
        line_number: int,
        raw_name: str,
        quantity: str,
        unit_of_measure: str | None,
        unit_price_eur: str | None,
        line_total_eur: str,
    ) -> ParsedReceiptItem:
        return ParsedReceiptItem(
            line_number=line_number,
            raw_name=raw_name,
            normalized_raw_name=self.normalize_receipt_name(raw_name),
            quantity=self.parse_decimal(quantity),
            unit_of_measure=unit_of_measure,
            unit_price_eur=self.parse_decimal(unit_price_eur) if unit_price_eur else None,
            line_total_eur=self.parse_decimal(line_total_eur),
        )


PARSERS: tuple[ReceiptParser, ...] = (SparReceiptParser(),)


def get_receipt_parser(retailer_name: str) -> ReceiptParser:
    for parser in PARSERS:
        retailer_key = parser.normalize_spaces(retailer_name).lower()
        if retailer_key in parser.retailer_keys:
            return parser
    raise UnsupportedReceiptParserError(f"Unsupported receipt retailer: {retailer_name}")


async def parse_spar_receipt(content: bytes) -> ParsedReceipt:
    return await SparReceiptParser().parse(content)
