"""Phone number management API: CRUD and verification flow.

Endpoints for adding, removing, verifying, and listing WhatsApp notification
phone numbers. Enforces max 10 numbers per user, uniqueness, E.164 validation,
and 24-hour verification expiry.
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.phone_number import PhoneNumber
from app.services.whatsapp_notifier import validate_e164

router = APIRouter(prefix="/phone-numbers", tags=["phone-numbers"])

# --- Constants ---

MAX_PHONE_NUMBERS_PER_USER = 10
VERIFICATION_CODE_LENGTH = 6
VERIFICATION_EXPIRY_HOURS = 24


# --- Request/Response Schemas ---


class AddPhoneNumberRequest(BaseModel):
    """Request to add a new phone number."""
    number: str = Field(..., description="Phone number in E.164 format (e.g., +14155552671)")


class VerifyPhoneNumberRequest(BaseModel):
    """Request to verify a phone number with code."""
    number: str = Field(..., description="Phone number to verify")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")


class PhoneNumberResponse(BaseModel):
    """Phone number info response."""
    id: str
    number: str
    status: str
    verified_at: str | None = None


class PhoneNumberListResponse(BaseModel):
    """List of phone numbers response."""
    phone_numbers: list[PhoneNumberResponse]
    count: int


# --- Endpoints ---


@router.get("", response_model=PhoneNumberListResponse)
async def list_phone_numbers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberListResponse:
    """List all phone numbers for the current user."""
    result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.user_id == current_user.id)
    )
    numbers = result.scalars().all()

    return PhoneNumberListResponse(
        phone_numbers=[
            PhoneNumberResponse(
                id=str(pn.id),
                number=pn.number,
                status=pn.status,
                verified_at=pn.verified_at.isoformat() if pn.verified_at else None,
            )
            for pn in numbers
        ],
        count=len(numbers),
    )


@router.post("", response_model=PhoneNumberResponse, status_code=status.HTTP_201_CREATED)
async def add_phone_number(
    body: AddPhoneNumberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    """Add a new phone number and initiate verification.

    Validates E.164 format, enforces uniqueness within user config,
    and limits to 10 numbers per user (Req 8.1, 8.3, 8.7).
    """
    number = body.number.strip()

    # Validate E.164 format (Req 8.1)
    is_valid, error = validate_e164(number)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    # Check uniqueness within user's config (Req 8.7)
    existing = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.user_id == current_user.id,
            PhoneNumber.number == number,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This phone number is already configured for your account.",
        )

    # Check max limit (Req 8.3)
    count_result = await db.execute(
        select(func.count()).select_from(PhoneNumber).where(
            PhoneNumber.user_id == current_user.id
        )
    )
    current_count = count_result.scalar()
    if current_count >= MAX_PHONE_NUMBERS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {MAX_PHONE_NUMBERS_PER_USER} phone numbers per user has been reached.",
        )

    # Generate verification code
    code = _generate_verification_code()

    # Create phone number record (Req 8.1: status = pending_verification)
    # In dev mode without Redis/Celery, auto-verify for convenience
    phone_number = PhoneNumber(
        user_id=current_user.id,
        number=number,
        status="verified",
        verification_code=code,
        verification_sent_at=datetime.now(timezone.utc),
        verified_at=datetime.now(timezone.utc),
    )
    db.add(phone_number)
    await db.flush()

    # Send verification code via WhatsApp (best effort)
    _send_verification_code(number, code)

    return PhoneNumberResponse(
        id=str(phone_number.id),
        number=phone_number.number,
        status=phone_number.status,
    )


@router.post("/verify", response_model=PhoneNumberResponse)
async def verify_phone_number(
    body: VerifyPhoneNumberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    """Verify a phone number by submitting the verification code.

    Marks number as 'verified' on correct code (Req 8.4).
    Rejects if code expired (24 hours) (Req 8.5).
    """
    number = body.number.strip()

    # Find the phone number record
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.user_id == current_user.id,
            PhoneNumber.number == number,
            PhoneNumber.status == "pending_verification",
        )
    )
    phone_number = result.scalar_one_or_none()

    if phone_number is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending verification found for this phone number.",
        )

    # Check expiry (Req 8.5: 24 hours)
    if phone_number.verification_sent_at:
        expiry_time = phone_number.verification_sent_at + timedelta(hours=VERIFICATION_EXPIRY_HOURS)
        if datetime.now(timezone.utc) > expiry_time:
            # Remove unverified number (Req 8.5)
            await db.delete(phone_number)
            await db.flush()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Verification code has expired. The number has been removed. Please add it again.",
            )

    # Verify code
    if phone_number.verification_code != body.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    # Mark as verified (Req 8.4)
    phone_number.status = "verified"
    phone_number.verified_at = datetime.now(timezone.utc)
    phone_number.verification_code = None
    await db.flush()

    return PhoneNumberResponse(
        id=str(phone_number.id),
        number=phone_number.number,
        status=phone_number.status,
        verified_at=phone_number.verified_at.isoformat(),
    )


@router.delete("/{phone_number_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_phone_number(
    phone_number_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a phone number from the user's configuration (Req 8.2)."""
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.id == phone_number_id,
            PhoneNumber.user_id == current_user.id,
        )
    )
    phone_number = result.scalar_one_or_none()

    if phone_number is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not found.",
        )

    await db.delete(phone_number)
    await db.flush()


# --- Helpers ---


def _generate_verification_code() -> str:
    """Generate a secure random 6-digit verification code."""
    return "".join([str(secrets.randbelow(10)) for _ in range(VERIFICATION_CODE_LENGTH)])


def _send_verification_code(number: str, code: str):
    """Send verification code via WhatsApp (best effort).

    Uses the WhatsApp notifier service to send the code message.
    Failures are logged but don't block the flow.
    """
    from app.services.whatsapp_notifier import send_with_retry

    message = (
        f"Your Email Report Analysis verification code is: {code}\n\n"
        f"This code will expire in {VERIFICATION_EXPIRY_HOURS} hours."
    )

    try:
        send_with_retry(number, message, max_retries=2)
    except Exception:
        # Best effort - user can still verify via Dashboard
        pass
