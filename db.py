"""Data layer: models, password hashing, role-scoped data access, safe SQL."""
import os, hashlib, hmac, re, sqlite3
import pandas as pd
from sqlalchemy import (create_engine, Column, Integer, String, Float, Boolean,
                        DateTime, ForeignKey, UniqueConstraint, select, func, case, text, inspect)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timedelta

def _url():
    try:
        import streamlit as st
        if "DATABASE_URL" in st.secrets: return st.secrets["DATABASE_URL"]
    except Exception: pass
    return os.getenv("DATABASE_URL", "sqlite:///campuspulse.db")

engine = create_engine(_url(), future=True)
Session = sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

class University(Base):
    __tablename__ = "universities"
    id = Column(Integer, primary_key=True); name = Column(String, unique=True, nullable=False)
class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    university_id = Column(Integer, ForeignKey("universities.id"), nullable=False)
    name = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("university_id", "name"),)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    university_id = Column(Integer, ForeignKey("universities.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"))
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False); designation = Column(String); faculty_id = Column(String)
    role = Column(String, default="faculty")  # faculty | hod | admin
    pw_hash = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    must_change_pw = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    failed_logins = Column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until = Column(DateTime)
class Batch(Base):
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True)
    university_id = Column(Integer, ForeignKey("universities.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False); programme = Column(String); academic_year = Column(String)
    semester = Column(Integer); section = Column(String); subject = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    students = relationship("Student", cascade="all, delete-orphan")
class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    student_id = Column(String, nullable=False); name = Column(String)
    attendance = Column(Float); marks = Column(Float); quiz_submitted = Column(Boolean)
    quiz_marks = Column(Float); quiz_total = Column(Float); assignment = Column(Float); exam = Column(Float)
    __table_args__ = (UniqueConstraint("batch_id", "student_id"),)  # no duplicate students per batch
class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True); university_id = Column(Integer, ForeignKey("universities.id"), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id")); action = Column(String, nullable=False)
    target = Column(String); detail = Column(String); created_at = Column(DateTime, default=datetime.utcnow)
class QueryHistory(Base):
    __tablename__ = "query_history"
    id = Column(Integer, primary_key=True); user_id = Column(Integer, ForeignKey("users.id"))
    question = Column(String); sql = Column(String); created_at = Column(DateTime, default=datetime.utcnow)

_NEW_USER_COLS = {"active": "BOOLEAN NOT NULL DEFAULT TRUE", "must_change_pw": "BOOLEAN NOT NULL DEFAULT FALSE",
                  "failed_logins": "INTEGER NOT NULL DEFAULT 0", "locked_until": "TIMESTAMP"}
def migrate(eng):
    """Adds Phase 3 columns to a database created by an earlier phase (safe to run repeatedly)."""
    insp = inspect(eng)
    if not insp.has_table("users"): return
    have = {c["name"] for c in insp.get_columns("users")}
    with eng.begin() as con:
        for name, ddl in _NEW_USER_COLS.items():
            if name not in have: con.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
def init_db(): Base.metadata.create_all(engine); migrate(engine)

# ---- passwords (stdlib scrypt, per-user salt) ----
def hash_pw(pw):
    salt = os.urandom(16); h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + h.hex()
def check_pw(pw, stored):
    salt, h = stored.split("$")
    return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex(), h)

def register_faculty(s, university, department, email, name, pw, designation, faculty_id):
    if len(pw) < 8: raise ValueError("Password must be at least 8 characters.")
    if s.scalar(select(User).where(User.email == email.lower().strip())): raise ValueError("Email already registered.")
    uni = s.scalar(select(University).where(University.name == university.strip())) or University(name=university.strip())
    s.add(uni); s.flush()
    dep = s.scalar(select(Department).where(Department.university_id == uni.id, Department.name == department.strip())) \
          or Department(university_id=uni.id, name=department.strip())
    s.add(dep); s.flush()
    u = User(university_id=uni.id, department_id=dep.id, email=email.lower().strip(), full_name=name.strip(),
             designation=designation, faculty_id=faculty_id, role="faculty", pw_hash=hash_pw(pw))
    s.add(u); s.commit(); return u
class AccountLocked(Exception): pass
MAX_FAILS, LOCK_MINUTES = 5, 15
_DUMMY = hash_pw("dummy-password")  # so unknown emails cost the same time as known ones
def login(s, email, pw):
    u = s.scalar(select(User).where(User.email == email.lower().strip()))
    if u is None: check_pw(pw, _DUMMY); return None
    now = datetime.utcnow()
    if u.locked_until and u.locked_until > now: raise AccountLocked(f"Too many attempts. Try again in {LOCK_MINUTES} minutes or ask your administrator.")
    if check_pw(pw, u.pw_hash) and u.active:
        u.failed_logins = 0; u.locked_until = None; s.commit(); return u
    u.failed_logins = (u.failed_logins or 0) + 1
    if u.failed_logins >= MAX_FAILS: u.locked_until = now + timedelta(minutes=LOCK_MINUTES); u.failed_logins = 0
    s.commit(); return None
def change_password(s, user_id, old, new):
    u = s.get(User, user_id)
    if not check_pw(old, u.pw_hash): raise ValueError("Current password is incorrect.")
    if len(new) < 8: raise ValueError("New password must be at least 8 characters.")
    if new == old: raise ValueError("New password must be different.")
    u.pw_hash = hash_pw(new); u.must_change_pw = False; s.commit(); return u

# ---- role-scoped access: every read goes through here ----
def visible_batches(s, u):
    q = select(Batch).where(Batch.university_id == u.university_id)
    if u.role == "faculty": q = q.where(Batch.owner_id == u.id)
    elif u.role == "hod": q = q.where(Batch.department_id == u.department_id)
    return list(s.scalars(q.order_by(Batch.created_at.desc())))
def get_batch(s, u, batch_id):
    """Returns batch only if the user may see it (blocks ID tampering)."""
    return next((b for b in visible_batches(s, u) if b.id == batch_id), None)
def can_edit(u, b): return b.owner_id == u.id
def batch_df(s, u, batch_ids=None):
    ids = [b.id for b in visible_batches(s, u) if batch_ids is None or b.id in batch_ids]
    if not ids: return pd.DataFrame()
    q = (select(Student, Batch.name.label("batch"), Batch.semester, Department.name.label("department"), User.full_name.label("faculty"))
         .join(Batch, Student.batch_id == Batch.id).join(Department, Batch.department_id == Department.id)
         .join(User, Batch.owner_id == User.id).where(Batch.id.in_(ids)))
    rows = s.execute(q).all()
    return pd.DataFrame([dict(batch_id=r.Student.batch_id, batch=r.batch, department=r.department, faculty=r.faculty,
        semester=r.semester, student_id=r.Student.student_id, name=r.Student.name, attendance=r.Student.attendance,
        marks=r.Student.marks, quiz_submitted=r.Student.quiz_submitted, quiz_marks=r.Student.quiz_marks,
        quiz_total=r.Student.quiz_total, assignment=r.Student.assignment, exam=r.Student.exam) for r in rows])

def save_students(s, batch, df, mode="update"):
    """mode 'replace' wipes batch first; 'update' upserts by student_id. Returns (added, updated)."""
    if mode == "replace":
        for st in list(batch.students): s.delete(st)
        s.flush(); s.expire(batch, ["students"])  # drop stale collection so deleted rows aren't reused
    existing = {x.student_id: x for x in batch.students}; add = upd = 0
    for r in df.to_dict("records"):
        r = {k: (None if pd.isna(v) else v) for k, v in r.items()}
        st = existing.get(r["student_id"])
        if st: upd += 1
        else: st = Student(batch_id=batch.id, student_id=r["student_id"]); s.add(st); existing[r["student_id"]] = st; add += 1
        for k, v in r.items():
            if k != "student_id": setattr(st, k, v)
    s.commit(); s.expire(batch, ["students"]); return add, upd

def department_summary(s, u):
    """Aggregated only (no student rows). Admin: all depts in own university. HOD: own dept."""
    if u.role not in ("hod", "admin"): raise PermissionError
    q = (select(Department.name, Batch.semester, func.count(Student.id), func.avg(Student.marks), func.avg(Student.attendance),
                func.avg(case((Student.quiz_submitted == True, 100.0), else_=0.0)))  # noqa: E712
         .join(Batch, Batch.department_id == Department.id).join(Student, Student.batch_id == Batch.id)
         .where(Department.university_id == u.university_id).group_by(Department.name, Batch.semester))
    if u.role == "hod": q = q.where(Department.id == u.department_id)
    return pd.DataFrame(s.execute(q).all(), columns=["department", "semester", "students", "avg_marks", "avg_attendance", "quiz_rate"])

# ---- safe NL->SQL execution: runs on an in-memory copy of ONLY the user's authorized rows ----
_BAD = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace|truncate|vacuum)\b", re.I)
def run_safe_sql(sql, df):
    sql = sql.strip().rstrip(";")
    if ";" in sql or not re.match(r"(?is)^\s*(select|with)\b", sql) or _BAD.search(sql):
        raise PermissionError("Only a single read-only SELECT query is allowed.")
    con = sqlite3.connect(":memory:"); df.to_sql("students", con, index=False)
    try: return pd.read_sql_query(sql, con)
    finally: con.close()

