import streamlit as st, pandas as pd, plotly.express as px, os
from db import *
import csv_import as ci
st.set_page_config("CampusPulse AI", "📊", layout="wide"); init_db()
THRESH = 75
ss = st.session_state
def sec(k):
    try: return st.secrets[k]
    except Exception: return os.getenv(k)

def auth_screen():
    st.title("📊 CampusPulse AI"); st.caption("Upload your class data. See how every batch is doing.")
    t1, t2 = st.tabs(["Log in", "Register (Faculty)"])
    with t1:
        e = st.text_input("Email", key="le"); p = st.text_input("Password", type="password", key="lp")
        if st.button("Log in", type="primary"):
            try:
                with Session() as s: u = login(s, e, p)
            except AccountLocked as ex: st.error(str(ex)); return
            if u: ss.user = u; st.rerun()
            else: st.error("Wrong email or password, or the account is inactive.")
    with t2:
        c = st.columns(2)
        f = {"name": c[0].text_input("Full name"), "email": c[1].text_input("Faculty email"),
             "pw": c[0].text_input("Password (min 8 chars)", type="password"), "uni": c[1].text_input("University name"),
             "dep": c[0].text_input("Department"), "des": c[1].text_input("Designation"), "fid": c[0].text_input("Faculty ID")}
        if st.button("Create account"):
            if not all(f.values()): st.error("Please fill every field.")
            else:
                try:
                    with Session() as s: register_faculty(s, f["uni"], f["dep"], f["email"], f["name"], f["pw"], f["des"], f["fid"])
                    st.success("Account created. Please log in.")
                except ValueError as ex: st.error(str(ex))

def kpis(df):
    c = st.columns(5)
    c[0].metric("Students", len(df)); c[1].metric("Avg attendance", f"{df.attendance.mean():.1f}%")
    c[2].metric("Avg marks", f"{df.marks.mean():.1f}"); c[3].metric("Quiz submitted", f"{df.quiz_submitted.fillna(False).astype(bool).mean()*100:.0f}%")
    c[4].metric(f"Attendance < {THRESH}%", int((df.attendance < THRESH).sum()))

def support_flags(df):
    r = pd.Series("", index=df.index)
    r += (df.attendance < THRESH).map({True: f"Attendance below {THRESH}%; ", False: ""})
    r += (df.marks < 40).map({True: "Marks below 40; ", False: ""})
    r += (~df.quiz_submitted.fillna(False).astype(bool)).map({True: "Quiz not submitted; ", False: ""})
    out = df.assign(reason=r); return out[out.reason != ""][["student_id","name","attendance","marks","reason"]]

def dashboard(u):
    st.header(f"Welcome, {u.full_name.split()[-1] if u.role!='faculty' else u.full_name.split()[0]} Sir/Madam!")
    st.caption("Manage your classes, upload student records, and explore academic performance.")
    with Session() as s: bs = visible_batches(s, u); df = batch_df(s, u)
    if df.empty:
        st.info("No batches yet. Click **Add Batch** in the sidebar and upload a CSV to get started."); return
    kpis(df); st.subheader("Recent batches")
    st.dataframe(pd.DataFrame([dict(Batch=b.name, Year=b.academic_year, Semester=b.semester, Uploaded=b.created_at.strftime("%d %b %Y")) for b in bs[:5]]), hide_index=True)

