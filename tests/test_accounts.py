import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, inspect
from db import *

def test_lockout_after_repeated_failures(w):
    for _ in range(MAX_FAILS): assert login(w.s, "f1@a", "bad") is None
    with pytest.raises(AccountLocked): login(w.s, "f1@a", "password1")   # even the right password is refused
def test_lock_expires_and_counter_resets(w):
    for _ in range(MAX_FAILS): login(w.s, "f1@a", "bad")
    w.f1.locked_until = datetime.utcnow() - timedelta(minutes=1); w.s.commit()
    assert login(w.s, "f1@a", "password1") and w.f1.failed_logins == 0
def test_success_resets_failures(w):
    for _ in range(MAX_FAILS - 1): login(w.s, "f1@a", "bad")
    assert login(w.s, "f1@a", "password1"); assert login(w.s, "f1@a", "bad") is None and w.f1.failed_logins == 1
def test_unknown_email_same_result(w): assert login(w.s, "nobody@x", "password1") is None
def test_deactivated_cannot_login_and_reactivates(w):
    set_active(w.s, w.admin, w.f1.id, False); assert login(w.s, "f1@a", "password1") is None
    set_active(w.s, w.admin, w.f1.id, True); w.f1.failed_logins = 0; w.f1.locked_until = None; w.s.commit()
    assert login(w.s, "f1@a", "password1")
def test_deactivation_permissions(w):
    for actor in (w.f1, w.hod): 
        with pytest.raises(PermissionError): set_active(w.s, actor, w.f2.id, False)
    with pytest.raises(PermissionError): set_active(w.s, w.admin, w.f4.id, False)      # other university
    with pytest.raises(PermissionError): set_active(w.s, w.admin, w.admin.id, False)   # not yourself
def test_change_password(w):
    with pytest.raises(ValueError): change_password(w.s, w.f1.id, "wrong", "newpassword1")
    with pytest.raises(ValueError): change_password(w.s, w.f1.id, "password1", "short")
    with pytest.raises(ValueError): change_password(w.s, w.f1.id, "password1", "password1")
    change_password(w.s, w.f1.id, "password1", "newpassword1")
    assert login(w.s, "f1@a", "password1") is None and login(w.s, "f1@a", "newpassword1")
def test_admin_reset_forces_change_and_unlocks(w):
    for _ in range(MAX_FAILS): login(w.s, "f1@a", "bad")
    admin_reset_password(w.s, w.admin, w.f1.id, "temporary99")
    u = login(w.s, "f1@a", "temporary99"); assert u and u.must_change_pw
    change_password(w.s, u.id, "temporary99", "mynewpass1"); assert not w.s.get(User, u.id).must_change_pw
def test_reset_permissions(w):
    with pytest.raises(PermissionError): admin_reset_password(w.s, w.hod, w.f1.id, "temporary99")
    with pytest.raises(PermissionError): admin_reset_password(w.s, w.admin, w.f4.id, "temporary99")
    with pytest.raises(ValueError): admin_reset_password(w.s, w.admin, w.f1.id, "short")
def test_new_accounts_must_change_password(w):
    assert create_user(w.s, w.admin, "n@a", "N", "temporary99", w.dc.id).must_change_pw
def test_migration_adds_columns_to_old_database(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path/'old.db'}")
    with e.begin() as c: c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")); c.execute(text("INSERT INTO users VALUES (1,'a@b')"))
    migrate(e); migrate(e)   # second run must be a no-op
    cols = {c["name"] for c in inspect(e).get_columns("users")}; assert {"active", "must_change_pw", "failed_logins", "locked_until"} <= cols
    with e.connect() as c: assert c.execute(text("SELECT active, failed_logins FROM users")).one() == (1, 0)
