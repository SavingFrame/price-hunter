import uuid
from decimal import Decimal

from sqlalchemy import bindparam, case, func, literal, or_, true
from sqlalchemy import select as sa_select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.common import get_datetime_utc
from app.models.price_observation import PriceObservation
from app.models.product import Product
from app.models.product_alias import ProductAlias, ProductAliasSource
from app.models.receipt import ReceiptItem  # noqa: F401
from app.services.receipts.parser import ParsedReceiptItem


class ReceiptProductMatcher:
    """Match parsed receipt names to canonical products.

    Receipt lines are usually short, abbreviated, and retailer-specific. For example,
    SPAR can print `TJ.BARILLA PIPE RI.500 g` while the catalog product is named
    `Barilla pipe rigate n.91 500 g`. This matcher compares two receipt-name forms
    against product aliases and product names: the stored normalized receipt name and
    an expanded receipt name with known retailer abbreviations replaced.

    The database does most of the work with PostgreSQL trigram functions:

    1. Build alias candidates for the receipt retailer and global aliases.
    2. Score candidates by text similarity, exact alias match, alias source, retailer,
       and latest observed price.
    3. Keep only the best alias row per product.
    4. Return the best product only if it is confidently matched.

    Bags and other noisy receipt lines should usually fall below the acceptance score,
    which leaves them for user review or skipping.
    """

    # Minimum final score for an automatic match. Exact alias matches bypass this,
    # because a saved alias is already treated as trusted product knowledge.
    accept_score = 0.85

    # pg_trgm `%` uses the session's `pg_trgm.similarity_threshold`. We set it to
    # this value before each match query so Postgres can use the trigram index as an
    # early prefilter. The final acceptance threshold is applied after full scoring.
    candidate_score_threshold = Decimal("0.18")
    candidate_limit = 30

    # Retailer receipt abbreviations. This does not change the stored raw name. It
    # only creates a second, expanded query string for matching.
    receipt_name_replacements = {
        "TJ.": "tjestenina ",
        "TJE.": "tjestenina ",
        "TJES.": "tjestenina ",
        "TJEST.": "tjestenina ",
        "JOG.": "jogurt ",
        "JOGU.": "jogurt ",
        "MLIJ.SV.": "mlijeko svježe ",
        "MLIJ.": "mlijeko ",
        "SV.": "svježe ",
        "VRH.ZA": "vrhnje za ",
        "KUH.": "kuhanje ",
        "POD.UZ.M": "podni uzgoj m",
        "POD.": "podravka ",
        "SW.CHIL.ASIA": "sweet chili asia",
        "SW.CHILI": "sweet chili",
        "IN.JUHA": "instant juha",
        "KRIST.": "kristal",
        "UZ.M": "uzgoj m",
        "JAG/CR.RIBIZ": "jagoda crni ribiz",
        "CR.RIBIZ": "crni ribiz",
        "RI.": "rigate ",
    }

    async def find_matching_product(
        self,
        session: AsyncSession,
        retailer_id: uuid.UUID,
        parsed_item: ParsedReceiptItem,
    ) -> Product | None:
        """Return the best automatic product match for a parsed receipt item.

        The method intentionally returns only one product or `None`. Candidate display
        for manual review should use a separate method later, because review UI needs
        lower-confidence candidates and explanation fields.
        """
        await self._set_similarity_threshold(session)
        row = (await session.exec(
            self._build_product_match_statement().params(
                stored_receipt_name=parsed_item.normalized_raw_name,
                expanded_receipt_name=self.expand_receipt_name(parsed_item.raw_name),
                unit_price=parsed_item.unit_price_eur,
                line_total=parsed_item.line_total_eur,
                retailer_id=retailer_id,
            ),
        )).first()
        if row is None:
            return None

        if float(row.exact_score) <= 0 and float(row.score) < self.accept_score:
            return None

        return await session.get(Product, row.product_id)

    async def create_or_update_product_alias(
        self,
        session: AsyncSession,
        retailer_id: uuid.UUID,
        parsed_item: ParsedReceiptItem,
        product: Product,
    ) -> ProductAlias:
        """Persist the receipt name as a retailer-specific alias for future receipts."""
        statement = select(ProductAlias).where(
            ProductAlias.product_id == product.id,
            ProductAlias.retailer_id == retailer_id,
            ProductAlias.normalized_alias_name == parsed_item.normalized_raw_name,
            ProductAlias.retailer_product_code.is_(None),
            ProductAlias.source == ProductAliasSource.RECEIPT,
        )
        alias = (await session.exec(statement)).first()
        if alias is None:
            alias = ProductAlias(
                product_id=product.id,
                retailer_id=retailer_id,
                alias_name=parsed_item.raw_name,
                normalized_alias_name=parsed_item.normalized_raw_name,
                retailer_product_code=None,
                source=ProductAliasSource.RECEIPT,
            )
        else:
            alias.alias_name = parsed_item.raw_name
            alias.last_seen_at = get_datetime_utc()

        session.add(alias)
        return alias

    def expand_receipt_name(self, value: str) -> str:
        """Expand known receipt abbreviations into a better search query."""
        result = value
        for source, target in self.receipt_name_replacements.items():
            result = result.replace(source, target)
        return " ".join(result.lower().split())

    async def _set_similarity_threshold(self, session: AsyncSession) -> None:
        """Set pg_trgm's `%` threshold for this transaction.

        PostgreSQL's `%` operator does not accept a threshold argument directly. It
        reads the value from `pg_trgm.similarity_threshold`, so the matcher sets it
        before running the query. The `true` flag makes the setting local to the
        current transaction.
        """
        await session.exec(
            sa_select(
                func.set_config(
                    "pg_trgm.similarity_threshold",
                    str(self.candidate_score_threshold),
                    True,
                ),
            ),
        )

    def _build_product_match_statement(self):
        """Build the complete product matching query.

        The query is expressed with SQLAlchemy instead of raw SQL, but it still maps to
        PostgreSQL-specific SQL. The important pieces are CTEs for alias candidates and
        top candidates, plus a lateral subquery for the latest price observation.
        """
        stored_receipt_name = func.lower(bindparam("stored_receipt_name"))
        expanded_receipt_name = func.lower(bindparam("expanded_receipt_name"))
        unit_price = bindparam("unit_price")
        line_total = bindparam("line_total")
        retailer_id = bindparam("retailer_id")

        alias_name = func.lower(ProductAlias.alias_name)
        normalized_alias_name = func.lower(ProductAlias.normalized_alias_name)
        product_name = func.lower(Product.name)

        text_score = self._build_text_score(
            alias_name=alias_name,
            normalized_alias_name=normalized_alias_name,
            product_name=product_name,
            stored_receipt_name=stored_receipt_name,
            expanded_receipt_name=expanded_receipt_name,
        )
        rank_score = self._build_rank_score(
            normalized_alias_name=normalized_alias_name,
            product_name=product_name,
            stored_receipt_name=stored_receipt_name,
            expanded_receipt_name=expanded_receipt_name,
        )
        exact_score = self._build_exact_score(
            normalized_alias_name,
            stored_receipt_name,
            expanded_receipt_name,
        )
        retailer_score = self._build_retailer_score(retailer_id)
        source_score = self._build_source_score()
        product_rank = func.row_number().over(
            partition_by=Product.id,
            order_by=(
                rank_score.desc(),
                ProductAlias.confidence.desc(),
                ProductAlias.last_seen_at.desc(),
            ),
        )

        # First stage: find plausible alias matches for this retailer. The `%`
        # operator is pg_trgm's index-backed similarity operator. This is much cheaper
        # than calculating `similarity()` and `word_similarity()` for every alias row.
        # A product can have many aliases, so this CTE may still contain multiple rows
        # for the same product.
        alias_candidates = (
            sa_select(
                Product.id.label("product_id"),
                ProductAlias.confidence.label("confidence"),
                text_score.label("text_score"),
                exact_score.label("exact_score"),
                retailer_score.label("retailer_score"),
                source_score.label("source_score"),
                product_rank.label("product_rank"),
            )
            .join(ProductAlias, ProductAlias.product_id == Product.id)
            .where(
                or_(
                    ProductAlias.retailer_id == retailer_id,
                    ProductAlias.retailer_id.is_(None),
                ),
                or_(
                    ProductAlias.normalized_alias_name.op("%")(stored_receipt_name),
                    ProductAlias.normalized_alias_name.op("%")(expanded_receipt_name),
                ),
            )
            .cte("alias_candidates")
        )
        # Second stage: keep the strongest alias row for each product, then keep only
        # the best products before doing price scoring.
        top_candidates = self._build_top_candidates(alias_candidates)

        # Third stage: compare the receipt price with the latest known retailer price.
        # This helps when receipt abbreviations are weak but the price is distinctive.
        latest_price = self._build_latest_price_lateral(top_candidates, retailer_id)
        price_score = self._build_price_score(latest_price, unit_price, line_total)
        score = self._build_final_score(top_candidates, price_score)

        return (
            sa_select(
                top_candidates.c.product_id,
                top_candidates.c.text_score,
                top_candidates.c.exact_score,
                price_score,
                score,
            )
            .select_from(top_candidates.outerjoin(latest_price, true()))
            .order_by(score.desc(), top_candidates.c.confidence.desc())
            .limit(1)
        )

    def _build_text_score(
        self,
        alias_name,
        normalized_alias_name,
        product_name,
        stored_receipt_name,
        expanded_receipt_name,
    ):
        """Score broad text similarity using stored and expanded receipt names."""
        return func.greatest(
            func.similarity(normalized_alias_name, stored_receipt_name),
            func.word_similarity(stored_receipt_name, normalized_alias_name),
            func.similarity(normalized_alias_name, expanded_receipt_name),
            func.word_similarity(expanded_receipt_name, normalized_alias_name),
            func.similarity(alias_name, stored_receipt_name),
            func.word_similarity(stored_receipt_name, alias_name),
            func.similarity(alias_name, expanded_receipt_name),
            func.word_similarity(expanded_receipt_name, alias_name),
            func.similarity(product_name, stored_receipt_name),
            func.word_similarity(stored_receipt_name, product_name),
            func.similarity(product_name, expanded_receipt_name),
            func.word_similarity(expanded_receipt_name, product_name),
        )

    def _build_rank_score(
        self,
        normalized_alias_name,
        product_name,
        stored_receipt_name,
        expanded_receipt_name,
    ):
        """Score alias rows for per-product ranking.

        This intentionally excludes `alias_name` and uses normalized alias/product
        name fields. We want stable fields to choose the best alias row per product.
        """
        return func.greatest(
            func.similarity(normalized_alias_name, stored_receipt_name),
            func.word_similarity(stored_receipt_name, normalized_alias_name),
            func.similarity(normalized_alias_name, expanded_receipt_name),
            func.word_similarity(expanded_receipt_name, normalized_alias_name),
            func.similarity(product_name, stored_receipt_name),
            func.word_similarity(stored_receipt_name, product_name),
            func.similarity(product_name, expanded_receipt_name),
            func.word_similarity(expanded_receipt_name, product_name),
        )

    def _build_exact_score(
        self,
        normalized_alias_name,
        stored_receipt_name,
        expanded_receipt_name,
    ):
        """Boost aliases that exactly match the stored or expanded receipt name."""
        return case(
            (
                normalized_alias_name.in_([stored_receipt_name, expanded_receipt_name]),
                literal(Decimal("0.25")),
            ),
            else_=literal(Decimal("0")),
        )

    def _build_retailer_score(self, retailer_id):
        """Prefer aliases from the same retailer, but allow global aliases."""
        return case(
            (ProductAlias.retailer_id == retailer_id, literal(Decimal("0.08"))),
            (ProductAlias.retailer_id.is_(None), literal(Decimal("0.03"))),
            else_=literal(Decimal("0")),
        )

    def _build_source_score(self):
        """Prefer aliases from sources that are useful for receipts."""
        return case(
            (ProductAlias.source == ProductAliasSource.RECEIPT, literal(Decimal("0.06"))),
            (ProductAlias.source == ProductAliasSource.PRICE_CSV, literal(Decimal("0.04"))),
            (ProductAlias.source == ProductAliasSource.MANUAL, literal(Decimal("0.03"))),
            else_=literal(Decimal("0")),
        )

    def _build_top_candidates(self, alias_candidates):
        """Deduplicate aliases down to one row per product and keep top products."""
        return (
            sa_select(alias_candidates)
            .where(alias_candidates.c.product_rank == 1)
            .order_by(
                alias_candidates.c.exact_score.desc(),
                alias_candidates.c.text_score.desc(),
                alias_candidates.c.confidence.desc(),
            )
            .limit(self.candidate_limit)
            .cte("top_candidates")
        )

    def _build_latest_price_lateral(self, top_candidates, retailer_id):
        """Return the latest retailer price for each candidate product.

        LATERAL lets the latest-price lookup depend on the current candidate product.
        """
        return (
            sa_select(PriceObservation.price_eur, PriceObservation.unit_price_eur)
            .where(
                PriceObservation.product_id == top_candidates.c.product_id,
                PriceObservation.retailer_id == retailer_id,
            )
            .order_by(
                PriceObservation.observed_date.desc(),
                PriceObservation.price_eur.nulls_last(),
            )
            .limit(1)
            .lateral("latest_price")
        )

    def _build_price_score(self, latest_price, unit_price, line_total):
        """Boost candidates when known prices match the receipt line.

        For normal receipt lines, `unit_price` is usually the product price. For some
        lines, especially multi-quantity rows, `line_total` can also be useful.
        """
        return case(
            (latest_price.c.price_eur == unit_price, literal(Decimal("0.30"))),
            (latest_price.c.price_eur == line_total, literal(Decimal("0.20"))),
            (latest_price.c.unit_price_eur == unit_price, literal(Decimal("0.26"))),
            else_=literal(Decimal("0")),
        ).label("price_score")

    def _build_final_score(self, top_candidates, price_score):
        """Combine all independent signals into the final ranking score."""
        return (
            top_candidates.c.text_score
            + top_candidates.c.exact_score
            + top_candidates.c.retailer_score
            + top_candidates.c.source_score
            + price_score
        ).label("score")


receipt_product_matcher = ReceiptProductMatcher()
