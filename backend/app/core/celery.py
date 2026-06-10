import datetime
import logging
import uuid

from celery import Celery, chain
from celery.schedules import crontab
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.services.daily_observation_service import ObservationDailyCalculator
from app.services.open_food_facts.s3_image_syncer import S3ImageSyncer
from app.services.price_csv_import_job import PriceCsvImportJob

logger = logging.getLogger(__name__)

celery = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery.conf.beat_schedule = {
    "download-csv-daily-at-7am": {
        "task": "app.core.celery.download_csv",
        "schedule": crontab(hour=7, minute=0),
    },
    "sync-product-images-every-2-week": {
        "task": "app.core.celery.sync_product_images",
        "schedule": crontab(hour=7, minute=0, day_of_month="1,15"),
    },
}


@celery.task
def download_csv(date: datetime.date | None = None):
    if not date:
        date = datetime.date.today()
    job = PriceCsvImportJob()

    retailer_tasks = [
        download_retailer_csv.si(
            retailer_id=str(retailer_id),
            date=date,
        )
        for retailer_id in job.supported_retailer_ids()
    ]
    chain(
        *retailer_tasks,
        reconcile_product_names.si(),
        calculate_observation_daily.si(date_from=date, date_to=date),
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
def download_retailer_csv(retailer_id: str, date: datetime.date):
    logger.info("Importing price CSV for retailer %s on date %s", retailer_id, date)
    PriceCsvImportJob().import_retailer(
        retailer_id=uuid.UUID(retailer_id),
        date=date,
    )


@celery.task
def reconcile_product_names(_results=None):
    return PriceCsvImportJob().reconcile_product_names()


@celery.task
def backfill_csv(days: int = 30):
    today = datetime.date.today()
    date_from = today - datetime.timedelta(days=days)

    retailer_tasks = []

    job = PriceCsvImportJob()

    for i in range(days):
        date = today - datetime.timedelta(days=i)
        for retailer_id in job.supported_retailer_ids():
            retailer_tasks.append(
                download_retailer_csv.si(
                    retailer_id=str(retailer_id),
                    date=date,
                )
            )

    chain(
        *retailer_tasks,
        reconcile_product_names.si(),
        calculate_observation_daily.si(date_from=date_from, date_to=today),
    ).apply_async()


@celery.task
def sync_product_images():
    with Session(engine) as session:
        syncer = S3ImageSyncer()
        syncer.download_keys()
        table = syncer.create_temporary_table(session)
        syncer.copy_pictures_to_temp_table(session, table)
        syncer.update_product_images(session, table)
        session.commit()
