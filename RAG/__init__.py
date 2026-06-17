import os
import json
import traceback
from pypdf import PdfReader
from docx import Document
from database import supabase
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def _clean_json(text):
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def _gemini(prompt, temp=0.3, max_tokens=1024):
    model = genai.GenerativeModel("gemini-2.0-flash-lite")
    res = model.generate_content(prompt, generation_config={
        "response_mime_type": "application/json",
        "temperature": temp,
        "max_output_tokens": max_tokens,
    }, request_options={"timeout": 25.0})
    return _clean_json(res.text)


def extract_text(file_path):
    ext = os.path.splitext(file_path.lower())[1]
    if ext == ".pdf":
        return "\n".join(p.extract_text() for p in PdfReader(file_path).pages if p.extract_text()).strip()
    if ext == ".docx":
        return "\n".join(p.text for p in Document(file_path).paragraphs if p.text).strip()
    raise ValueError("Only .pdf and .docx files are supported")


KNOWN_SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "ruby", "php", "swift", "kotlin",
    "html", "css", "react", "angular", "vue", "next.js", "node.js", "express", "django", "flask", "fastapi",
    "spring", "laravel", "rails", "bootstrap", "tailwind",
    "sql", "mysql", "postgresql", "mongodb", "redis", "firebase", "supabase", "dynamodb", "sqlite",
    "docker", "kubernetes", "aws", "azure", "gcp", "linux", "nginx", "terraform", "ansible",
    "git", "github", "gitlab", "ci/cd", "jenkins", "github actions",
    "machine learning", "deep learning", "tensorflow", "pytorch", "scikit-learn", "opencv", "nlp",
    "pandas", "numpy", "matplotlib", "jupyter",
    "rest api", "graphql", "websocket", "microservices",
    "figma", "photoshop", "illustrator",
    "agile", "scrum", "jira",
    "power bi", "tableau", "excel",
]


def extract_skills_local(text):
    text_lower = text.lower()
    found = [s for s in KNOWN_SKILLS if s in text_lower]
    return [s.title() if len(s) > 3 else s.upper() for s in found]


def get_embedding(text, task="RETRIEVAL_DOCUMENT"):
    return genai.embed_content(
        model="models/gemini-embedding-001",
        content=" ".join(text.split()),
        task_type=task,
    )["embedding"]


def save_resume(user_id, text, embedding):
    supabase.table("user_resumes").upsert(
        {"user_id": user_id, "resume_text": text, "embedding": embedding},
        on_conflict="user_id",
    ).execute()


def get_resume(user_id):
    res = supabase.table("user_resumes").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


def match_jobs(query_embedding, threshold=0.25, limit=5):
    res = supabase.rpc("match_jobs", {
        "query_embedding": query_embedding,
        "match_threshold": threshold,
        "match_count": limit,
    }).execute()
    return res.data or []


def extract_ai_profile(resume_text):
    prompt = f"""Extract structured data from this resume. Respond with JSON only:
{{
  "top_skills": ["skill1", "skill2"],
  "experience_level": "fresher|junior|mid|senior",
  "preferred_roles": ["role1", "role2"],
  "education": "highest degree",
  "projects_summary": "brief summary"
}}
Rules: top_skills max 8, preferred_roles max 5, only extract what's mentioned.

RESUME:
{resume_text}"""
    try:
        return _gemini(prompt, temp=0.1)
    except Exception as e:
        print(f"Profile extraction failed: {e}")
        skills = extract_skills_local(resume_text)
        return {"top_skills": skills[:8], "experience_level": "fresher", "preferred_roles": [], "education": "", "projects_summary": ""}


def save_ai_profile(user_id, profile):
    supabase.table("user_ai_profiles").upsert({
        "user_id": user_id,
        "top_skills": profile.get("top_skills", []),
        "experience_level": profile.get("experience_level", "fresher"),
        "preferred_roles": profile.get("preferred_roles", []),
        "education": profile.get("education", ""),
        "projects_summary": profile.get("projects_summary", ""),
        "job_fit_score": profile.get("job_fit_score", 0),
        "missing_skills": profile.get("missing_skills", []),
    }, on_conflict="user_id").execute()


def get_ai_profile(user_id):
    res = supabase.table("user_ai_profiles").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


def analyze_resume_data(resume_text, matched_jobs):
    jobs_summary = [{"title": j.get("title"), "company": j.get("company"), "description": (j.get("description") or "")[:300]} for j in matched_jobs]

    prompt = f"""Analyze this resume against the jobs. Respond with JSON only:
{{
  "match_score": 85,
  "matched_skills": ["Python", "SQL"],
  "missing_skills": ["Docker", "AWS"],
  "recommendation": "brief advice"
}}
matched_skills max 6, missing_skills max 5.

RESUME:
{resume_text}

JOBS:
{json.dumps(jobs_summary, indent=2)}"""
    try:
        return _gemini(prompt, temp=0.2)
    except Exception as e:
        print(f"Resume analysis error: {e}")
        traceback.print_exc()
        skills = extract_skills_local(resume_text)
        return {"match_score": 0, "matched_skills": skills[:6], "missing_skills": [], "recommendation": "AI service unavailable. Skills extracted locally from your resume."}


def generate_answer(resume, jobs, query, total_jobs=0, saved_jobs_count=0, missing_skills=None):
    valid_ids = [j.get("id") for j in jobs]
    jobs_input = [{"id": j.get("id"), "title": j.get("title"), "company": j.get("company"), "description": (j.get("description") or "")[:400]} for j in jobs]

    missing_text = f"\nMISSING SKILLS: {json.dumps(missing_skills)}" if missing_skills else ""

    prompt = f"""You are HirePulse Pivot AI. Respond ONLY with JSON:
{{
  "text": "your response",
  "jobs": [{{ "id": job_id, "match_reason": "why it matches" }}]
}}

RESUME:
{resume}
{missing_text}

MATCHED JOBS:
{json.dumps(jobs_input, indent=2)}

VALID IDs: {json.dumps(valid_ids)}
TOTAL JOBS: {total_jobs} | SAVED: {saved_jobs_count}

USER: {query}

RULES:
1. Only valid JSON
2. Resume questions → constructive feedback
3. Job questions → return matches with reasons
4. ONLY use IDs from VALID IDs. Never invent IDs.
5. No relevant jobs → return "jobs": []
6. Mention missing skills in career advice if available"""

    try:
        return _gemini(prompt, temp=0.7)
    except Exception:
        traceback.print_exc()
        return _fallback(query, jobs, total_jobs, saved_jobs_count)


def _fallback(query, jobs, total_jobs, saved_count):
    q = query.lower()
    if any(w in q for w in ["hi", "hello", "hey", "hii", "yo"]):
        return {"text": "Hello! I'm HirePulse Pivot AI. How can I help with your job search?", "jobs": []}
    if any(w in q for w in ["resume", "cv", "profile"]):
        return {"text": "I've reviewed your resume — strong skills! Try 'Suggest me jobs' for matches!", "jobs": []}
    if any(w in q for w in ["saved jobs", "bookmarked"]):
        return {"text": f"You have {saved_count} saved jobs!", "jobs": []}
    if any(w in q for w in ["how many", "total jobs"]):
        return {"text": f"We have {total_jobs} jobs listed. What role are you looking for?", "jobs": []}
    if any(w in q for w in ["suggest", "find", "show", "match", "recommend", "jobs"]):
        return {"text": "Here are jobs matching your profile:", "jobs": [{"id": j.get("id"), "match_reason": "Matches your skills."} for j in jobs], "fallback": True}
    return {"text": "Ask me for job suggestions or resume feedback!", "jobs": []}
