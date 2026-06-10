from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, func, select

from app.models import PriceObservationDaily
from app.models.price_observation import PriceObservation


class ObservationDailyCalculator:
    def __init__(self, date_from: date, date_to: date, session: Session):
        self.date_from = date_from
        self.date_to = date_to
        self.session = session

    def _build_select_query(self):

        return (
            select(
                PriceObservation.product_id,
                PriceObservation.retailer_id,
                PriceObservation.observed_date,
                func.min(PriceObservation.price_eur).label("price_eur_min"),
                func.max(PriceObservation.price_eur).label("price_eur_max"),
                func.avg(PriceObservation.price_eur).label("price_eur_avg"),
                func.min(PriceObservation.unit_price_eur).label("unit_price_eur_min"),
                func.max(PriceObservation.unit_price_eur).label("unit_price_eur_max"),
                func.avg(PriceObservation.unit_price_eur).label("unit_price_eur_avg"),
                func.bool_or(PriceObservation.is_special_sale).label("is_special_sale"),
                func.count(PriceObservation.id).label("observation_count"),
            )
            .where(
                PriceObservation.observed_date >= self.date_from,
                PriceObservation.observed_date <= self.date_to,
            )
            .group_by(
                PriceObservation.product_id,
                PriceObservation.observed_date,
                PriceObservation.retailer_id,
            )
        )

    def calculate(self):
        select_stmt = self._build_select_query()
        insert_stmt = insert(PriceObservationDaily).from_select(
            [
                "product_id",
                "retailer_id",
                "observed_date",
                "price_eur_min",
                "price_eur_max",
                "price_eur_avg",
                "unit_price_eur_min",
                "unit_price_eur_max",
                "unit_price_eur_avg",
                "is_special_sale",
                "observation_count",
            ],
            select_stmt,
        )
        insert_stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_price_observation_daily",
            set_={
                "price_eur_min": insert_stmt.excluded.price_eur_min,
                "price_eur_max": insert_stmt.excluded.price_eur_max,
                "price_eur_avg": insert_stmt.excluded.price_eur_avg,
                "unit_price_eur_min": insert_stmt.excluded.unit_price_eur_min,
                "unit_price_eur_max": insert_stmt.excluded.unit_price_eur_max,
                "unit_price_eur_avg": insert_stmt.excluded.unit_price_eur_avg,
                "is_special_sale": insert_stmt.excluded.is_special_sale,
                "observation_count": insert_stmt.excluded.observation_count,
            },
        )
        self.session.exec(insert_stmt)
        self.session.commit()
