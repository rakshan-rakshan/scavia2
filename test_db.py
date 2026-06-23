import asyncio
from sqlalchemy import text
from api.db.database import async_session_factory

async def test():
    async with async_session_factory() as s:
        await s.execute(text('SELECT 1'))
        print('DB connection OK')

asyncio.run(test())
