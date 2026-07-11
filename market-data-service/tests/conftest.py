"""Shared fixtures: in-memory SQLite session with the mirrored schema.

Production DDL is owned by Flyway; create_all here is test-only.
"""
import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Symbol


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_for_sqlite(element, compiler, **kw):
    # SQLite only auto-increments INTEGER PRIMARY KEY (not BIGINT).
    return "INTEGER"


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    s = factory()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture()
def reliance(session: Session) -> Symbol:
    sym = Symbol(ticker="RELIANCE", yahoo_symbol="RELIANCE.NS",
                 name="Reliance Industries Ltd", sector="Oil & Gas")
    session.add(sym)
    session.commit()
    return sym
