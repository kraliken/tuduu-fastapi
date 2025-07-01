from fastapi import Depends, HTTPException
from database.models import User, Role
from database.connection import SessionDep
from sqlmodel import select
from routers.auth.oauth2 import oauth2_scheme, verify_token


def get_current_user(session: SessionDep, token: str = Depends(oauth2_scheme)):
    username = verify_token(token)

    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()

    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
