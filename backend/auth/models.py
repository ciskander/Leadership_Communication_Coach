"""
auth/models.py — Pure-Python dataclass models for auth entities.
No ORM dependency; raw sqlite3 rows are mapped here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class UserAuth:
    id: str
    email: str
    role: str                           # admin | coach | coachee
    oauth_provider: str
    oauth_sub: str
    display_name: Optional[str] = None
    coach_id: Optional[str] = None
    airtable_user_record_id: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "UserAuth":
        return cls(
            id=row["id"],
            email=row["email"],
            role=row["role"],
            oauth_provider=row["oauth_provider"],
            oauth_sub=row["oauth_sub"],
            display_name=row["display_name"],
            coach_id=row["coach_id"],
            airtable_user_record_id=row["airtable_user_record_id"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )


@dataclass
class Session:
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime

    @classmethod
    def from_row(cls, row) -> "Session":
        return cls(
            session_id=row["session_id"],
            user_id=row["user_id"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )


@dataclass
class InviteToken:
    token: str
    coach_id: str
    role: str
    expires_at: datetime
    used_by: Optional[str] = None
    created_at: Optional[datetime] = None
    used_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "InviteToken":
        return cls(
            token=row["token"],
            coach_id=row["coach_id"],
            role=row["role"],
            expires_at=row["expires_at"],
            used_by=row["used_by"],
            created_at=row["created_at"],
            used_at=row["used_at"],
        )
