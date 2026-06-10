import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import bindparam, case, desc, func, or_, union_all
from sqlalchemy import select as sa_select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.domains.products.aliases import ProductAlias
from app.domains.products.models import Product
from app.domains.products.price_observation_daily import PriceObservationDaily
from app.domains.products.retailers import Retailer


@dataclass(frozen=True)
class SimilarProductCandidate:
    product: Product
    retailers: list[Retailer]
    latest_price_eur: Decimal | None
    average_price_eur: Decimal | None
    latest_observed_date: date | None
    score: Decimal


class ProductSimilarityService:
    """Find user-facing similar product suggestions.

    This service is intentionally lightweight. It does not try to build global
    product equivalence groups. It only returns plausible alternatives that a user
    can select for a product list item.
    """

    candidate_score_threshold = Decimal("0.18")
    candidate_query_limit = 120
    max_query_texts = 6

    async def find_similar_products(
        self,
        session: AsyncSession,
        product_id: uuid.UUID,
        limit: int = 20,
    ) -> list[SimilarProductCandidate]:
        target_product = await session.get(Product, product_id)
        if target_product is None:
            return []

        query_texts = await self._get_query_texts(session, target_product)
        if not query_texts:
            return []

        target_retailer_ids = await self._get_product_retailer_ids(
            session, target_product.id
        )

        await self._set_similarity_threshold(session)
        scored_product_ids: dict[uuid.UUID, Decimal] = {}
        for query_text in query_texts:
            rows = (await session.exec(
                self._build_candidate_statement(query_text, target_product),
            )).all()
            for candidate_product_id, score in rows:
                previous_score = scored_product_ids.get(candidate_product_id)
                if previous_score is None or score > previous_score:
                    scored_product_ids[candidate_product_id] = score

        if not scored_product_ids:
            return []

        candidates = await self._load_candidates(
            session=session,
            scored_product_ids=scored_product_ids,
            target_retailer_ids=target_retailer_ids,
        )
        candidates.sort(
            key=lambda candidate: (
                candidate.score,
                candidate.latest_observed_date or date.min,
                candidate.average_price_eur or Decimal("0"),
            ),
            reverse=True,
        )
        return candidates[:limit]

    async def _get_query_texts(
        self, session: AsyncSession, target_product: Product
    ) -> list[str]:
        rows = (await session.exec(
            select(ProductAlias.normalized_alias_name)
            .where(ProductAlias.product_id == target_product.id)
            .order_by(ProductAlias.confidence.desc(), ProductAlias.last_seen_at.desc())
            .limit(self.max_query_texts - 1),
        )).all()

        query_texts = [self._normalize_query_text(target_product.name)]
        query_texts.extend(self._normalize_query_text(row) for row in rows)

        unique_query_texts: list[str] = []
        seen_query_texts: set[str] = set()
        for query_text in query_texts:
            if len(query_text) < 3 or query_text in seen_query_texts:
                continue
            unique_query_texts.append(query_text)
            seen_query_texts.add(query_text)

        return unique_query_texts[: self.max_query_texts]

    @staticmethod
    def _normalize_query_text(value: str | None) -> str:
        return " ".join((value or "").strip().lower().split())

    async def _set_similarity_threshold(self, session: AsyncSession) -> None:
        await session.exec(
            sa_select(
                func.set_config(
                    "pg_trgm.similarity_threshold",
                    str(self.candidate_score_threshold),
                    True,
                ),
            ),
        )

    def _build_candidate_statement(self, query_text: str, target_product: Product):
        query_param = bindparam("query_text", query_text)
        product_name = func.lower(Product.name)
        alias_name = func.lower(ProductAlias.alias_name)
        normalized_alias_name = func.lower(ProductAlias.normalized_alias_name)

        product_matches = select(
            Product.id.label("product_id"),
            func.similarity(product_name, query_param).label("text_score"),
        ).where(
            Product.id != target_product.id,
            product_name.op("%")(query_param),
        )
        alias_matches = select(
            ProductAlias.product_id.label("product_id"),
            func.greatest(
                func.similarity(alias_name, query_param),
                func.similarity(normalized_alias_name, query_param),
            ).label("text_score"),
        ).where(
            ProductAlias.product_id != target_product.id,
            or_(
                alias_name.op("%")(query_param),
                normalized_alias_name.op("%")(query_param),
            ),
        )
        matched_products = union_all(product_matches, alias_matches).subquery(
            "matched_products",
        )

        same_barcode_score = self._build_same_barcode_score(target_product)
        same_category_score = self._build_same_category_score(target_product)
        score = (
            matched_products.c.text_score + same_barcode_score + same_category_score
        ).label("score")

        return (
            select(Product.id, func.max(score).label("score"))
            .join(matched_products, matched_products.c.product_id == Product.id)
            .group_by(Product.id)
            .order_by(desc("score"))
            .limit(self.candidate_query_limit)
        )

    @staticmethod
    def _build_same_barcode_score(target_product: Product):
        if not target_product.barcode:
            return Decimal("0")
        return case(
            (Product.barcode == target_product.barcode, Decimal("0.20")),
            else_=Decimal("0"),
        )

    @staticmethod
    def _build_same_category_score(target_product: Product):
        if not target_product.category:
            return Decimal("0")
        return case(
            (
                func.lower(Product.category) == target_product.category.lower(),
                Decimal("0.04"),
            ),
            else_=Decimal("0"),
        )

    async def _load_candidates(
        self,
        session: AsyncSession,
        scored_product_ids: dict[uuid.UUID, Decimal],
        target_retailer_ids: set[uuid.UUID],
    ) -> list[SimilarProductCandidate]:
        products = (await session.exec(
            select(Product).where(Product.id.in_(scored_product_ids.keys())),
        )).all()
        retailers_by_product_id = await self._load_retailers_by_product_id(
            session=session,
            product_ids=[product.id for product in products],
        )
        price_stats_by_product_id = await self._load_price_stats_by_product_id(
            session=session,
            product_ids=[product.id for product in products],
        )

        candidates: list[SimilarProductCandidate] = []
        for product in products:
            stats = price_stats_by_product_id.get(product.id)
            if stats is None:
                continue

            retailers = retailers_by_product_id.get(product.id, [])
            candidate_retailer_ids = {retailer.id for retailer in retailers}
            other_retailer_score = (
                Decimal("0.40")
                if candidate_retailer_ids - target_retailer_ids
                else Decimal("0")
            )
            candidates.append(
                SimilarProductCandidate(
                    product=product,
                    retailers=retailers,
                    latest_price_eur=stats[0],
                    average_price_eur=stats[1],
                    latest_observed_date=stats[2],
                    score=scored_product_ids[product.id] + other_retailer_score,
                ),
            )

        return candidates

    @staticmethod
    async def _get_product_retailer_ids(
        session: AsyncSession,
        product_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        rows = (await session.exec(
            select(PriceObservationDaily.retailer_id)
            .where(PriceObservationDaily.product_id == product_id)
            .distinct(),
        )).all()
        return set(rows)

    @staticmethod
    async def _load_retailers_by_product_id(
        session: AsyncSession,
        product_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[Retailer]]:
        rows = (await session.exec(
            select(PriceObservationDaily.product_id, Retailer)
            .join(Retailer, Retailer.id == PriceObservationDaily.retailer_id)
            .where(PriceObservationDaily.product_id.in_(product_ids))
            .group_by(PriceObservationDaily.product_id, Retailer.id)
            .order_by(PriceObservationDaily.product_id, Retailer.name),
        )).all()

        retailers_by_product_id: dict[uuid.UUID, list[Retailer]] = {}
        for product_id, retailer in rows:
            retailers_by_product_id.setdefault(product_id, []).append(retailer)

        return retailers_by_product_id

    @staticmethod
    async def _load_price_stats_by_product_id(
        session: AsyncSession,
        product_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, tuple[Decimal | None, Decimal | None, date | None]]:
        latest_dates = (
            select(
                PriceObservationDaily.product_id.label("product_id"),
                func.max(PriceObservationDaily.observed_date).label(
                    "latest_observed_date"
                ),
            )
            .where(PriceObservationDaily.product_id.in_(product_ids))
            .group_by(PriceObservationDaily.product_id)
            .subquery("latest_dates")
        )
        rows = (await session.exec(
            select(
                PriceObservationDaily.product_id,
                PriceObservationDaily.price_eur_avg.label("latest_price_eur"),
                PriceObservationDaily.price_eur_avg.label("average_price_eur"),
                latest_dates.c.latest_observed_date,
            )
            .join(
                latest_dates,
                (latest_dates.c.product_id == PriceObservationDaily.product_id)
                & (
                    latest_dates.c.latest_observed_date
                    == PriceObservationDaily.observed_date
                ),
            )
            .where(
                PriceObservationDaily.product_id.in_(product_ids),
            )
        )).all()

        return {
            product_id: (latest_price_eur, average_price_eur, latest_observed_date)
            for product_id, latest_price_eur, average_price_eur, latest_observed_date in rows
        }


product_similarity_service = ProductSimilarityService()
