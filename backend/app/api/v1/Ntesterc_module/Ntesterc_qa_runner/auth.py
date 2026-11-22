from fastapi import Header, HTTPException
from app.core.dependencies import get_current_user_id


async def actor(authorization: str | None = Header(default=None)):
    if not authorization:
        raise HTTPException(401, '请先登录')
    return await get_current_user_id(authorization)