# ---- Phase 2: administration (all checks enforced here, not in the UI) ----
def _need(u, *roles):
    if u.role not in roles: raise PermissionError("You do not have permission for this action.")
def list_departments(s, u):
    return list(s.scalars(select(Department).where(Department.university_id == u.university_id).order_by(Department.name)))
def audit(s, u, action, target="", detail=""):
    """Adds an audit row; committed together with the caller's change."""
    s.add(AuditLog(university_id=u.university_id, actor_id=u.id, action=action, target=str(target), detail=str(detail)))
def list_audit(s, u, limit=200):
    _need(u, "admin")
    rows = s.execute(select(AuditLog, User.full_name).outerjoin(User, AuditLog.actor_id == User.id)
        .where(AuditLog.university_id == u.university_id).order_by(AuditLog.id.desc()).limit(limit)).all()
    return pd.DataFrame([dict(when=r.AuditLog.created_at, by=r.full_name, action=r.AuditLog.action, target=r.AuditLog.target, detail=r.AuditLog.detail) for r in rows])
def add_department(s, u, name):
    _need(u, "admin"); name = name.strip()
    if not name: raise ValueError("Department name is required.")
    if s.scalar(select(Department).where(Department.university_id == u.university_id, Department.name == name)): raise ValueError("Department already exists.")
    d = Department(university_id=u.university_id, name=name); s.add(d); audit(s, u, 'department_added', name); s.commit(); return d