def add_batch(u):
    st.header("➕ Add New Batch")
    with Session() as s: deps = list(s.scalars(select(Department).where(Department.id == u.department_id)))
    c = st.columns(2)
    name = c[0].text_input("Batch name", placeholder="CSE 2nd Year - Section A"); prog = c[1].text_input("Course / Programme", "B.Tech")
    c[0].text_input("Department", deps[0].name, disabled=True)
    year = c[1].text_input("Academic year", "2026-27"); sem = c[0].number_input("Semester", 1, 12, 1); sec_ = c[1].text_input("Section")
    subj = c[0].text_input("Subject (optional)")
    st.download_button("⬇ Download sample CSV template", open("sample_template.csv").read(), "campuspulse_template.csv")
    f = st.file_uploader("Upload CSV", type="csv")
    if not f: return
    raw = ci.read_csv(f); st.write("**Preview**"); st.dataframe(raw.head(8), hide_index=True)
    guess = ci.guess_mapping(raw.columns); opts = [None] + list(raw.columns); st.write("**Column matching** (fix any that are wrong)")
    cols = st.columns(3); mapping = {}
    for i, fld in enumerate(ci.FIELDS):
        mapping[fld] = cols[i % 3].selectbox(fld.replace("_"," ").title(), opts, index=opts.index(guess[fld]), key=f"m{fld}")
    if not all(mapping[r] for r in ci.REQUIRED): st.error("Map Student ID and Student Name to continue."); return
    ok, probs = ci.apply_mapping(raw, mapping)
    st.success(f"{len(ok)} of {len(raw)} rows are ready to import.")
    if len(probs): st.warning(f"{len(probs)} issue(s) found. Rows with missing/duplicate IDs are skipped; other bad values are left blank."); st.dataframe(probs, hide_index=True)
    if st.button("Import batch", type="primary", disabled=not name or ok.empty):
        with Session() as s:
            b = Batch(university_id=u.university_id, department_id=u.department_id, owner_id=u.id, name=name, programme=prog,
                      academic_year=year, semester=int(sem), section=sec_, subject=subj); s.add(b); s.flush()
            a, _ = save_students(s, b, ok, "replace")
        st.success(f"Imported {a} students into '{name}'. Open it from **My Batches**.")

def my_batches(u):
    st.header("📚 Batches")
    with Session() as s: bs = visible_batches(s, u)
    if not bs: st.info("Nothing here yet."); return
    pick = st.selectbox("Open a batch", bs, format_func=lambda b: f"{b.name} ({b.academic_year})")
    with Session() as s:
        b = get_batch(s, u, pick.id); df = batch_df(s, u, [b.id])
    if b is None: st.error("Access denied."); return
    kpis(df); t = st.tabs(["Performance", "Attendance", "Quizzes", "Needs support", "Manage"])
    with t[0]:
        st.plotly_chart(px.histogram(df, x="marks", nbins=10, title="Marks distribution"), use_container_width=True)
        st.write("**Top 5**"); st.dataframe(df.nlargest(5, "marks")[["student_id","name","marks"]], hide_index=True)
        st.caption(f"Highest {df.marks.max()} · Lowest {df.marks.min()}")
    with t[1]:
        st.plotly_chart(px.histogram(df, x="attendance", nbins=10, title="Attendance distribution"), use_container_width=True)
        st.write(f"**Below {THRESH}%**"); st.dataframe(df[df.attendance < THRESH][["student_id","name","attendance"]], hide_index=True)
    with t[2]:
        sub = df.quiz_submitted.fillna(False).astype(bool); st.write(f"Submitted: **{sub.sum()}** · Not submitted: **{(~sub).sum()}** · Avg quiz marks: **{df.quiz_marks.mean():.1f}**")
        st.dataframe(df[~sub][["student_id","name"]], hide_index=True)
    with t[3]:
        st.caption(f"Criteria: attendance < {THRESH}%, marks < 40, or quiz not submitted. Please review each case manually.")
        st.dataframe(support_flags(df), hide_index=True)
    with t[4]:
        if not can_edit(u, b): st.info("Read-only: you are not the owner of this batch."); return
        nn = st.text_input("Rename batch", b.name)
        if st.button("Save name"):
            with Session() as s: x = s.get(Batch, b.id); x.name = nn; s.commit()
            st.rerun()
        up = st.file_uploader("Upload updated CSV", type="csv", key="upd")
        if up:
            raw = ci.read_csv(up); ok, probs = ci.apply_mapping(raw, ci.guess_mapping(raw.columns))
            mode = st.radio("What should happen?", ["update", "replace"], format_func=lambda m: "Update existing students & add new ones" if m=="update" else "Replace the whole batch")
            if st.button("Apply CSV"):
                with Session() as s: a, up_ = save_students(s, s.get(Batch, b.id), ok, mode); audit(s, u, 'batch_csv_'+mode, b.name, f'{a} added, {up_} updated'); s.commit()
                st.success(f"{a} added, {up_} updated. {len(probs)} issue(s) reported."); st.dataframe(probs)
        st.divider(); sure = st.checkbox("I understand deleting a batch cannot be undone")
        if st.button("Delete batch", disabled=not sure):
            with Session() as s: audit(s, u, 'batch_deleted', b.name); s.delete(s.get(Batch, b.id)); s.commit()
            st.rerun()

