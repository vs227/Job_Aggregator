from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from auth import create_token, get_current_user, verify_password, hash_password
from models import RegisterUser, LoginUser, JobsInput, SavedJob, AlertPreference, SearchJob, SourceInput, ResumeChatInput
import shutil
import json
import tempfile
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from scrapers.main import refresh_and_import_jobs
from RAG import (
    extract_text, get_embedding, save_resume, get_resume,
    match_jobs, generate_answer, analyze_resume_data,
    extract_ai_profile, save_ai_profile, get_ai_profile,
    extract_skills_local, chunk_resume_text, get_embeddings_batch,
    save_resume_chunks,
)


import time
from collections import defaultdict
from datetime import date

class SlidingWindowRateLimiter:
    def __init__(self, requests_per_minute: int = 10):
        self.rpm = requests_per_minute
        self.requests = defaultdict(list)

    def check_rate_limit(self, identifier: str):
        now = time.time()
        window_start = now - 60
        timestamps = [t for t in self.requests[identifier] if t > window_start]
        if len(timestamps) >= self.rpm:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded (max {self.rpm} queries/min). Please wait a moment!"
            )
        timestamps.append(now)
        self.requests[identifier] = timestamps

minute_limiter = SlidingWindowRateLimiter(requests_per_minute=10)

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        print("[APScheduler] Initializing 3-day background job refresh...")
        scheduler.add_job(
            refresh_and_import_jobs,
            trigger=IntervalTrigger(days=3),
            args=[50],
            id='auto_3day_job_refresh',
            name='3-Day Job Refresh (Adzuna)',
            replace_existing=True,
        )
        scheduler.start()
        print("[APScheduler] Background scheduler active. Jobs will auto-refresh every 3 days.")
    except Exception as e:
        print(f"[APScheduler] Warning starting background scheduler: {e}")

    yield

    try:
        print("[APScheduler] Shutting down background scheduler...")
        scheduler.shutdown()
    except Exception as e:
        print(f"[APScheduler] Warning shutting down scheduler: {e}")

app = FastAPI(lifespan=lifespan)

DAILY_CHAT_LIMIT = 30
_daily_chat_tracker = {}

def get_remaining_daily_chat_limit(user_id: int):
    today = str(date.today())
    key = (user_id, today)
    used = _daily_chat_tracker.get(key, 0)
    return max(0, DAILY_CHAT_LIMIT - used)

