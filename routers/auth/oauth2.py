from fastapi import HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import select
from database.connection import SessionDep
from database.models import TokenData, User, UserRead
from datetime import datetime, timezone, timedelta
from jose import JWTError, jwt
import os
from dotenv import load_dotenv
from pathlib import Path

print("cwd:", Path().resolve())
print("env file exists:", Path(".env").exists())

load_dotenv(override=True)

secret_key = os.getenv("SECRET_KEY")
algorithm = os.getenv("ALGORITHM")
access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=access_token_expire_minutes)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=algorithm)
    return encoded_jwt


def get_current_user(
    request: Request,
    session: SessionDep,
):

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = request.cookies.get("access_token")

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        username = payload.get("username")

        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    statement = select(User).where(User.username == token_data.username)
    user = session.exec(statement).first()

    if user is None:
        raise credentials_exception

    return UserRead(
        id=user.id,
        username=user.username,
        role=user.role,
        created_at=user.created_at,
    )


def verify_token(token: str):
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        username: str = payload.get("username")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
