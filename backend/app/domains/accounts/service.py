from typing import Any

from sqlmodel import Session, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.domains.accounts.models import User, UserCreate, UserUpdate


def _build_user(user_create: UserCreate) -> User:
    return User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )


def _apply_user_update(db_user: User, user_in: UserUpdate) -> None:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)


def create_user_sync(*, session: Session, user_create: UserCreate) -> User:
    db_obj = _build_user(user_create)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


async def create_user(*, session: AsyncSession, user_create: UserCreate) -> User:
    db_obj = _build_user(user_create)
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    return db_obj


def update_user_sync(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    _apply_user_update(db_user, user_in)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


async def update_user(
    *, session: AsyncSession, db_user: User, user_in: UserUpdate
) -> Any:
    _apply_user_update(db_user, user_in)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


def get_user_by_email_sync(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


async def get_user_by_email(*, session: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = (await session.exec(statement)).first()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate_sync(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email_sync(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user


async def authenticate(
    *, session: AsyncSession, email: str, password: str
) -> User | None:
    db_user = await get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
    return db_user
