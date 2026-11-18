import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine)


def get_db():
    # Сессия закрывается без commit при ошибке, поэтому недоделанные изменения откатываются.
    with SessionLocal() as db:
        yield db
