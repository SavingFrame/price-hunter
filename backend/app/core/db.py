# ruff: noqa: F403, F405

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.domains.accounts import service as accounts_service
from app.domains.accounts.models import UserCreate
from app.domains.models import *  # noqa: F403
from app.domains.products.retailers import RetailerEnum

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
async_engine = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI))


# make sure all SQLModel models are imported before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def get_or_create(session: Session, model: type[SQLModel], defaults=None, **params):
    instance = session.exec(select(model).filter_by(**params)).first()
    if instance:
        return instance, False
    else:
        params |= defaults or {}
        instance = model(**params)
        try:
            session.add(instance)
            session.commit()
        except Exception:  # The actual exception depends on the specific database so we catch all exceptions. This is similar to the official documentation: https://docs.sqlalchemy.org/en/latest/orm/session_transaction.html
            session.rollback()
            instance = session.query(model).filter_by(**params).one()
            return instance, False
        else:
            return instance, True


def init_db(session: Session) -> None:
    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        accounts_service.create_user_sync(session=session, user_create=user_in)
    for retailer in RetailerEnum:
        get_or_create(
            session,
            Retailer,
            name=retailer.value.name,
            id=retailer.value.id,
        )
