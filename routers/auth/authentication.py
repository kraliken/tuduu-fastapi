from fastapi import APIRouter, status, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import OperationalError
from database.models import User, UserCreate, UserRead, Token, TokenWithUser
from database.connection import SessionDep
from sqlmodel import select
from utils.hashing import Hash
from datetime import datetime, timezone
from typing import Annotated
from .oauth2 import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserRead)
def create_user(user: UserCreate, session: SessionDep):
    statement = select(User).where(User.username == user.username)
    existing_user = session.exec(statement).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed_password = Hash.bcrypt(user.password)

    db_user = User(
        username=user.username,
        hashed_password=hashed_password,
        created_at=datetime.now(timezone.utc),
    )

    session.add(db_user)
    session.commit()
    session.refresh(db_user)

    return UserRead(
        id=db_user.id, username=db_user.username, created_at=db_user.created_at
    )


@router.post("/login", response_model=TokenWithUser)
def login(
    request: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    try:
        statement = select(User).where(User.username == request.username)
        user = session.exec(statement).first()
    except OperationalError:
        # Adatbázis hiba (pl. Azure DB alszik vagy hálózati gond)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server waking up, please try again soon.",
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not Hash.verify(user.hashed_password, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"username": user.username})

    return TokenWithUser(
        access_token=access_token,
        token_type="bearer",
        user=UserRead(
            id=user.id,
            username=user.username,
            role=user.role,
            created_at=user.created_at,
        ),
    )


@router.get("/me")
def read_users_me(current_user: Annotated[UserRead, Depends(get_current_user)]):
    return current_user
