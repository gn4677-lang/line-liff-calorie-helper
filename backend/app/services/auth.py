from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Preference, ReportingBias, User


def get_or_create_user(db: Session, line_user_id: str, display_name: str = "Demo User") -> User:
    user = db.scalar(select(User).where(User.line_user_id == line_user_id))
    if user:
        return user

    user = User(line_user_id=line_user_id, display_name=display_name, daily_calorie_target=settings.default_daily_calorie_target)
    db.add(user)
    db.flush()
    db.add(Preference(user_id=user.id))
    db.add(ReportingBias(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user
