import os, sys, tempfile, pytest
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
from db import *

@pytest.fixture()
def w():
    """Two universities. A: CSE (hod, fac1, fac2) + ME (fac3) + admin. B: CSE (fac4) + admin."""
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    s = Session(); W = type("W", (), {})(); W.s = s
    ua, ub = University(name="A"), University(name="B"); s.add_all([ua, ub]); s.flush()
    dc, dm, db_ = Department(university_id=ua.id, name="CSE"), Department(university_id=ua.id, name="ME"), Department(university_id=ub.id, name="CSE")
    s.add_all([dc, dm, db_]); s.flush(); W.dc, W.dm, W.db = dc, dm, db_
    def mk(email, uni, dep, role):
        u = User(university_id=uni.id, department_id=dep.id, email=email, full_name=email, role=role, pw_hash=hash_pw("password1")); s.add(u); s.flush(); return u
    W.admin, W.hod, W.f1, W.f2, W.f3 = mk("adm@a", ua, dc, "admin"), mk("hod@a", ua, dc, "hod"), mk("f1@a", ua, dc, "faculty"), mk("f2@a", ua, dc, "faculty"), mk("f3@a", ua, dm, "faculty")
    W.admin_b, W.f4 = mk("adm@b", ub, db_, "admin"), mk("f4@b", ub, db_, "faculty")
    def batch(owner, uni, dep, name, marks, year="2026-27"):
        b = Batch(university_id=uni.id, department_id=dep.id, owner_id=owner.id, name=name, academic_year=year, semester=1); s.add(b); s.flush()
        for i, m in enumerate(marks): s.add(Student(batch_id=b.id, student_id=f"{b.id}-{i}", name=f"n{i}", attendance=80, marks=m, quiz_submitted=True, quiz_marks=10, quiz_total=20))
        s.flush(); return b
    W.b1, W.b2 = batch(W.f1, ua, dc, "f1 batch", [50, 60]), batch(W.f2, ua, dc, "f2 batch", [70, 90])
    W.b3, W.b4 = batch(W.f3, ua, dm, "f3 batch", [40, 40]), batch(W.f4, ub, db_, "f4 batch", [99])
    W.b1_old = batch(W.f1, ua, dc, "f1 batch 2025", [30, 40], "2025-26"); s.commit(); yield W; s.close()
