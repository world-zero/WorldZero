from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models.contact import ContactMessage
from schemas.contact import ContactMessageIn, ContactMessageOut
from services.contact_limit import hit_contact_limit

router = APIRouter()


@router.post("", response_model=ContactMessageOut, status_code=201)
async def submit_contact(
    data: ContactMessageIn,
    request: Request,
    session: AsyncSession = Depends(get_db, scope="function"),
):
    if data.website:
        # Honeypot: same shape as success so a bot learns nothing.
        return ContactMessageOut(id=0, created_at=datetime.now(timezone.utc))
    hit_contact_limit(request)
    msg = ContactMessage(name=data.name, email=data.email, message=data.message)
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return ContactMessageOut.model_validate(msg)