def compare(u):
    st.header("⚖ Compare Batches")
    with Session() as s: bs = visible_batches(s, u)
    sel = st.multiselect("Pick two or more batches", bs, format_func=lambda b: b.name)
    if len(sel) < 2: st.info("Select at least two batches."); return
    with Session() as s: df = batch_df(s, u, [b.id for b in sel])
    g = df.groupby("batch").agg(students=("student_id","count"), avg_marks=("marks","mean"), avg_attendance=("attendance","mean"),
        quiz_rate=("quiz_submitted", lambda x: x.fillna(False).astype(bool).mean()*100), support=("attendance", lambda x: (x < THRESH).sum())).reset_index()
    st.dataframe(g.round(1), hide_index=True)
    for m in ["avg_marks","avg_attendance","quiz_rate"]: st.plotly_chart(px.bar(g, x="batch", y=m, title=m.replace("_"," ").title()), use_container_width=True)

def dept_view(u):
    st.header("🏛 " + ("University Overview" if u.role == "admin" else "Department Overview"))
    with Session() as s: d = department_summary(s, u)
    if d.empty: st.info("No data uploaded yet."); return
    g = d.assign(w=d.students).groupby("department").apply(lambda x: pd.Series({"students": x.students.sum(),
        "avg_marks": (x.avg_marks*x.w).sum()/x.w.sum(), "avg_attendance": (x.avg_attendance*x.w).sum()/x.w.sum(),
        "quiz_rate": (x.quiz_rate*x.w).sum()/x.w.sum()}), include_groups=False).reset_index()
    st.dataframe(g.round(1), hide_index=True)
    for m in ["avg_marks","avg_attendance","quiz_rate","students"]: st.plotly_chart(px.bar(g, x="department", y=m, title=m.replace("_"," ").title()), use_container_width=True)
    st.plotly_chart(px.bar(d, x="semester", y="avg_marks", color="department", barmode="group", title="Semester-wise average marks"), use_container_width=True)
    with Session() as s: tr = trend_summary(s, u)
    if tr.academic_year.nunique() > 1:
        st.plotly_chart(px.line(tr.sort_values("academic_year"), x="academic_year", y="avg_marks", color="department", markers=True, title="Average marks by academic year"), use_container_width=True)
        st.plotly_chart(px.line(tr.sort_values("academic_year"), x="academic_year", y="avg_attendance", color="department", markers=True, title="Average attendance by academic year"), use_container_width=True)
    else: st.info("Improvement over time appears once data from two or more academic years is uploaded.")
    st.caption("Aggregated figures only. No individual student records are shown here.")

def force_change(u):
    st.header("Please set a new password"); st.caption("You are using a temporary password.")
    account_form(u, key="fc"); st.stop()

def account_form(u, key="ac"):
    o = st.text_input("Current password", type="password", key=key+"o"); n = st.text_input("New password (min 8 characters)", type="password", key=key+"n")
    if st.button("Change password", key=key+"b"):
        try:
            with Session() as s: change_password(s, u.id, o, n)
            st.success("Password changed."); ss.pop("user", None); st.rerun() if key == "fc" else None
        except ValueError as ex: st.error(str(ex))

def account(u):
    st.header("🔐 My Account"); st.write(f"**{u.full_name}** · {u.email} · {u.role}"); account_form(u)

