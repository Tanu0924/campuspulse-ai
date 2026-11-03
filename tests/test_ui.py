"""Smoke tests: every page renders for every role without an exception (uses Streamlit's AppTest)."""
import os, pytest
from streamlit.testing.v1 import AppTest
APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")
def open_page(user, page):
    at = AppTest.from_file(APP, default_timeout=30); at.session_state["user"] = user; at.run()
    assert not at.exception, at.exception
    at.sidebar.radio[0].set_value(page).run(); assert not at.exception, (page, at.exception); return at
@pytest.mark.parametrize("page", ["Dashboard", "Add Batch", "Batches", "Compare", "Ask AI", "Account"])
def test_faculty_pages(w, page): open_page(w.f1, page)
@pytest.mark.parametrize("page", ["Dashboard", "Batches", "Compare", "Department", "Faculty", "Ask AI", "Account"])
def test_hod_pages(w, page): open_page(w.hod, page)
@pytest.mark.parametrize("page", ["Dashboard", "University", "Manage", "Activity", "Account"])
def test_admin_pages(w, page): open_page(w.admin, page)
def test_login_screen_shows_when_logged_out():
    at = AppTest.from_file(APP, default_timeout=30).run(); assert not at.exception and len(at.tabs) == 2
def test_deactivated_user_is_logged_out(w):
    at = AppTest.from_file(APP, default_timeout=30); at.session_state["user"] = w.f1
    set_active_ = __import__("db").set_active; set_active_(w.s, w.admin, w.f1.id, False); at.run()
    assert "user" not in at.session_state
