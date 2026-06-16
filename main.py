from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from auth import create_token, get_current_user, verify_password, hash_password
from models import RegisterUser, LoginUser, JobsInput, SavedJob, AlertPreference, SearchJob, SourceInput, ResumeChatInput
import shutil
import json
import tempfile
import os
from RAG import extract_text, get_embedding, save_resume, get_resume, match_jobs, generate_answer, analyze_resume_data

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {
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

@app.get("/profile")
def profile(user_id: int = Depends(get_current_user)):
    user = (supabase.table("users").select("id, username, email, created_at").eq("id", user_id).execute())

    if not user.data:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    return user.data[0]

@app.post("/job_sources")
def create_source(source: SourceInput, user_id: str = Depends(get_current_user)):
    new_source = (supabase.table("job_sources").insert({"source_name": source.source_name, "source_url": source.source_url}).execute())

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

@app.get("/jobs/{job_id}")
def get_job(job_id: int, user_id: int = Depends(get_current_user)):
    job = (supabase.table("jobs").select("*").eq("id", job_id).execute())

    if not job.data:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )
    return job.data[0]

@app.get("/get_jobs")
def get_jobs(page: int = 1, per_page: int = 10, user_id: str = Depends(get_current_user)):
    offset = (page - 1) * per_page
    jobs = supabase.table("jobs").select("*").range(offset, offset + per_page - 1).execute()
    return {"jobs": jobs.data, "page": page, "per_page": per_page}

@app.get("/locations")
def get_locations(user_id: str = Depends(get_current_user)):
    res = supabase.table("jobs").select("location").execute()
    locations = sorted(list(set(item["location"].strip() for item in res.data if item.get("location"))))
    return locations

@app.post("/search_jobs")
def search_jobs(search: SearchJob, page: int = 1, per_page: int = 10, user_id: str = Depends(get_current_user)):
    query = supabase.table("jobs").select("*")

    if search.location:
        query = query.ilike("location", f"%{search.location}%")

    if search.company:
        query = query.ilike("company", f"%{search.company}%")

    if search.job_type:
        query = query.eq("job_type", search.job_type)

    jobs = query.execute()
    results = jobs.data

    if search.keyword:
        keywords = search.keyword.lower().split()
        filtered = []
        for job in results:
            title = (job.get("title") or "").lower()
            company = (job.get("company") or "").lower()
            desc = (job.get("description") or "").lower()
            if all(any(kw in field for field in (title, company, desc)) for kw in keywords):
                filtered.append(job)
        results = filtered

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

    offset = (page - 1) * per_page
    paginated_results = results[offset:offset + per_page]

    return {"jobs": paginated_results, "page": page, "per_page": per_page, "total": len(results)}

@app.post("/save_job")
def save_job(saved_job: SavedJob, user_id: str = Depends(get_current_user)):
    existing = (supabase.table("saved_jobs").select("*").eq("user_id", user_id).eq("job_id", saved_job.job_id).execute())

    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="Job already saved"
        )

    saved = (supabase.table("saved_jobs").insert({"user_id": user_id,"job_id": saved_job.job_id}).execute())

    return {
        "message": "Job saved successfully",
        "saved_job": saved.data[0]
    }

@app.get("/saved_jobs")
def get_saved_jobs(user_id: int = Depends(get_current_user)):
    saved = (supabase.table("saved_jobs").select("*, jobs(*)").eq("user_id", user_id).execute())
    return saved.data

@app.delete("/saved_jobs/{job_id}")
def unsave_job(job_id: int, user_id: int = Depends(get_current_user)):
    deleted = (supabase.table("saved_jobs").delete().eq("user_id", user_id).eq("job_id", job_id).execute())
    return {"message": "Job unsaved successfully"}

@app.get("/job_sources")
def get_sources(user_id: str = Depends(get_current_user)):
    sources = (supabase.table("job_sources").select("*").execute())
    return sources.data

@app.delete("/job_sources/{source_id}")
def delete_source(source_id: int, user_id: int = Depends(get_current_user)):
    deleted = (supabase.table("job_sources").delete().eq("id", source_id).execute())
    return {"message": "Job source deleted successfully"}

@app.post("/alert_preferences")
def create_alert(alert: AlertPreference, background_tasks: BackgroundTasks, user_id: int = Depends(get_current_user)):
    new_alert = (supabase.table("alert_preferences").insert({
            "user_id": user_id,
            "keyword": alert.keyword,
            "location": alert.location,
            "min_salary": alert.min_salary,
            "email_enabled": alert.email_enabled
        }).execute()
    )

    if alert.email_enabled:
        from alerts import send_immediate_alerts
        background_tasks.add_task(
            send_immediate_alerts,
            user_id,
            alert.keyword,
            alert.location,
            alert.min_salary
        )

    return {"message": "Alert preference created successfully", "alert": new_alert.data[0]}

