"""Creates fictional demo data: 1 university, 2 departments, admin + HOD + 2 faculty. Password for all: Demo@12345"""
import random; from db import *
init_db(); random.seed(1)
with Session() as s:
    if s.scalar(select(University)): print("Already seeded"); raise SystemExit
    uni = University(name="Demo University"); s.add(uni); s.flush()
    deps = {n: Department(university_id=uni.id, name=n) for n in ["Computer Science Engineering","Mechanical Engineering"]}
    s.add_all(deps.values()); s.flush()
    mk = lambda e,n,d,r: User(university_id=uni.id, department_id=deps[d].id if d else None, email=e, full_name=n, role=r, designation="Professor", pw_hash=hash_pw("Demo@12345"))
    users = [mk("admin@demo.edu","Registrar","Computer Science Engineering","admin"), mk("hod.cse@demo.edu","Dr. Iyer","Computer Science Engineering","hod"),
             mk("rakesh@demo.edu","Rakesh Sharma","Computer Science Engineering","faculty"), mk("meena@demo.edu","Meena Pillai","Mechanical Engineering","faculty")]
    s.add_all(users); s.flush()
    for u, dep, name, sem in [(users[2],"Computer Science Engineering","CSE 1st Year - A",1),(users[2],"Computer Science Engineering","CSE 2nd Year - B",3),(users[3],"Mechanical Engineering","ME 2nd Year - A",3)]:
        b = Batch(university_id=uni.id, department_id=deps[dep].id, owner_id=u.id, name=name, academic_year="2026-27", semester=sem, section=name[-1]); s.add(b); s.flush()
        for i in range(30):
            qs = random.random() > .2; s.add(Student(batch_id=b.id, student_id=f"{b.id}{i:03d}", name=f"Student {b.id}-{i}", attendance=round(random.uniform(55,98),1),
                marks=round(random.uniform(35,95),1), quiz_submitted=qs, quiz_marks=round(random.uniform(8,20),1) if qs else None, quiz_total=20))
    s.commit(); print("Seeded. Logins: admin@demo.edu, hod.cse@demo.edu, rakesh@demo.edu, meena@demo.edu / Demo@12345")
