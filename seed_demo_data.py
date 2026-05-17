# seed_demo_data.py – PostgreSQL version – realistic demo data
# Run after seed_user.py to populate your Supabase/Render DB

import psycopg2
import json
import os
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/taskflo")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Clear existing data (safe, you can re‑run any time)
for table in ["tasks", "projects", "comments", "activities", "notifications", "files"]:
    cur.execute(f"DELETE FROM {table}")

now = datetime.utcnow()

# ---------- PROJECTS ----------
projects = [
    {
        "id": "proj-1",
        "title": "Marketing Campaign Q3",
        "description": "Plan and execute the Q3 marketing campaign across email, social media, and paid ads.",
        "created_by": "a1",
        "deadline": (now + timedelta(days=45)).strftime("%Y-%m-%d"),
        "progress": 40,
        "team": json.dumps(["a1", "m1", "m2", "m3"]),
        "milestones": json.dumps([
            {"name":"Strategy","status":"completed","date":(now - timedelta(days=10)).strftime("%Y-%m-%d")},
            {"name":"Content Creation","status":"in-progress","date":None},
            {"name":"Launch","status":"upcoming","date":None}
        ])
    },
    {
        "id": "proj-2",
        "title": "HR Onboarding Portal",
        "description": "Build an internal portal for new hires: document uploads, task checklists, and training modules.",
        "created_by": "a2",
        "deadline": (now + timedelta(days=60)).strftime("%Y-%m-%d"),
        "progress": 65,
        "team": json.dumps(["a2", "m4", "m5", "m6"]),
        "milestones": json.dumps([
            {"name":"Requirements","status":"completed","date":(now - timedelta(days=20)).strftime("%Y-%m-%d")},
            {"name":"Development","status":"completed","date":(now - timedelta(days=5)).strftime("%Y-%m-%d")},
            {"name":"Testing","status":"in-progress","date":None},
            {"name":"Release","status":"upcoming","date":None}
        ])
    },
    {
        "id": "proj-3",
        "title": "API Redesign",
        "description": "Refactor the public API for v2 with rate limiting, better error handling, and OpenAPI specs.",
        "created_by": "a1",
        "deadline": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
        "progress": 20,
        "team": json.dumps(["a1", "m3", "m6"]),
        "milestones": json.dumps([
            {"name":"Specification","status":"completed","date":(now - timedelta(days=3)).strftime("%Y-%m-%d")},
            {"name":"Implementation","status":"in-progress","date":None},
            {"name":"Review","status":"upcoming","date":None}
        ])
    },
    {
        "id": "proj-4",
        "title": "Customer Feedback Dashboard",
        "description": "Create a real-time analytics dashboard for customer feedback and NPS scores.",
        "created_by": "a2",
        "deadline": (now + timedelta(days=20)).strftime("%Y-%m-%d"),
        "progress": 10,
        "team": json.dumps(["a2", "m1", "m2", "m4", "m5"]),
        "milestones": json.dumps([
            {"name":"Data Pipeline","status":"completed","date":(now - timedelta(days=2)).strftime("%Y-%m-%d")},
            {"name":"UI/UX Design","status":"in-progress","date":None},
            {"name":"Integration","status":"upcoming","date":None}
        ])
    }
]

for p in projects:
    cur.execute(
        "INSERT INTO projects (id, title, description, created_by, deadline, status, progress, team, milestones) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (p["id"], p["title"], p["description"], p["created_by"], p["deadline"],
         "ACTIVE", p["progress"], p["team"], p["milestones"])
    )