@app.get("/alert_preferences")
def get_alerts(user_id: int = Depends(get_current_user)):
    alerts = (supabase.table("alert_preferences").select("*").eq("user_id", user_id).execute())
    return alerts.data

@app.delete("/alert_preferences/{alert_id}")
def delete_alert(alert_id: int, user_id: int = Depends(get_current_user)):
    deleted = (supabase.table("alert_preferences").delete().eq("user_id", user_id).eq("id", alert_id).execute())
    return {"message": "Alert preference deleted successfully"}

@app.post("/resume/upload")
def upload_resume(file: UploadFile = File(...), user_id: int = Depends(get_current_user)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as temp:
        shutil.copyfileobj(file.file, temp)
        temp_path = temp.name
    try:
        text = extract_text(temp_path)
        embedding = get_embedding(text)
        save_resume(user_id, text, embedding)

        matched = match_jobs(embedding, limit=10)
        analysis = analyze_resume_data(text, matched)

        return {
            "message": "Resume uploaded successfully",
            "analysis": analysis
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/resume/chat")
def chat_with_resume(chat_input: ResumeChatInput, user_id: int = Depends(get_current_user)):
    resume = get_resume(user_id)
    if not resume:
        raise HTTPException(status_code=400, detail="Please upload your resume first")
    query_emb = get_embedding(chat_input.message, task="RETRIEVAL_QUERY")
    resume_emb = resume.get("embedding")
    if resume_emb:
        if isinstance(resume_emb, str):
            try:
                resume_emb = json.loads(resume_emb)
            except Exception:
                resume_emb = [float(x) for x in resume_emb.strip("[]").split(",") if x.strip()]
        search_emb = [(r + q) / 2 for r, q in zip(resume_emb, query_emb)]
    else:
        search_emb = query_emb

    matched_jobs = match_jobs(search_emb, limit=5)
    db_count = 0
    saved_count = 0
    try:
        count_res = supabase.table("jobs").select("id", count="exact").limit(0).execute()
        db_count = count_res.count or 0
        saved_res = supabase.table("saved_jobs").select("id", count="exact").eq("user_id", user_id).limit(0).execute()
        saved_count = saved_res.count or 0
    except Exception:
        pass

    ai_result = generate_answer(
        resume=resume["resume_text"],
        jobs=matched_jobs,
        query=chat_input.message,
        total_jobs=db_count,
        saved_jobs_count=saved_count
    )

    matched_jobs_dict = {j["id"]: j for j in matched_jobs}
    if matched_jobs and any("job_url" not in j for j in matched_jobs):
        try:
            job_ids = [j["id"] for j in matched_jobs]
            db_jobs = supabase.table("jobs").select("id, job_url").in_("id", job_ids).execute().data or []
            db_url_map = {j["id"]: j.get("job_url") for j in db_jobs}
            for j_id, job in matched_jobs_dict.items():
                job["job_url"] = db_url_map.get(j_id, "#")
        except Exception as e:
            print(f"Error fetching job URLs: {e}")
            for job in matched_jobs_dict.values():
                if "job_url" not in job:
                    job["job_url"] = "#"

    structured_jobs = []
    for item in ai_result.get("jobs", []):
        job_id = item.get("id")
        if job_id in matched_jobs_dict:
            job_data = matched_jobs_dict[job_id]
            structured_jobs.append({
                "id": job_data["id"],
                "title": job_data["title"],
                "company": job_data["company"],
                "location": job_data["location"],
                "salary": job_data["salary"],
                "description": job_data["description"],
                "job_url": job_data.get("job_url", "#"),
                "match_reason": item.get("match_reason", "A suitable match for your profile.")
            })
    if ai_result.get("fallback") and not structured_jobs and matched_jobs:
        for job_data in matched_jobs_dict.values():
            structured_jobs.append({
                "id": job_data["id"],
                "title": job_data["title"],
                "company": job_data["company"],
                "location": job_data["location"],
                "salary": job_data["salary"],
                "description": job_data["description"],
                "job_url": job_data.get("job_url", "#"),
                "match_reason": "Matches key skills in your profile."
            })

    return {
        "response": ai_result.get("text", "Here are the jobs that match your profile:"),
        "matches": structured_jobs
    }
