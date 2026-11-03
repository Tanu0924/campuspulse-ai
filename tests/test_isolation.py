import pytest, pandas as pd
from db import *
import csv_import as ci

def names(bs): return {b.name for b in bs}

def test_faculty_sees_only_own_batches(w):
    assert names(visible_batches(w.s, w.f1)) == {"f1 batch", "f1 batch 2025"}
def test_id_tampering_blocked(w):
    assert get_batch(w.s, w.f1, w.b2.id) is None      # same department, other faculty
    assert get_batch(w.s, w.f1, w.b4.id) is None      # other university
def test_hod_scope_is_own_department(w):
    assert names(visible_batches(w.s, w.hod)) == {"f1 batch", "f2 batch", "f1 batch 2025"}
    assert get_batch(w.s, w.hod, w.b3.id) is None     # ME batch hidden from CSE HOD
def test_admin_never_crosses_university(w):
    assert "f4 batch" not in names(visible_batches(w.s, w.admin)); assert get_batch(w.s, w.admin, w.b4.id) is None
    assert "f1 batch" not in names(visible_batches(w.s, w.admin_b))
def test_only_owner_can_edit(w):
    assert can_edit(w.f1, w.b1) and not can_edit(w.hod, w.b1) and not can_edit(w.admin, w.b1)
def test_batch_df_never_leaks(w):
    assert set(batch_df(w.s, w.f1)["faculty"]) == {"f1@a"}
    assert batch_df(w.s, w.f1, [w.b2.id]).empty        # asking for someone else's batch id returns nothing
def test_summary_permissions_and_scope(w):
    with pytest.raises(PermissionError): department_summary(w.s, w.f1)
    assert set(department_summary(w.s, w.hod).department) == {"CSE"}
    assert set(department_summary(w.s, w.admin).department) == {"CSE", "ME"}
    assert department_summary(w.s, w.admin_b).students.sum() == 1
    assert "name" not in department_summary(w.s, w.admin).columns
def test_summary_values_from_real_data(w):
    r = department_summary(w.s, w.admin); me = r[r.department == "ME"].iloc[0]
    assert me.avg_marks == 40 and me.quiz_rate == 100
def test_trend(w):
    t = trend_summary(w.s, w.hod); assert set(t.academic_year) == {"2025-26", "2026-27"}
    with pytest.raises(PermissionError): trend_summary(w.s, w.f1)
def test_role_management(w):
    with pytest.raises(PermissionError): set_role(w.s, w.f1, w.f2.id, "hod")        # faculty can't promote
    with pytest.raises(PermissionError): set_role(w.s, w.hod, w.f2.id, "hod")       # hod can't promote
    with pytest.raises(PermissionError): set_role(w.s, w.admin, w.f4.id, "hod")     # other university
    with pytest.raises(PermissionError): set_role(w.s, w.admin, w.admin.id, "faculty")
    assert set_role(w.s, w.admin, w.f2.id, "hod").role == "hod"
def test_create_user_and_department_rules(w):
    with pytest.raises(PermissionError): create_user(w.s, w.admin, "x@a", "X", "password1", w.db.id)   # other uni's department
    with pytest.raises(PermissionError): add_department(w.s, w.hod, "Law")
    with pytest.raises(ValueError): add_department(w.s, w.admin, "CSE")
    assert create_user(w.s, w.admin, "new@a", "New", "password1", w.dm.id, "hod").role == "hod"
    with pytest.raises(PermissionError): list_users(w.s, w.f1)
    assert {x.email for x in list_users(w.s, w.hod)} <= {"adm@a", "hod@a", "f1@a", "f2@a"}
def test_login_and_hashing(w):
    assert login(w.s, "F1@A", "password1") and not login(w.s, "f1@a", "wrong")
    assert w.f1.pw_hash != "password1"
def test_safe_sql(w):
    df = batch_df(w.s, w.f1)
    assert len(run_safe_sql("select * from students", df)) == 4
    for bad in ["drop table students", "select 1; select 2", "delete from students", "with x as (select 1) update students set marks=1", "pragma table_info(students)"]:
        with pytest.raises(PermissionError): run_safe_sql(bad, df)
    with pytest.raises(Exception): run_safe_sql("select * from users", df)   # no access to auth data
def test_upsert_no_duplicates(w):
    df = pd.DataFrame([dict(student_id="X1", name="A", marks=50.0), dict(student_id="X2", name="B", marks=60.0)])
    save_students(w.s, w.b1, df, "replace"); assert len(w.b1.students) == 2
    a, u = save_students(w.s, w.b1, pd.DataFrame([dict(student_id="X1", name="A", marks=77.0), dict(student_id="X3", name="C", marks=1.0)]), "update")
    assert (a, u) == (1, 1) and len(w.b1.students) == 3 and {x.marks for x in w.b1.students if x.student_id == "X1"} == {77.0}
def test_csv_aliases_and_problems():
    raw = ci.read_csv(__import__("io").StringIO("Roll Number,Student Name,Attendance %,Overall Marks,Quiz Submitted\nR1,A,90%,80,Yes\nR1,B,50,abc,No\n,C,120,70,y\n"))
    m = ci.guess_mapping(raw.columns); assert m["student_id"] == "Roll Number" and m["attendance"] == "Attendance %"
    ok, p = ci.apply_mapping(raw, m)
    assert len(ok) == 0 or ok.student_id.is_unique
    issues = " ".join(p.issue); assert "Duplicate" in issues and "Missing" in issues and "Not a number" in issues and "Out of range" in issues
