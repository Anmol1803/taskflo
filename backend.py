# ============================================================
# TeamFlow Backend – PostgreSQL · Multi-Assignee · RBAC · Real-Time
# ============================================================
import os, uuid, json, time, re, hashlib
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File,
    Depends, HTTPException, Header, Request, Query
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
import jwt

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

limiter = Limiter(key_func=get_remote_address)

# ---------- CONFIG ----------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/teamflow")
UPLOAD_DIR = "uploads"
JWT_SECRET = os.getenv("JWT_SECRET", "teamflow-demo-secret-2026")
JWT_REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET", "teamflow-refresh-secret-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
ALLOWED_UPLOAD_TYPES = [
    "image/jpeg", "image/png", "image/gif",
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "application/zip"
]
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

app = FastAPI(title="TeamFlow API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DATABASE POOL ----------
pool = SimpleConnectionPool(1, 10, DATABASE_URL)

def get_db_conn():
    """Get a connection from the pool."""
    conn = pool.getconn()
    conn.cursor_factory = RealDictCursor
    return conn

def return_db_conn(conn):
    """Return connection to pool."""
    pool.putconn(conn)

def init_db():
    """Create tables if they don't exist."""
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            role TEXT NOT NULL DEFAULT 'MEMBER',
            department TEXT,
            avatar TEXT,
            status TEXT DEFAULT 'offline',
            last_active TEXT,
            is_demo INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_by TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'ACTIVE',
            progress INTEGER DEFAULT 0,
            team JSONB DEFAULT '[]',
            milestones JSONB DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            assigned_to JSONB DEFAULT '[]',
            assigned_by TEXT,
            priority TEXT DEFAULT 'MEDIUM',
            urgency TEXT DEFAULT 'NORMAL',
            status TEXT DEFAULT 'TODO',
            review_status TEXT DEFAULT '',
            progress INTEGER DEFAULT 0,
            deadline TEXT,
            blocked INTEGER DEFAULT 0,
            block_reason TEXT DEFAULT '',
            dependencies JSONB DEFAULT '[]',
            submission_note TEXT DEFAULT '',
            attachments JSONB DEFAULT '[]',
            checklist JSONB DEFAULT '[]',
            acceptance_criteria JSONB DEFAULT '[]',
            worked_on_by JSONB DEFAULT '[]',
            version_history JSONB DEFAULT '[]',
            current_viewers JSONB DEFAULT '[]',
            last_updated TEXT
        );

        CREATE TABLE IF NOT EXISTS comments (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            content TEXT,
            parent_id TEXT,
            created_at TEXT,
            reactions JSONB DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            action TEXT,
            entity_type TEXT,
            entity_id TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            message TEXT,
            type TEXT,
            read INTEGER DEFAULT 0,
            created_at TEXT,
            target_task_id TEXT
        );

        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            original_name TEXT,
            mime_type TEXT,
            size INTEGER,
            storage_key TEXT,
            uploaded_by TEXT,
            uploaded_at TEXT
        );
    """)
    conn.commit()
    cur.close()
    return_db_conn(conn)

# Run table creation
init_db()

# ---------- PASSWORD HASHING ----------
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ---------- HELPERS ----------
def row_to_task(row: dict) -> dict:
    """Convert JSONB columns from strings to Python objects."""
    json_fields = ["dependencies", "attachments", "checklist", "acceptance_criteria",
                   "worked_on_by", "version_history", "current_viewers", "assigned_to",
                   "team", "milestones"]  # also for projects
    for field in json_fields:
        if field in row and row[field] is not None:
            # psycopg2 returns JSONB as Python dicts/lists automatically
            pass  # no need to load, they are already parsed
    return row

def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

def create_refresh_token(user_id: str) -> tuple[str, str]:
    token_id = uuid.uuid4().hex
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
        "jti": token_id
    }
    token = jwt.encode(payload, JWT_REFRESH_SECRET, algorithm=ALGORITHM)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, created_at) VALUES (%s,%s,%s,%s,%s)",
        (token_id, user_id, token_hash, expire.isoformat(), datetime.utcnow().isoformat())
    )
    conn.commit()
    cur.close()
    return_db_conn(conn)
    return token, token_id

def verify_refresh_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_REFRESH_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        token_id = payload.get("jti")
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM refresh_tokens WHERE id = %s AND revoked = 0", (token_id,))
        row = cur.fetchone()
        cur.close()
        return_db_conn(conn)
        if not row:
            return None
        if hashlib.sha256(token.encode()).hexdigest() != row["token_hash"]:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
            return None
        return payload["sub"]
    except:
        return None

def revoke_refresh_token(token_id: str):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE id = %s", (token_id,))
    conn.commit()
    cur.close()
    return_db_conn(conn)

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    return_db_conn(conn)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(user)

def admin_required(user: dict = Depends(get_current_user)):
    if user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def is_assigned_to_task(user_id: str, task: dict) -> bool:
    assignees = task.get("assigned_to", [])
    if isinstance(assignees, str):
        try:
            assignees = json.loads(assignees)
        except:
            assignees = []
    return user_id in assignees

# ---------- AUTH ----------
class UserLogin(BaseModel):
    user_id: str

class LoginEmail(BaseModel):
    email: str
    password: str

class SignupData(BaseModel):
    name: str
    email: EmailStr
    password: str
    department: str = "General"

class RefreshBody(BaseModel):
    refresh_token: str

class ProjectCreate(BaseModel):
    title: str
    description: str = ""
    deadline: str
    team: List[str] = []

# ---------- REACTIONS ----------
class ReactionAdd(BaseModel):
    emoji: str

@app.patch("/api/comments/{comment_id}/reaction")
async def add_reaction(comment_id: str, data: ReactionAdd,
                       current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM comments WHERE id = %s", (comment_id,))
    comment = cur.fetchone()
    if not comment:
        cur.close(); return_db_conn(conn)
        raise HTTPException(status_code=404, detail="Comment not found")
    reactions = comment["reactions"] if comment["reactions"] else {}
    reactions[data.emoji] = reactions.get(data.emoji, 0) + 1
    cur.execute("UPDATE comments SET reactions = %s WHERE id = %s",
                (json.dumps(reactions), comment_id))
    conn.commit()
    cur.close()
    return_db_conn(conn)
    await broadcast({"type": "reaction_update", "payload": {
        "commentId": comment_id,
        "reactions": reactions
    }})
    return {"id": comment_id, "reactions": reactions}

@app.post("/api/projects")
def create_project(data: ProjectCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Only admins can create projects")
    conn = get_db_conn()
    cur = conn.cursor()
    project_id = "p" + str(int(time.time() * 1000))
    cur.execute(
        "INSERT INTO projects (id, title, description, created_by, deadline, status, progress, team, milestones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (project_id, data.title, data.description, current_user["id"], data.deadline, "ACTIVE", 0, json.dumps(data.team), "[]")
    )
    conn.commit()
    cur.close()
    return_db_conn(conn)
    return {"id": project_id, "title": data.title}

@app.post("/auth/login")
@limiter.limit("5/minute")
def login_demo(body: UserLogin, request: Request):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s AND is_demo = 1", (body.user_id,))
    user = cur.fetchone()
    cur.close()
    return_db_conn(conn)
    if not user:
        raise HTTPException(status_code=404, detail="Demo user not found")
    user_dict = dict(user)
    access_token = create_access_token(user_dict["id"], user_dict["role"])
    refresh_token, _ = create_refresh_token(user_dict["id"])
    return {
        "user": user_dict,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@app.post("/auth/login-email")
@limiter.limit("5/minute")
def login_email(body: LoginEmail, request: Request):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (body.email,))
    user = cur.fetchone()
    cur.close()
    return_db_conn(conn)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not pwd_context.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user_dict = dict(user)
    access_token = create_access_token(user_dict["id"], user_dict["role"])
    refresh_token, _ = create_refresh_token(user_dict["id"])
    return {
        "user": user_dict,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@app.post("/auth/signup")
@limiter.limit("3/day")
def signup(body: SignupData, request: Request):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (body.email,))
    existing = cur.fetchone()
    if existing:
        cur.close(); return_db_conn(conn)
        raise HTTPException(status_code=400, detail="Email already registered")
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()["count"]
    role = "ADMIN" if count == 0 else "MEMBER"
    user_id = "u" + str(int(time.time() * 1000))[-4:]
    hashed = pwd_context.hash(body.password)
    cur.execute(
        "INSERT INTO users (id, name, email, password_hash, role, department, avatar, status, last_active, is_demo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (user_id, body.name, body.email, hashed, role, body.department, body.name[0].upper(), "offline", "now", 0)
    )
    conn.commit()
    cur.close()
    return_db_conn(conn)
    return {"message": "Account created", "user_id": user_id}

@app.post("/auth/refresh")
def refresh_token(body: RefreshBody):
    user_id = verify_refresh_token(body.refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    try:
        payload = jwt.decode(body.refresh_token, JWT_REFRESH_SECRET, algorithms=[ALGORITHM])
        revoke_refresh_token(payload["jti"])
    except:
        pass
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    return_db_conn(conn)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user_dict = dict(user)
    new_access = create_access_token(user_dict["id"], user_dict["role"])
    new_refresh, _ = create_refresh_token(user_dict["id"])
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer"
    }

@app.get("/api/users")
def get_users(current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, role, department, avatar, status FROM users")
    rows = cur.fetchall()
    cur.close()
    return_db_conn(conn)
    return [dict(r) for r in rows]

# ---------- TASKS ----------
class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_ids: Optional[List[str]] = None
    priority: Optional[str] = None
    urgency: Optional[str] = None
    status: Optional[str] = None
    review_status: Optional[str] = None
    progress: Optional[int] = None
    deadline: Optional[str] = None
    blocked: Optional[bool] = None
    block_reason: Optional[str] = None
    dependencies: Optional[List[str]] = None
    submission_note: Optional[str] = None
    attachments: Optional[List[dict]] = None
    checklist: Optional[List[dict]] = None
    acceptance_criteria: Optional[List[str]] = None
    worked_on_by: Optional[List[str]] = None
    version_history: Optional[List[dict]] = None
    current_viewers: Optional[List[str]] = None

class TaskCreate(BaseModel):
    title: str
    project_id: str
    assignee_ids: List[str] = []
    priority: str = "MEDIUM"
    deadline: str
    description: str = ""
    urgency: str = "NORMAL"

@app.get("/api/tasks")
def get_tasks(request: Request,
              skip: int = Query(0, ge=0),
              limit: int = Query(50, ge=1, le=100),
              current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    if current_user["role"] != "ADMIN":
        cur.execute("""
            SELECT DISTINCT t.* FROM tasks t
            CROSS JOIN jsonb_array_elements_text(t.assigned_to) AS assignee
            WHERE assignee = %s
            ORDER BY t.last_updated DESC
            LIMIT %s OFFSET %s
        """, (current_user["id"], limit, skip))
    else:
        cur.execute("SELECT * FROM tasks ORDER BY last_updated DESC LIMIT %s OFFSET %s", (limit, skip))
    rows = cur.fetchall()
    cur.close()
    return_db_conn(conn)
    return [row_to_task(dict(r)) for r in rows]

@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    row = cur.fetchone()
    cur.close()
    return_db_conn(conn)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    task = row_to_task(dict(row))
    if current_user["role"] != "ADMIN" and not is_assigned_to_task(current_user["id"], task):
        raise HTTPException(status_code=403, detail="Forbidden")
    return task

@app.patch("/api/tasks/{task_id}")
@limiter.limit("30/minute")
async def update_task(task_id: str, data: TaskUpdate, request: Request,
                      current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    task = cur.fetchone()
    if not task:
        cur.close(); return_db_conn(conn)
        raise HTTPException(status_code=404, detail="Task not found")
    task_dict = row_to_task(dict(task))
    if current_user["role"] != "ADMIN" and not is_assigned_to_task(current_user["id"], task_dict):
        cur.close(); return_db_conn(conn)
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = data.dict(exclude_unset=True)
    if "assignee_ids" in update_data:
        update_data["assigned_to"] = json.dumps(update_data.pop("assignee_ids"))
    json_fields = ["dependencies", "attachments", "checklist", "acceptance_criteria",
                   "worked_on_by", "version_history", "current_viewers"]
    for field in json_fields:
        if field in update_data and update_data[field] is not None:
            update_data[field] = json.dumps(update_data[field])

    update_data["last_updated"] = datetime.utcnow().isoformat()
    if "blocked" in update_data:
        update_data["blocked"] = 1 if update_data["blocked"] else 0

    set_clause = ", ".join(f"{k} = %s" for k in update_data)
    values = list(update_data.values()) + [task_id]
    cur.execute(f"UPDATE tasks SET {set_clause} WHERE id = %s", values)
    conn.commit()

    action = f'updated task "{task_dict["title"]}"'
    if "status" in update_data:
        action = f'changed status of "{task_dict["title"]}" to {update_data["status"]}'
    await log_activity(current_user["id"], action, "Task", task_id)

    cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    updated_task = row_to_task(dict(cur.fetchone()))
    cur.close()
    return_db_conn(conn)
    await broadcast({"type": "task_updated", "payload": updated_task})
    return updated_task

@app.post("/api/tasks")
@limiter.limit("20/minute")
async def create_task(data: TaskCreate, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Only admins can create tasks")
    conn = get_db_conn()
    cur = conn.cursor()
    task_id = "t" + str(int(time.time() * 1000))
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO tasks (id, project_id, title, description, assigned_to, assigned_by, priority, urgency, status, review_status, progress, deadline, blocked, block_reason, dependencies, submission_note, attachments, checklist, acceptance_criteria, worked_on_by, version_history, current_viewers, last_updated) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (task_id, data.project_id, data.title, data.description or "",
         json.dumps(data.assignee_ids), current_user["id"], data.priority, data.urgency,
         "TODO", "", 0, data.deadline, 0, "", "[]", "", "[]", "[]", "[]", "[]", "[]", "[]", now)
    )
    conn.commit()
    cur.close()
    return_db_conn(conn)
    for uid in data.assignee_ids:
        await create_notification(uid, f'New task assigned: "{data.title}"', "ASSIGNED", task_id)
    await log_activity(current_user["id"], f'created task "{data.title}"', "Task", task_id)
    return {"id": task_id, "title": data.title, "status": "TODO"}

# ---------- PROJECTS ----------
@app.get("/api/projects")
def get_projects(current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects")
    rows = cur.fetchall()
    cur.close()
    return_db_conn(conn)
    projects = []
    for r in rows:
        d = dict(r)
        # JSONB columns are already parsed
        if current_user["role"] != "ADMIN" and current_user["id"] not in d.get("team", []):
            continue
        projects.append(d)
    return projects

@app.get("/api/projects/{project_id}")
def get_project(project_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
    row = cur.fetchone()
    cur.close()
    return_db_conn(conn)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    d = dict(row)
    if current_user["role"] != "ADMIN" and current_user["id"] not in d.get("team", []):
        raise HTTPException(status_code=403, detail="Forbidden")
    return d

# ---------- COMMENTS ----------
class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[str] = None

@app.get("/api/comments/{task_id}")
def get_comments(task_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM comments WHERE task_id = %s", (task_id,))
    rows = cur.fetchall()
    cur.close()
    return_db_conn(conn)
    return [dict(r) for r in rows]

@app.post("/api/comments/{task_id}")
@limiter.limit("30/minute")
async def add_comment(task_id: str, data: CommentCreate, request: Request,
                      current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    comment_id = "c" + str(int(time.time() * 1000))
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO comments VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (comment_id, task_id, current_user["id"], data.content, data.parent_id, now, "{}")
    )
    conn.commit()
    cur.execute("SELECT * FROM comments WHERE id = %s", (comment_id,))
    new_comment = dict(cur.fetchone())
    cur.close()
    return_db_conn(conn)
    await handle_mentions(data.content, task_id, current_user["id"])
    await log_activity(current_user["id"], f'commented on task', "Task", task_id)
    return new_comment

# ---------- NOTIFICATIONS ----------
class NotificationCreate(BaseModel):
    userId: str
    message: str
    type: str
    targetTaskId: Optional[str] = None

class NotificationRead(BaseModel):
    read: bool = True

@app.get("/api/notifications")
def get_notifications(current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC", (current_user["id"],))
    rows = cur.fetchall()
    cur.close()
    return_db_conn(conn)
    return [dict(r) for r in rows]

@app.post("/api/notifications")
async def add_notification(data: NotificationCreate, current_user: dict = Depends(get_current_user)):
    await create_notification(data.userId, data.message, data.type, data.targetTaskId)
    return {"status": "ok"}

@app.patch("/api/notifications/{notif_id}/read")
def mark_notification_read(notif_id: str, body: NotificationRead = NotificationRead(read=True),
                           current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET read = %s WHERE id = %s AND user_id = %s",
                (1 if body.read else 0, notif_id, current_user["id"]))
    conn.commit()
    cur.close()
    return_db_conn(conn)
    return {"id": notif_id, "read": body.read}

# ---------- ACTIVITIES ----------
@app.get("/api/activities")
def get_activities(current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM activities ORDER BY created_at DESC LIMIT 50")
    rows = cur.fetchall()
    cur.close()
    return_db_conn(conn)
    return [dict(r) for r in rows]

# ---------- FILE UPLOAD ----------
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
@limiter.limit("10/minute")
async def upload_file(request: Request,
                      file: UploadFile = File(...),
                      current_user: dict = Depends(get_current_user)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed")
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    storage_name = f"{file_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, storage_name)
    with open(file_path, "wb") as f:
        f.write(content)
    size = len(content)
    now = datetime.utcnow().isoformat()
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO files VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (file_id, file.filename, file.content_type, size, file_path, current_user["id"], now)
    )
    conn.commit()
    cur.close()
    return_db_conn(conn)
    return {
        "id": file_id,
        "name": file.filename,
        "size": size,
        "type": file.content_type,
        "url": f"/uploads/{storage_name}"
    }

# ---------- ANALYTICS ----------
@app.get("/api/analytics/dashboard")
def analytics_dashboard(current_user: dict = Depends(admin_required)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks")
    tasks = [dict(r) for r in cur.fetchall()]
    cur.close()
    return_db_conn(conn)
    total = len(tasks)
    completed = sum(1 for t in tasks if t["status"] == "APPROVED")
    rate = int((completed / total) * 100) if total > 0 else 0
    pending = sum(1 for t in tasks if t["status"] == "SUBMITTED")
    overdue = sum(1 for t in tasks if t["status"] != "APPROVED" and t["deadline"] and
                 t["deadline"] < datetime.utcnow().isoformat())
    blocked = sum(1 for t in tasks if int(t.get("blocked", 0)) == 1)
    return {
        "totalTasks": total,
        "completionRate": rate,
        "pendingReviews": pending,
        "overdue": overdue,
        "blocked": blocked
    }

# ---------- WEBSOCKET ----------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_sockets: dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        for uid, sockets in list(self.user_sockets.items()):
            if websocket in sockets:
                sockets.remove(websocket)
                if not sockets:
                    del self.user_sockets[uid]

    def register_user(self, user_id: str, websocket: WebSocket):
        self.user_sockets.setdefault(user_id, []).append(websocket)

    async def broadcast(self, message: dict):
        msg = json.dumps(message)
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(msg)
            except:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to_user(self, user_id: str, message: dict):
        msg = json.dumps(message)
        sockets = self.user_sockets.get(user_id, [])
        dead = []
        for ws in sockets:
            try:
                await ws.send_text(msg)
            except:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    user_id = None
    try:
        data = await websocket.receive_json()
        if data.get("action") == "auth":
            token = data["token"]
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
                if payload.get("type") == "access":
                    user_id = payload["sub"]
                    manager.register_user(user_id, websocket)
                    await websocket.send_json({"type": "auth_ok"})
            except:
                await websocket.send_json({"type": "auth_error"})
                return
        else:
            await websocket.send_json({"type": "auth_required"})
            return

        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "typing":
                task_id = data.get("taskId")
                if task_id:
                    await manager.broadcast({
                        "type": "typing",
                        "payload": {"userId": user_id, "taskId": task_id}
                    })
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# ---------- BACKGROUND HELPERS ----------
async def log_activity(user_id: str, action: str, entity_type: str = "Task", entity_id: str = ""):
    conn = get_db_conn()
    cur = conn.cursor()
    aid = "a" + str(int(time.time() * 1000))
    now = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO activities VALUES (%s,%s,%s,%s,%s,%s)",
                (aid, user_id, action, entity_type, entity_id, now))
    conn.commit()
    cur.close()
    return_db_conn(conn)
    await broadcast({"type": "activity", "payload": {
        "userId": user_id, "action": action, "entityId": entity_id, "ts": now
    }})

async def create_notification(user_id: str, message: str, notif_type: str, target_task_id: str = None):
    conn = get_db_conn()
    cur = conn.cursor()
    nid = "n" + str(int(time.time() * 1000))
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO notifications VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (nid, user_id, message, notif_type, 0, now, target_task_id)
    )
    conn.commit()
    cur.close()
    return_db_conn(conn)
    await broadcast_to_user(user_id, {"type": "notification", "payload": {"message": message}})

async def handle_mentions(content: str, task_id: str, from_user_id: str):
    mentions = re.findall(r'@(\w+)', content)
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    all_users = {u["name"].lower(): u for u in [dict(r) for r in cur.fetchall()]}
    cur.close()
    return_db_conn(conn)
    from_name = None
    for u in all_users.values():
        if u["id"] == from_user_id:
            from_name = u["name"]
            break
    for name in mentions:
        lname = name.lower()
        user = all_users.get(lname)
        if user and user["id"] != from_user_id:
            message = f'{from_name} mentioned you in a comment'
            await create_notification(user["id"], message, "MENTION", task_id)

async def broadcast(message):
    await manager.broadcast(message)

async def broadcast_to_user(user_id, message):
    await manager.send_to_user(user_id, message)

# ---------- SERVE FRONTEND ----------
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

if os.path.isdir("dist"):
    app.mount("/", StaticFiles(directory="dist", html=True), name="frontend")


# ---------- Auto-seed if database is empty ----------
def auto_seed():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()["count"]
    cur.close()
    return_db_conn(conn)
    if count == 0:
        print("Database empty. Running seed scripts…")
        import subprocess, sys
        subprocess.run([sys.executable, "seed_user.py"])
        subprocess.run([sys.executable, "seed_demo_data.py"])
        print("Seeding complete.")

auto_seed()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))