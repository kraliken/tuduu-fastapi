from typing import Annotated
from sqlmodel import Session, SQLModel, create_engine, text
from fastapi import Depends
from urllib.parse import quote_plus

import os

username = os.getenv("DB_USERNAME")
password = quote_plus(os.getenv("DB_PASSWORD"))
server = os.getenv("DB_SERVER")
database = os.getenv("DB_DATABASE")

connection_string = (
    f"mssql+pyodbc://{username}:{password}@{server}:1433/{database}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
    "&encrypt=yes"
    "&trustservercertificate=no"
    "&connection+timeout=30"
)

engine = create_engine(connection_string, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
