from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.connection import create_db_and_tables
from contextlib import asynccontextmanager
from routers.auth import authentication
from routers.admin import users
from routers.todo import todos
from routers.vodafone import vodafone
from dotenv import load_dotenv

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("📋 Táblák létrehozása...")
    create_db_and_tables()
    print("✅ Táblák létrehozva!")
    yield


app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8080",
    "https://kraliken-fastapi.azurewebsites.net",
    "https://kraliken-nextjs.azurewebsites.net",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(authentication.router)
app.include_router(users.router, prefix="/api/v1")
app.include_router(todos.router, prefix="/api/v1")
app.include_router(vodafone.router, prefix="/api/v1")