def list_users(s, u):
    _need(u, "admin", "hod")
    q = select(User).where(User.university_id == u.university_id)
    if u.role == "hod": q = q.where(User.department_id == u.department_id)
    return list(s.scalars(q.order_by(User.full_name)))
def create_user(s, u, email, name, pw, department_id, role="faculty"):
    _need(u, "admin")
    if role not in ("faculty", "hod"): raise ValueError("Role must be faculty or hod.")
    if len(pw) < 8: raise ValueError("Password must be at least 8 characters.")
    if department_id not in [d.id for d in list_departments(s, u)]: raise PermissionError("Unknown department.")
    if s.scalar(select(User).where(User.email == email.lower().strip())): raise ValueError("Email already registered.")
    n = User(university_id=u.university_id, department_id=department_id, email=email.lower().strip(), full_name=name.strip(),
             role=role, pw_hash=hash_pw(pw), must_change_pw=True); s.add(n); audit(s, u, 'user_created', n.email, role); s.commit(); return n
def set_role(s, u, user_id, role):
    _need(u, "admin")
    if role not in ("faculty", "hod"): raise ValueError("Role must be faculty or hod.")
    t = s.get(User, user_id)
    if t is None or t.university_id != u.university_id: raise PermissionError("User not found in your university.")
    if t.id == u.id or t.role == "admin": raise PermissionError("Admin accounts cannot be changed here.")
    t.role = role; audit(s, u, 'role_changed', t.email, role); s.commit(); return t
def trend_summary(s, u):
    """Weighted averages per department and academic year (aggregated only)."""
    _need(u, "hod", "admin")
    q = (select(Department.name, Batch.academic_year, func.count(Student.id), func.avg(Student.marks), func.avg(Student.attendance))
         .join(Batch, Batch.department_id == Department.id).join(Student, Student.batch_id == Batch.id)
         .where(Department.university_id == u.university_id).group_by(Department.name, Batch.academic_year))
    if u.role == "hod": q = q.where(Department.id == u.department_id)
    return pd.DataFrame(s.execute(q).all(), columns=["department", "academic_year", "students", "avg_marks", "avg_attendance"])

def _managed_target(s, u, user_id):
    _need(u, "admin"); t = s.get(User, user_id)
    if t is None or t.university_id != u.university_id: raise PermissionError("User not found in your university.")
    if t.id == u.id or t.role == "admin": raise PermissionError("Admin accounts cannot be changed here.")
    return t
def admin_reset_password(s, u, user_id, temp_pw):
    t = _managed_target(s, u, user_id)
    if len(temp_pw) < 8: raise ValueError("Temporary password must be at least 8 characters.")
    t.pw_hash = hash_pw(temp_pw); t.must_change_pw = True; t.failed_logins = 0; t.locked_until = None; audit(s, u, 'password_reset', t.email); s.commit(); return t
def set_active(s, u, user_id, active):
    t = _managed_target(s, u, user_id); t.active = bool(active); audit(s, u, 'activated' if active else 'deactivated', t.email); s.commit(); return t
