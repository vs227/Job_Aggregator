from fastapi import FastAPI, Depends, HTTPException
from database import supabase
from auth import create_token, get_current_user, verify_password, hash_password
from models import RegisterUser, LoginUser, JobsInput, SavedJob, AlertPreference, SearchJob, SourceInput

app = FastAPI() 

@app.get("/")
def home():
    return{
        "message": "Welcome to the Job Aggregator service"
    }

@app.post("/register")
def register(user: RegisterUser):
    existing_user = (supabase.table("users").select("*").eq("email", user.email).execute())
    if existing_user.data:
        raise HTTPException(
            status_code=400,
            detail="Email already exists"
        )

    hashed = hash_password(user.password)
    new_user = (supabase.table("users").insert({
            "username": user.username,
            "email": user.email,
            "password_hash": hashed
        }).execute()
    )

    return {
        "message": "User registered successfully",
        "user": new_user.data[0]
    }

@app.post("/login")
def login(user: LoginUser):
    res = (supabase.table("users").select("*").eq("email", user.email).execute())

    if not res.data:
        raise HTTPException(
            status_code=401,
            detail="Invalid Email or Password"
        )
    db_user = res.data[0]

    if not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid Email or Password"
        )

    token = create_token({"user_id": db_user["id"], "email": db_user["email"]})

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer"
    }

@app.post("/job_sources")
def create_source(source: SourceInput, user_id: str = Depends(get_current_user)):
    new_source = (supabase.table("job_sources").insert({"source_name": source.source_name, "source_url": source.source_url}).execute()
    )

    return {
        "message": "Source created successfully",
        "source": new_source.data[0]
    }


@app.post("/jobs")
def create_job(job: JobsInput, user_id: str = Depends(get_current_user)):
    new_job = (supabase.table("jobs").insert({"title": job.title, "company": job.company, "location": job.location, "salary": job.salary, "job_type": job.job_type, "description": job.description, "job_url": job.job_url, "source_id": job.source_id}).execute())

    return {
        "message": "Job created successfully",
        "job": new_job.data[0]
    }

@app.get("/get_jobs")
def get_jobs(user_id: str = Depends(get_current_user)):
    jobs = supabase.table("jobs").select("*").execute()
    return jobs.data


@app.post("/search_jobs")
def search_jobs(search: SearchJob, user_id: str = Depends(get_current_user)):
    query = supabase.table("jobs").select("*")
    
    if search.keyword:
        query = query.ilike("title", f"%{search.keyword}%")
    
    if search.location:
        query = query.ilike("location", f"%{search.location}%")
    
    if search.company:
        query = query.ilike("company", f"%{search.company}%")
    
    if search.job_type:
        query = query.eq("job_type", search.job_type)
    
    jobs = query.execute()
    results = jobs.data
    
    if search.min_salary:
        filtered_results = []
        for job in results:
            job_salary = job.get("salary")
            if job_salary is not None:
                try:
                    salary_int = int(job_salary)
                    if salary_int >= search.min_salary:
                        filtered_results.append(job)
                except (ValueError, TypeError):
                    pass
        results = filtered_results
    
    return results