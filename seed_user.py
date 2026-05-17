import psycopg2
from passlib.context import CryptContext
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/teamflow")
PASSWORD = "123456"

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
hashed = pwd_context.hash(PASSWORD)

users = [
    {"id": "a1", "name": "Admin One",   "email": "admin1@gmail.com", "role": "ADMIN",  "department": "Management"},
    {"id": "a2", "name": "Admin Two",   "email": "admin2@gmail.com", "role": "ADMIN",  "department": "Management"},
    {"id": "m1", "name": "Member One",   "email": "member1@gmail.com", "role": "MEMBER", "department": "General"},
    {"id": "m2", "name": "Member Two",   "email": "member2@gmail.com", "role": "MEMBER", "department": "General"},
    {"id": "m3", "name": "Member Three", "email": "member3@gmail.com", "role": "MEMBER", "department": "General"},
    {"id": "m4", "name": "Member Four",  "email": "member4@gmail.com", "role": "MEMBER", "department": "General"},
    {"id": "m5", "name": "Member Five",  "email": "member5@gmail.com", "role": "MEMBER", "department": "General"},
    {"id": "m6", "name": "Member Six",   "email": "member6@gmail.com", "role": "MEMBER", "department": "General"},
]

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
for u in users:
    cur.execute("SELECT id FROM users WHERE id = %s OR email = %s", (u["id"], u["email"]))
    if cur.fetchone():
        print(f"Skipping {u['name']} (already exists)")
        continue
    cur.execute(
        "INSERT INTO users (id, name, email, password_hash, role, department, avatar, status, last_active, is_demo) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (u["id"], u["name"], u["email"], hashed, u["role"], u["department"], u["name"][0].upper(), "offline", "now", 0)
    )
    print(f"Added {u['name']} ({u['role']})")
conn.commit()
cur.close()
conn.close()
print("Done seeding users.")