from fastapi import APIRouter, Depends
from database.connection import SessionDep
from database.models import User, UserRead
from sqlmodel import select
from typing import List
from utils.dependencies import get_current_admin_user

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("/", response_model=List[UserRead])
def get_all_users(
    session: SessionDep, current_user: User = Depends(get_current_admin_user)
):
    statement = select(User).where(User.id != current_user.id)
    users = session.exec(statement).all()

    return [
        UserRead(
            id=user.id,
            username=user.username,
            role=user.role,
            created_at=user.created_at,
        )
        for user in users
    ]
