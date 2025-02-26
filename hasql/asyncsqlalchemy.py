import asyncio
from typing import Sequence

import sqlalchemy as sa  # type: ignore
from sqlalchemy.ext.asyncio import AsyncConnection  # type: ignore
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import QueuePool  # type: ignore

from hasql.base import BasePoolManager
from hasql.metrics import DriverMetrics
from hasql.utils import Dsn


class PoolManager(BasePoolManager):
    def get_pool_freesize(self, pool: AsyncEngine):
        queue_pool: QueuePool = pool.sync_engine.pool
        return queue_pool.size() - queue_pool.checkedout()

    def acquire_from_pool(self, pool: AsyncEngine, **kwargs):
        return pool.connect()

    async def release_to_pool(      # type: ignore
        self,
        connection: AsyncConnection,
        _: AsyncEngine,
        **kwargs
    ):
        await connection.close()

    async def _is_master(self, connection: AsyncConnection):
        return await connection.scalar(
            sa.text("SHOW transaction_read_only"),
        ) == "off"

    async def _pool_factory(self, dsn: Dsn):
        # TODO: Add support of psycopg3 after release of sqlalchemy 2.0
        d = str(dsn).replace("postgresql", "postgresql+asyncpg")
        return create_async_engine(d, **self.pool_factory_kwargs)

    def _prepare_pool_factory_kwargs(self, kwargs: dict) -> dict:
        kwargs["pool_size"] = kwargs.get("pool_size", 1) + 1
        return kwargs

    async def _close(self, pool: AsyncEngine):
        await pool.dispose()

    async def _terminate(self, pool: AsyncEngine):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, pool.sync_engine.dispose)

    def is_connection_closed(self, connection: AsyncConnection):
        return connection.closed

    def host(self, pool: AsyncEngine):
        return pool.sync_engine.url.host

    def _driver_metrics(self) -> Sequence[DriverMetrics]:
        return [
            DriverMetrics(
                max=p.sync_engine.pool.size(),
                min=0,
                idle=p.sync_engine.pool.checkedin(),
                used=p.sync_engine.pool.checkedout(),
                host=p.sync_engine.url.host,
            ) for p in self.pools
        ]


__all__ = ("PoolManager",)
