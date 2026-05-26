"""
Purge service: Scheduled background task to hard-delete soft-deleted users and their data after 30 days.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import AsyncSessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)


class PurgeService:
    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings

    async def run_purge(self) -> int:
        """
        Hard-deletes all users (and cascaded data) whose deleted_at
        timestamp is older than 30 days.
        Returns the number of users purged.
        """
        threshold_date = datetime.now(timezone.utc) - timedelta(days=30)
        
        # Find users to delete
        query = select(User).where(
            User.deleted_at.is_not(None),
            User.deleted_at < threshold_date
        )
        result = await self.db.execute(query)
        users_to_purge = result.scalars().all()
        
        if not users_to_purge:
            return 0
            
        user_ids = [u.id for u in users_to_purge]
        
        # Hard delete
        delete_stmt = delete(User).where(User.id.in_(user_ids))
        await self.db.execute(delete_stmt)
        await self.db.commit()
        
        return len(user_ids)


async def _purge_loop():
    """Infinite loop that triggers the purge every 24 hours."""
    while True:
        try:
            # Sleep first so we don't hit immediately on boot every dev reload
            # Or we can run once then sleep. Let's run once then sleep 24h.
            settings = get_settings()
            async with AsyncSessionLocal() as db:
                service = PurgeService(db, settings)
                purged_count = await service.run_purge()
                if purged_count > 0:
                    logger.info(f"PurgeService: Hard-deleted {purged_count} soft-deleted users.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"PurgeService error: {e}")
        
        # 24 hours
        await asyncio.sleep(86400)


def start_purge_scheduler():
    """Starts the asyncio background task for purging."""
    loop = asyncio.get_running_loop()
    loop.create_task(_purge_loop())
