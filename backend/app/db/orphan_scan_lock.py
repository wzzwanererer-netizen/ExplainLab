"""PostgreSQL's dedicated advisory lock for orphan-scan leadership."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text

ORPHAN_SCAN_LOCK = int.from_bytes(b"EXLABORP", "big")


@contextmanager
def orphan_scan_leadership(engine: Engine) -> Iterator[bool]:
    if engine.dialect.name != "postgresql":
        yield True
        return
    with engine.connect() as connection:
        # Detach ensures connection.close physically releases the session lock.
        connection.detach()
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(CAST(:lock_id AS bigint))"),
            {"lock_id": ORPHAN_SCAN_LOCK},
        ).scalar_one()
        try:
            connection.commit()
            yield acquired
        finally:
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(CAST(:lock_id AS bigint))"),
                    {"lock_id": ORPHAN_SCAN_LOCK},
                )
                connection.commit()