def check_and_update_daily_chat_limit(user_id: int):
    today = str(date.today())
    key = (user_id, today)
    used = _daily_chat_tracker.get(key, 0)
    if used >= DAILY_CHAT_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Daily AI chat limit reached ({DAILY_CHAT_LIMIT} queries/day). Please try again tomorrow!"
        )
    _daily_chat_tracker[key] = used + 1
    return DAILY_CHAT_LIMIT - (used + 1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/jobs/refresh")
def manual_jobs_refresh(background_tasks: BackgroundTasks, user_id: str = Depends(get_current_user)):
    background_tasks.add_task(refresh_and_import_jobs, 50)
    return {"message": "Job refresh initiated in background. Outdated jobs will be deleted and 50 fresh ones loaded."}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {
        "message": "Welcome to the Job Aggregator service",
        "status": "online"
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
    res = (supabase.table("users").select("id, email, password_hash").eq("email", user.email).execute())

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

        try:
            # 1. Embed and save full resume
            embedding = get_embedding(text)
            save_resume(user_id, text, embedding)

            # 2. Chunk document (800 chars / 100 overlap) and save vector chunks to pgvector
            chunks = chunk_resume_text(text, chunk_size=800, chunk_overlap=100)
            chunk_embeddings = get_embeddings_batch(chunks)
            save_resume_chunks(user_id, chunks, chunk_embeddings)

            # 3. Find matched jobs using semantic search
            matched = match_jobs(embedding, limit=10)

            # 4. LLM Analysis: extract ALL skills, calculate match score & generate AI recommendations
            analysis = analyze_resume_data(text, matched)

            # 5. Extract and update profile
            profile = extract_ai_profile(text)
            profile["job_fit_score"] = analysis.get("match_score", 80)
            profile["recommendation"] = analysis.get("recommendation", "")
            if analysis.get("extracted_skills"):
                profile["top_skills"] = analysis["extracted_skills"]
            save_ai_profile(user_id, profile)


            return {"message": "Resume uploaded and vector chunks stored successfully", "analysis": analysis, "profile": profile}
        except Exception as e:
            print(f"Error processing upload_resume: {e}")
            skills = extract_skills_local(text)
            analysis = {
                "match_score": 75,
                "extracted_skills": skills,
                "recommendation": "Your resume has been parsed. Consider highlighting core project metrics and key framework competencies.",
            }
            profile = {"top_skills": skills, "experience_level": "fresher", "preferred_roles": [], "education": "", "projects_summary": ""}
            return {"message": "Resume parsed successfully", "analysis": analysis, "profile": profile}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)



def _job_to_dict(job_data, reason="Matches your profile."):
    return {
        "id": job_data["id"], "title": job_data["title"],
        "company": job_data["company"], "location": job_data["location"],
        "salary": job_data["salary"], "description": job_data["description"],
        "job_url": job_data.get("job_url", "#"), "match_reason": reason,
    }


def _fill_job_urls(matched_jobs_dict):
    if not matched_jobs_dict:
        return
    try:
        job_ids = list(matched_jobs_dict.keys())
        db_jobs = supabase.table("jobs").select("id, job_url").in_("id", job_ids).execute().data or []
        url_map = {j["id"]: j.get("job_url") for j in db_jobs}
        for j_id, job in matched_jobs_dict.items():
            job.setdefault("job_url", url_map.get(j_id, "#"))
    except Exception as e:
        print(f"Error fetching job URLs: {e}")


@app.post("/resume/chat")
def chat_with_resume(chat_input: ResumeChatInput, user_id: int = Depends(get_current_user)):
    minute_limiter.check_rate_limit(str(user_id))
    check_and_update_daily_chat_limit(user_id)
    resume = get_resume(user_id)
    ai_profile = get_ai_profile(user_id)

    if not resume:
        return {
            "response": "Please upload your resume using the box on the left first. Once uploaded, I can match jobs to your skills and assist with your career!",
            "matches": [],
            "remaining_daily": get_remaining_daily_chat_limit(user_id),
            "daily_limit": DAILY_CHAT_LIMIT
        }

    user_skills = (ai_profile.get("top_skills") or []) if ai_profile else extract_skills_local(resume["resume_text"])
    skills_str = ", ".join(user_skills)
    roles_str = ", ".join(ai_profile.get("preferred_roles") or []) if ai_profile else ""
    context = f"Candidate Skills: {skills_str}. Roles: {roles_str}. Query: {chat_input.message}"

    matched_jobs = []
    try:
        search_emb = get_embedding(context, task="RETRIEVAL_QUERY")
        matched_jobs = match_jobs(search_emb, limit=8)
    except Exception as e:
        print(f"Notice matching jobs error: {e}")

    ai_result = generate_answer(
        resume=resume["resume_text"], jobs=matched_jobs, query=chat_input.message,
        total_jobs=100, saved_jobs_count=0, user_skills=user_skills,
    )

    matched_jobs_dict = {j["id"]: j for j in matched_jobs}
    _fill_job_urls(matched_jobs_dict)

    structured = []
    for item in ai_result.get("jobs", []):
        if item.get("id") in matched_jobs_dict:
            structured.append(_job_to_dict(matched_jobs_dict[item["id"]], item.get("match_reason", "A suitable match.")))

    if ai_result.get("fallback") and not structured:
        structured = [_job_to_dict(j, "Matches key skills in your profile.") for j in matched_jobs_dict.values()]

    return {
        "response": ai_result.get("text", "Here are the jobs that match your profile:"),
        "matches": structured,
        "remaining_daily": get_remaining_daily_chat_limit(user_id),
        "daily_limit": DAILY_CHAT_LIMIT
    }


@app.get("/resume/analysis")
def get_user_resume_analysis(user_id: int = Depends(get_current_user)):
    resume = get_resume(user_id)
    if not resume:
        return {"has_resume": False, "remaining_daily": get_remaining_daily_chat_limit(user_id), "daily_limit": DAILY_CHAT_LIMIT}

    ai_profile = get_ai_profile(user_id)
    rec = None
    if ai_profile:
        rec = ai_profile.get("recommendation")
        if not rec and ai_profile.get("missing_skills"):
            ms = ai_profile["missing_skills"]
            if isinstance(ms, list) and len(ms) > 0:
                rec = ms[0]
            elif isinstance(ms, str):
                rec = ms

    if not rec or "Consider highlighting core project metrics" in rec or "Your resume has been processed" in rec:
        try:
            matched = match_jobs(get_embedding(resume["resume_text"]), limit=5)
            analysis = analyze_resume_data(resume["resume_text"], matched)
            rec = analysis.get("recommendation")
            if ai_profile and rec:
                ai_profile["recommendation"] = rec
                save_ai_profile(user_id, ai_profile)
        except Exception as e:
            rec = "Highlight cloud infrastructure (AWS/Docker) and system performance metrics in your projects to optimize your profile for target developer roles."

    skills = (ai_profile.get("top_skills") if ai_profile else None) or extract_skills_local(resume["resume_text"])
    score = (ai_profile.get("job_fit_score") if ai_profile else None) or 85

    return {
        "has_resume": True,
        "analysis": {
            "match_score": score,
            "extracted_skills": skills,
            "recommendation": rec
        },
        "profile": ai_profile or {"top_skills": skills, "job_fit_score": score},
        "remaining_daily": get_remaining_daily_chat_limit(user_id),
        "daily_limit": DAILY_CHAT_LIMIT
    }



@app.post("/logout")
def logout_user_session(user_id: int = Depends(get_current_user)):
    try:
        supabase.table("user_resumes").delete().eq("user_id", user_id).execute()
        supabase.table("user_resume_chunks").delete().eq("user_id", user_id).execute()
        supabase.table("user_ai_profiles").delete().eq("user_id", user_id).execute()
        print(f"Logged out user {user_id}: Purged resume text, vector chunks & AI profiles from database.")
    except Exception as e:
        print(f"Notice purging user resume embeddings on logout: {e}")
    return {"message": "Logged out successfully and user resume data erased."}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

