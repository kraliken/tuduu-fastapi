from typing import Annotated
from fastapi import APIRouter, Depends, status, HTTPException
from routers.auth.oauth2 import get_current_user
from database.models import Todo, TodoCreate, TodoUpdate, User
from database.connection import SessionDep
from sqlmodel import select, func, case
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict

router = APIRouter(prefix="/todo", tags=["todo"])


@router.get("/all")
def get_todos(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    category: str | None = None,
    status: str | None = None,
):

    base_query = select(Todo).where(
        Todo.user_id == current_user.id, Todo.category == category
    )

    count_query = select(func.count()).where(
        Todo.user_id == current_user.id, Todo.category == category
    )

    all_todos_count = session.exec(count_query).one()

    # Kategória szűrés (opcionális)
    if category:
        base_query = base_query.where(Todo.category == category)
        count_query = count_query.where(Todo.category == category)

    # Státusz szűrés (opcionális)
    if status:
        base_query = base_query.where(Todo.status == status)

    # Rendezés (SQL Server-kompatibilis!)
    filtered_query = base_query.order_by(
        case((Todo.status == "done", 1), else_=0),
        case((Todo.deadline.is_(None), 1), else_=0),
        Todo.deadline.asc(),
        Todo.created_at.asc(),
    )

    all_todos_count = session.exec(count_query).one()
    filtered_todos = session.exec(filtered_query).all()

    return {"all_count": all_todos_count, "filtered": filtered_todos}


@router.get("/upcoming")
def get_upcoming_todos(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
):
    HU_TZ = ZoneInfo("Europe/Budapest")
    now_local = datetime.now(HU_TZ)
    today = now_local.date()

    tomorrow = today + timedelta(days=1)

    # Hét végének helyes számítása (vasárnap)
    days_until_sunday = (6 - today.weekday()) % 7
    if days_until_sunday == 0:  # Ha ma vasárnap van
        days_until_sunday = 7  # Következő vasárnap
    end_of_week_date = today + timedelta(days=days_until_sunday)

    # Query feltételek - ha naive datetime-okat tárol az adatbázis, akkor naive feltételeket használunk
    today_start = datetime.combine(today, datetime.min.time())
    end_of_week = datetime.combine(end_of_week_date, datetime.max.time())

    query = (
        select(Todo)
        .where(
            Todo.user_id == current_user.id,
            Todo.deadline >= today_start,
            Todo.deadline <= end_of_week,
            Todo.status != "done",
        )
        .order_by(Todo.deadline.asc())
    )

    todos = session.exec(query).all()

    grouped_todos = {"today": [], "tomorrow": [], "this_week": []}

    for todo in todos:
        # Ha naive datetime, akkor naive-ként kezeljük
        if todo.deadline.tzinfo is None:
            deadline_date = todo.deadline.date()
        else:
            deadline_date = todo.deadline.astimezone(timezone.utc).date()

        if deadline_date == today:
            grouped_todos["today"].append(todo)
            grouped_todos["this_week"].append(todo)
        elif deadline_date == tomorrow:
            grouped_todos["tomorrow"].append(todo)
            grouped_todos["this_week"].append(todo)
        else:
            grouped_todos["this_week"].append(todo)

    # Stats lekérdezés
    query = (
        select(Todo.category, func.count(Todo.id).label("count"))
        .where(Todo.user_id == current_user.id)
        .group_by(Todo.category)
    )
    stats_results = session.exec(query).all()

    stats = {"personal": 0, "work": 0, "development": 0}

    for category, count in stats_results:
        if category in stats:
            stats[category] = count

    return {
        "upcoming": grouped_todos,
        "stats": {
            "personal": stats["personal"],
            "work": stats["work"],
            "development": stats["development"],
        },
    }


@router.get("/stats")
def get_todo_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
):
    # SQL query a kategóriánkénti csoportosításhoz
    query = (
        select(Todo.category, func.count(Todo.id).label("count"))
        .where(Todo.user_id == current_user.id)
        .group_by(Todo.category)
    )

    results = session.exec(query).all()

    # Alapértelmezett értékek minden kategóriához
    stats = {"personal": 0, "work": 0, "development": 0, "total": 0}

    # Feltöltjük a tényleges értékekkel

    for category, count in results:
        if category in stats:
            stats[category] = count

    return [
        {"name": "personal", "count": stats["personal"]},
        {"name": "work", "count": stats["work"]},
        {"name": "development", "count": stats["development"]},
    ]


@router.get("/today")
def get_todays_todos(
    current_user: Annotated[User, Depends(get_current_user)], session: SessionDep
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    done_stmt = select(Todo).where(
        Todo.user_id == current_user.id,
        Todo.status == "done",
        Todo.completed_at >= today_start,
        Todo.completed_at < today_end,
    )
    done_todos = session.exec(done_stmt).all()

    due_stmt = select(Todo).where(
        Todo.user_id == current_user.id,
        Todo.status != "done",
        Todo.deadline >= today_start,
        Todo.deadline < today_end,
    )
    due_todos = session.exec(due_stmt).all()

    def group_by_category(todos):
        grouped = defaultdict(list)
        for todo in todos:
            grouped[todo.category].append(todo)

        # minden kategória szerepeljen (még ha üres is)
        for category in ["personal", "work", "development"]:
            grouped.setdefault(category, [])
        return dict(grouped)

    return {
        "done_today": group_by_category(done_todos),
        "due_today": group_by_category(due_todos),
    }


@router.post("/create", status_code=status.HTTP_201_CREATED)
def create_todo(
    todo: TodoCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
):
    todo_data = todo.model_dump()

    completed_at = None
    if todo_data.get("status") == "done":
        completed_at = datetime.now(timezone.utc)

    db_todo = Todo(**todo_data, user_id=current_user.id, completed_at=completed_at)

    session.add(db_todo)
    session.commit()
    session.refresh(db_todo)
    return db_todo


@router.patch("/{todo_id}")
def update_todo(
    todo_id: int,
    todo_update: TodoUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
):
    db_todo = session.get(Todo, todo_id)

    if not db_todo or db_todo.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Todo not found")

    update_data = todo_update.model_dump(exclude_unset=True)

    new_status = update_data.get("status")
    if new_status is not None:
        if new_status == "done":
            db_todo.completed_at = datetime.now(timezone.utc)
        else:
            db_todo.completed_at = None

    for field, value in update_data.items():
        setattr(db_todo, field, value)

    db_todo.modified_at = datetime.now(timezone.utc)

    session.add(db_todo)
    session.commit()
    session.refresh(db_todo)
    return db_todo


@router.delete("/{todo_id}")
def delete_todo(
    todo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
):
    todo = session.get(Todo, todo_id)
    if not todo or todo.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Todo not found")
    session.delete(todo)
    session.commit()
    return {"ok": True}
