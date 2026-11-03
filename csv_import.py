import pandas as pd, io
ALIASES = {
 "student_id": ["student id","studentid","id","roll number","roll no","roll no.","rollno","enrollment","enrolment no"],
 "name": ["student name","name","full name"],
 "attendance": ["attendance","attendance %","attendance percentage","attendance (%)"],
 "marks": ["overall marks","marks","total marks","overall","total","percentage"],
 "quiz_submitted": ["quiz submitted","quiz submission","submitted quiz"],
 "quiz_marks": ["quiz marks","quiz score"], "quiz_total": ["quiz total marks","quiz total","quiz max"],
 "assignment": ["assignment marks","assignment","assignments"], "exam": ["examination marks","exam marks","exam","examination"],
}
FIELDS = list(ALIASES); REQUIRED = ["student_id", "name"]
def read_csv(file): return pd.read_csv(file, dtype=str, keep_default_na=False).rename(columns=lambda c: c.strip())
def guess_mapping(cols):
    low = {c.lower().strip(): c for c in cols}; m = {}
    for f, al in ALIASES.items():
        m[f] = next((low[a] for a in al if a in low), None)
    return m
def apply_mapping(raw, mapping):
    """Returns (clean_df, problems_df). Invalid rows are reported, never silently dropped."""
    out = pd.DataFrame({f: raw[c] if c else None for f, c in mapping.items()})
    probs = []
    for f in ["attendance","marks","quiz_marks","quiz_total","assignment","exam"]:
        num = pd.to_numeric(out[f].astype(str).str.replace("%","",regex=False).str.strip().replace("", None), errors="coerce")
        bad = num.isna() & out[f].notna() & (out[f].astype(str).str.strip() != "")
        for i in out.index[bad]: probs.append((i+2, f, f"Not a number: '{out.at[i,f]}'"))
        if f in ("attendance","marks"):
            for i in out.index[(num < 0) | (num > 100)]: probs.append((i+2, f, f"Out of range 0-100: {num[i]}"))
        out[f] = num
    qs = out["quiz_submitted"].astype(str).str.strip().str.lower()
    out["quiz_submitted"] = qs.map(lambda v: True if v in ("yes","y","true","1","submitted") else False if v in ("no","n","false","0","not submitted") else None)
    out["student_id"] = out["student_id"].astype(str).str.strip()
    for i in out.index[out["student_id"] == ""]: probs.append((i+2, "student_id", "Missing student ID"))
    dup = out["student_id"].duplicated(keep=False) & (out["student_id"] != "")
    for i in out.index[dup]: probs.append((i+2, "student_id", f"Duplicate ID '{out.at[i,'student_id']}'"))
    p = pd.DataFrame(probs, columns=["csv_row","column","issue"])
    bad_rows = set(p[p.issue.str.startswith(("Missing","Duplicate"))].csv_row) if len(p) else set()
    ok = out[[ (i+2) not in bad_rows for i in out.index ]].drop_duplicates("student_id")
    return ok.reset_index(drop=True), p