def manage(u):
    st.header("👥 " + ("Manage University" if u.role == "admin" else "Department Faculty"))
    with Session() as s: users = list_users(s, u); deps = {d.id: d.name for d in list_departments(s, u)}
    st.dataframe(pd.DataFrame([dict(Name=x.full_name, Email=x.email, Role=x.role, Department=deps.get(x.department_id)) for x in users]), hide_index=True)
    if u.role != "admin": return
    st.subheader("Add department"); dn = st.text_input("Department name")
    if st.button("Add department"):
        try:
            with Session() as s: add_department(s, u, dn)
            st.success("Added."); st.rerun()
        except ValueError as ex: st.error(str(ex))
    st.subheader("Change a role")
    tgt = st.selectbox("Person", [x for x in users if x.role != "admin"], format_func=lambda x: f"{x.full_name} ({x.role})")
    if tgt:
        nr = st.radio("New role", ["faculty", "hod"], index=["faculty","hod"].index(tgt.role), horizontal=True)
        if st.button("Save role"):
            with Session() as s: set_role(s, u, tgt.id, nr)
            st.success("Updated."); st.rerun()
    st.subheader("Reset password or deactivate")
    who = st.selectbox("Person", [x for x in users if x.role != "admin"], format_func=lambda x: f"{x.full_name} ({'active' if x.active else 'inactive'})", key="who")
    if who:
        tp = st.text_input("Temporary password", type="password", key="tp"); c2 = st.columns(2)
        if c2[0].button("Reset password"):
            try:
                with Session() as s: admin_reset_password(s, u, who.id, tp)
                st.success("Reset. They must choose a new password at next login.")
            except (ValueError, PermissionError) as ex: st.error(str(ex))
        if c2[1].button("Reactivate" if not who.active else "Deactivate"):
            with Session() as s: set_active(s, u, who.id, not who.active)
            st.rerun()
    st.subheader("Create an account")
    c = st.columns(2); n = c[0].text_input("Name", key="cn"); e = c[1].text_input("Email", key="ce")
    p = c[0].text_input("Temporary password", type="password", key="cp"); d = c[1].selectbox("Department", list(deps), format_func=deps.get, key="cd")
    r = st.radio("Role", ["faculty", "hod"], horizontal=True, key="cr")
    if st.button("Create account"):
        try:
            with Session() as s: create_user(s, u, e, n, p, d, r)
            st.success("Account created. Ask them to change the password after first login.")
        except (ValueError, PermissionError) as ex: st.error(str(ex))

def activity(u):
    st.header("📝 Activity Log"); st.caption("Who changed what in your university.")
    with Session() as s: d = list_audit(s, u)
    st.dataframe(d, hide_index=True) if len(d) else st.info("No activity recorded yet.")

def ask_ai(u):
    st.header("💬 Ask a Question")
    with Session() as s: df = batch_df(s, u)
    if df.empty: st.info("Upload a batch first."); return
    q = st.text_input("e.g. Who has attendance below 75%?")
    key = sec("ANTHROPIC_API_KEY")
    if q and st.button("Ask") :
        if not key: st.error("AI is not configured. Add ANTHROPIC_API_KEY to secrets."); return
        import anthropic
        schema = f"Table students({', '.join(df.columns)}). attendance & marks are 0-100; quiz_submitted is 0/1. Scope: {u.role}."
        r = anthropic.Anthropic(api_key=key).messages.create(model=sec("ANTHROPIC_MODEL") or "claude-sonnet-5-5", max_tokens=400,
            system="Return ONLY one SQLite SELECT query, no prose, no markdown. " + schema, messages=[{"role":"user","content":q}])
        sql = r.content[0].text.strip().strip("`").removeprefix("sql").strip()
        try:
            res = run_safe_sql(sql, df)
            with Session() as s: s.add(QueryHistory(user_id=u.id, question=q, sql=sql)); s.commit()
            st.dataframe(res, hide_index=True); st.code(sql, "sql")
        except Exception as ex: st.error(f"Could not run that safely: {ex}")

if "user" in ss:  # re-read from DB each run so role changes and deactivation apply immediately
    with Session() as s: fresh = s.get(User, ss.user.id)
    if fresh is None or not fresh.active: ss.clear(); st.warning("Your session has ended."); auth_screen(); st.stop()
    ss.user = fresh
if "user" not in ss: auth_screen(); st.stop()
u = ss.user
if u.must_change_pw: force_change(u)
pages = {"Dashboard": dashboard, "Add Batch": add_batch, "Batches": my_batches, "Compare": compare, "Ask AI": ask_ai, "Account": account}
if u.role in ("hod", "admin"):
    pages["Department" if u.role == "hod" else "University"] = dept_view
    pages["Faculty" if u.role == "hod" else "Manage"] = manage
    if u.role == "admin": pages["Activity"] = activity
st.sidebar.write(f"**{u.full_name}**  \n{u.role.upper()}")
page = st.sidebar.radio("Menu", list(pages))
if st.sidebar.button("Log out"): ss.clear(); st.rerun()
if u.role == "admin" and page in ("Add Batch",): st.info("Admins view aggregated data; they do not own batches.")
pages[page](u)
