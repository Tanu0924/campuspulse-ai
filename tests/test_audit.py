import pytest
from db import *
def test_admin_actions_are_logged(w):
    set_role(w.s, w.admin, w.f2.id, "hod"); set_active(w.s, w.admin, w.f1.id, False); admin_reset_password(w.s, w.admin, w.f1.id, "temporary99")
    add_department(w.s, w.admin, "Law"); create_user(w.s, w.admin, "z@a", "Z", "temporary99", w.dc.id)
    d = list_audit(w.s, w.admin); assert {"role_changed", "deactivated", "password_reset", "department_added", "user_created"} <= set(d.action)
    assert set(d.by) == {"adm@a"}
def test_audit_is_private_to_admin_and_university(w):
    set_role(w.s, w.admin, w.f2.id, "hod")
    for u in (w.f1, w.hod):
        with pytest.raises(PermissionError): list_audit(w.s, u)
    assert list_audit(w.s, w.admin_b).empty
def test_failed_action_not_logged(w):
    with pytest.raises(PermissionError): set_role(w.s, w.f1, w.f2.id, "hod")
    assert list_audit(w.s, w.admin).empty
