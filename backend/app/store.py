import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, JSON, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

engine = create_engine(
    os.getenv("DATABASE_URL", "sqlite:///./thermotwin.db"),
    **(
        {"connect_args": {"check_same_thread": False}}
        if not os.getenv("DATABASE_URL")
        else {}
    ),
)
Session = sessionmaker(bind=engine)
Base = declarative_base()


class Record(Base):
    __tablename__ = "records"
    id = Column(String, primary_key=True)
    kind = Column(String, index=True, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def init():
    Base.metadata.create_all(engine)


def put(key, kind, payload):
    with Session.begin() as s:
        s.add(Record(id=key, kind=kind, payload=payload))


def get(key):
    with Session() as s:
        record = s.get(Record, key)
        return record.payload if record else None


def update(key, payload):
    with Session.begin() as s:
        record = s.get(Record, key)
        if not record:
            raise KeyError(key)
        record.payload = payload


def listing(kind, limit=None):
    with Session() as s:
        query = s.query(Record).filter_by(kind=kind).order_by(Record.created_at.desc())
        if limit:
            query = query.limit(limit)
        return [r.payload for r in query.all()]