# ---------- TASKS ----------
tasks = [
    # proj-1 tasks
    {"id":"task-1-1","project_id":"proj-1","title":"Market Research Report",
     "description":"Analyze competitor campaigns and audience segments. Produce a 10-page report.",
     "assignee_ids":["m1"],"assigned_by":"a1","priority":"HIGH",
     "deadline":(now+timedelta(days=7)).strftime("%Y-%m-%d"),"status":"IN_PROGRESS","progress":50,
     "checklist":json.dumps([{"id":"c1","text":"Gather competitor data","done":True},
                              {"id":"c2","text":"Survey target audience","done":False},
                              {"id":"c3","text":"Write report","done":False}])},
    {"id":"task-1-2","project_id":"proj-1","title":"Social Media Content Calendar",
     "description":"Create and schedule 30 posts for the next month across Twitter, LinkedIn, and Instagram.",
     "assignee_ids":["m2","m3"],"assigned_by":"a1","priority":"MEDIUM",
     "deadline":(now+timedelta(days=12)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-1-3","project_id":"proj-1","title":"Email Newsletter Template",
     "description":"Design a reusable HTML email template matching the new brand guidelines.",
     "assignee_ids":["m2"],"assigned_by":"a1","priority":"LOW",
     "deadline":(now+timedelta(days=5)).strftime("%Y-%m-%d"),"status":"APPROVED","progress":100,
     "review_status":"APPROVED","checklist":"[]"},
    {"id":"task-1-4","project_id":"proj-1","title":"Landing Page A/B Test",
     "description":"Set up and run an A/B test for the new campaign landing page using VWO.",
     "assignee_ids":["m3"],"assigned_by":"a1","priority":"HIGH",
     "deadline":(now+timedelta(days=10)).strftime("%Y-%m-%d"),"status":"IN_PROGRESS","progress":30,"checklist":"[]"},
    {"id":"task-1-5","project_id":"proj-1","title":"PPC Ad Copy",
     "description":"Write and optimize 10 Google Ads headlines and descriptions.",
     "assignee_ids":["m1"],"assigned_by":"a1","priority":"MEDIUM",
     "deadline":(now+timedelta(days=14)).strftime("%Y-%m-%d"),"status":"SUBMITTED","progress":100,
     "review_status":"PENDING","checklist":"[]"},
    # proj-2 tasks
    {"id":"task-2-1","project_id":"proj-2","title":"Database Schema Design",
     "description":"Design PostgreSQL schema for employee profiles, documents, and training records.",
     "assignee_ids":["m4"],"assigned_by":"a2","priority":"CRITICAL",
     "deadline":(now-timedelta(days=2)).strftime("%Y-%m-%d"),"status":"IN_PROGRESS","progress":80,
     "checklist":"[]"},
    {"id":"task-2-2","project_id":"proj-2","title":"Frontend Dashboard UI",
     "description":"Build the main dashboard with React, showing onboarding progress and task lists.",
     "assignee_ids":["m5"],"assigned_by":"a2","priority":"HIGH",
     "deadline":(now+timedelta(days=10)).strftime("%Y-%m-%d"),"status":"IN_PROGRESS","progress":55,
     "checklist":"[]"},
    {"id":"task-2-3","project_id":"proj-2","title":"Document Upload Service",
     "description":"Implement secure file upload with virus scanning and PDF preview generation.",
     "assignee_ids":["m6"],"assigned_by":"a2","priority":"HIGH",
     "deadline":(now+timedelta(days=12)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-2-4","project_id":"proj-2","title":"Training Module API",
     "description":"Create REST endpoints for assigning and tracking training courses.",
     "assignee_ids":["m4","m5"],"assigned_by":"a2","priority":"MEDIUM",
     "deadline":(now+timedelta(days=20)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-2-5","project_id":"proj-2","title":"Integration Tests",
     "description":"Write Cypress integration tests for the onboarding flow.",
     "assignee_ids":["m6"],"assigned_by":"a2","priority":"LOW",
     "deadline":(now+timedelta(days=25)).strftime("%Y-%m-%d"),"status":"APPROVED","progress":100,
     "review_status":"APPROVED","checklist":"[]"},
    # proj-3 tasks
    {"id":"task-3-1","project_id":"proj-3","title":"OpenAPI Spec Draft",
     "description":"Write the OpenAPI 3.0 specification for the v2 public API.",
     "assignee_ids":["m3"],"assigned_by":"a1","priority":"CRITICAL",
     "deadline":(now+timedelta(days=5)).strftime("%Y-%m-%d"),"status":"IN_PROGRESS","progress":70,
     "checklist":"[]"},
    {"id":"task-3-2","project_id":"proj-3","title":"Rate Limiting Middleware",
     "description":"Implement token bucket rate limiting using Redis.",
     "assignee_ids":["m6"],"assigned_by":"a1","priority":"HIGH",
     "deadline":(now+timedelta(days=8)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-3-3","project_id":"proj-3","title":"Error Response Standardization",
     "description":"Standardize all error responses to follow RFC 7807 (Problem Details).",
     "assignee_ids":["m3","m6"],"assigned_by":"a1","priority":"MEDIUM",
     "deadline":(now+timedelta(days=15)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-3-4","project_id":"proj-3","title":"Authentication Migration",
     "description":"Migrate from custom JWT to OAuth2 with PKCE support.",
     "assignee_ids":["m6"],"assigned_by":"a1","priority":"HIGH",
     "deadline":(now+timedelta(days=18)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-3-5","project_id":"proj-3","title":"API Documentation Generator",
     "description":"Create a tool that auto-generates documentation from the OpenAPI spec.",
     "assignee_ids":["m3"],"assigned_by":"a1","priority":"LOW",
     "deadline":(now+timedelta(days=22)).strftime("%Y-%m-%d"),"status":"IN_PROGRESS","progress":25,
     "checklist":"[]"},
    # proj-4 tasks
    {"id":"task-4-1","project_id":"proj-4","title":"Data Warehouse Connector",
     "description":"Build connector to pull NPS and survey data from BigQuery.",
     "assignee_ids":["m1"],"assigned_by":"a2","priority":"CRITICAL",
     "deadline":(now+timedelta(days=3)).strftime("%Y-%m-%d"),"status":"IN_PROGRESS","progress":45,
     "checklist":"[]"},
    {"id":"task-4-2","project_id":"proj-4","title":"Real-time Dashboard UI",
     "description":"Design the main dashboard with charts for NPS trend, sentiment, and feedback categories.",
     "assignee_ids":["m2","m4"],"assigned_by":"a2","priority":"HIGH",
     "deadline":(now+timedelta(days=8)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-4-3","project_id":"proj-4","title":"Sentiment Analysis Pipeline",
     "description":"Integrate a sentiment analysis microservice to classify feedback in real time.",
     "assignee_ids":["m5"],"assigned_by":"a2","priority":"HIGH",
     "deadline":(now+timedelta(days=12)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-4-4","project_id":"proj-4","title":"Alerting Module",
     "description":"Set up alert rules for negative NPS spikes and send notifications via Slack/email.",
     "assignee_ids":["m1","m5"],"assigned_by":"a2","priority":"MEDIUM",
     "deadline":(now+timedelta(days=15)).strftime("%Y-%m-%d"),"status":"TODO","progress":0,"checklist":"[]"},
    {"id":"task-4-5","project_id":"proj-4","title":"Dashboard Permissions",
     "description":"Implement role-based access for viewing sensitive feedback data.",
     "assignee_ids":["m2"],"assigned_by":"a2","priority":"LOW",
     "deadline":(now+timedelta(days=18)).strftime("%Y-%m-%d"),"status":"IN_PROGRESS","progress":10,
     "checklist":"[]"}
]

for t in tasks:
    cur.execute(
        "INSERT INTO tasks (id, project_id, title, description, assigned_to, assigned_by, "
        "priority, urgency, status, review_status, progress, deadline, blocked, block_reason, "
        "dependencies, submission_note, attachments, checklist, acceptance_criteria, "
        "worked_on_by, version_history, current_viewers, last_updated) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (t["id"], t["project_id"], t["title"], t["description"],
         json.dumps(t["assignee_ids"]),
         t["assigned_by"],
         t["priority"],
         "URGENT" if t["priority"] == "CRITICAL" else "NORMAL",
         t["status"],
         t.get("review_status", ""),
         t.get("progress", 0),
         t["deadline"],
         0, "", "[]", "",
         "[]",
         t.get("checklist", "[]"),
         "[]", "[]", "[]", "[]",
         now.isoformat())
    )

# ---------- COMMENTS ----------
cur.execute(
    "INSERT INTO comments (id, task_id, user_id, content, parent_id, created_at, reactions) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
    ("cmt-1", "task-1-1", "a1", "@Member One Remember to include competitor pricing analysis.",
     None, (now - timedelta(days=1)).isoformat(), json.dumps({"👍":2}))
)
cur.execute(
    "INSERT INTO comments (id, task_id, user_id, content, parent_id, created_at, reactions) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
    ("cmt-2", "task-1-1", "m1", "Got it! Will add a section on pricing.",
     "cmt-1", (now - timedelta(hours=12)).isoformat(), "{}")
)

# ---------- ACTIVITIES ----------
cur.execute(
    "INSERT INTO activities (id, user_id, action, entity_type, entity_id, created_at) "
    "VALUES (%s,%s,%s,%s,%s,%s)",
    ("act-1", "a1", 'created project "Marketing Campaign Q3"', "Project", "proj-1",
     (now - timedelta(days=20)).isoformat())
)
cur.execute(
    "INSERT INTO activities (id, user_id, action, entity_type, entity_id, created_at) "
    "VALUES (%s,%s,%s,%s,%s,%s)",
    ("act-2", "m1", 'started working on "Market Research Report"', "Task", "task-1-1",
     (now - timedelta(days=2)).isoformat())
)

# ---------- NOTIFICATIONS ----------
cur.execute(
    "INSERT INTO notifications (id, user_id, message, type, read, created_at, target_task_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
    ("notif-1", "m1", 'New task assigned: "Market Research Report"', "ASSIGNED", 0,
     (now - timedelta(days=2)).isoformat(), "task-1-1")
)
cur.execute(
    "INSERT INTO notifications (id, user_id, message, type, read, created_at, target_task_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
    ("notif-2", "a1", 'Member One submitted "PPC Ad Copy" for review', "SUBMITTED", 1,
     (now - timedelta(hours=8)).isoformat(), "task-1-5")
)

conn.commit()
cur.close()
conn.close()
print("Demo data seeded successfully.")