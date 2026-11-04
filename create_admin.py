import getpass, sys
from db import *
init_db()
uni = input("University name: ").strip(); dep = input("Department name: ").strip()
name = input("Admin full name: ").strip(); email = input("Admin email: ").strip().lower()
pw = getpass.getpass("Password (min 8 chars): ")
if len(pw) < 8: sys.exit("Password too short")
with Session() as s:
    if s.scalar(select(User).where(User.email == email)): sys.exit("Email already exists")
    uni_row = s.scalar(select(University).where(University.name == uni)) or University(name=uni); s.add(uni_row); s.flush()
    dep_row = s.scalar(select(Department).where(Department.university_id == uni_row.id, Department.name == dep)) or Department(university_id=uni_row.id, name=dep)
    s.add(dep_row); s.flush()
    s.add(User(university_id=uni_row.id, department_id=dep_row.id, email=email, full_name=name, role="admin", designation="Administrator", pw_hash=hash_pw(pw)))
    s.commit(); print("Admin created.")