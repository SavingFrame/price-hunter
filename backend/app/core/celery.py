import datetime
import uuid

from celery import Celery, chain
from celery.schedules import crontab
from sqlmodel import Session

from app.core.db import engine
from app.services.daily_observation_service import ObservationDailyCalculator
from app.services.openfoodfacts_product_images import OpenFoodFactsProductImageSyncer
from app.services.price_csv_import_job import PriceCsvImportJob, parse_import_date

celery = Celery(
    "worker",
    broker="redis://localhost:6379/12",
    backend="redis://localhost:6379/13",  # result backend
)

celery.conf.beat_schedule = {
    "download-csv-daily-at-7am": {
        "task": "app.core.celery.download_csv",
        "schedule": crontab(hour=7, minute=0),
    },
}


@celery.task
def download_csv(date: datetime.date | str | None = None):
    today = parse_import_date(date)
    job = PriceCsvImportJob()

    retailer_tasks = [
        download_retailer_csv.si(
            retailer_id=str(retailer_id),
            date=today.isoformat(),
        )
        for retailer_id in job.supported_retailer_ids()
    ]
    chain(
        *retailer_tasks,
        reconcile_product_names.si(),
        calculate_observation_daily.si(date_from=today, date_to=today),
    ).apply_async()


@celery.task
def calculate_observation_daily(date_from: datetime.date, date_to: datetime.date):

    with Session(engine) as session:
        calculator = ObservationDailyCalculator(
            date_from=date_from,
            date_to=date_to,
            session=session,
        )
        calculator.calculate()


@celery.task
def download_retailer_csv(retailer_id: str, date: str):
    PriceCsvImportJob().import_retailer(
        retailer_id=uuid.UUID(retailer_id),
        date=parse_import_date(date),
    )


@celery.task
def reconcile_product_names(_results=None):
    return PriceCsvImportJob().reconcile_product_names()


@celery.task
def backfill_csv(days: int = 30):
    today = datetime.date.today()
    for i in range(days):
        date = today - datetime.timedelta(days=i)
        job = PriceCsvImportJob()
        for retailer_id in job.supported_retailer_ids():
            job.import_retailer(retailer_id=retailer_id, date=date)
    PriceCsvImportJob().reconcile_product_names()


@celery.task
def sync_product_images(limit: int | None = None):
    with Session(engine) as session:
        OpenFoodFactsProductImageSyncer().sync_missing_product_images(
            session=session,
            limit=limit,
        )
