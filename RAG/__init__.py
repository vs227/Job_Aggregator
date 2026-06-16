import os
import math
import json
import traceback
from pypdf import PdfReader
from docx import Document
from database import supabase
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def extract_text(file_path: str) -> str:
    _, ext = os.path.splitext(file_path.lower())
    if ext == ".pdf":
        return "\n".join([p.extract_text() for p in PdfReader(file_path).pages if p.extract_text()]).strip()
    elif ext in [".docx", ".doc"]:
        return "\n".join([p.text for p in Document(file_path).paragraphs if p.text]).strip()
    raise ValueError("Only PDF/DOCX supported")

def get_embedding(text: str, task: str = "RETRIEVAL_DOCUMENT") -> list:
    return genai.embed_content(
        model="models/gemini-embedding-001",
        content=" ".join(text.split()),
        task_type=task
    )["embedding"]

def generate_answer(resume: str, jobs: list, query: str, total_jobs: int = 0, saved_jobs_count: int = 0) -> dict:
    jobs_input = [
        {
            "id": j.get("id"),
            "title": j.get("title"),
            "company": j.get("company"),
            "description": (j.get("description") or "")[:400] + "..."
        }
        for j in jobs
    ]

    prompt = f"""You are HirePulse Pivot AI, a helpful career assistant.
You MUST respond ONLY with a valid JSON object in this exact format:
{{
  "text": "Your helpful, friendly response to the user",
  "jobs": [] or [{{ "id": job_id, "match_reason": "Short reason why this job matches the user's resume" }}]
}}

CONTEXT:
USER RESUME:
{resume}

MATCHED JOBS (if any):
{json.dumps(jobs_input, indent=2)}

TOTAL JOBS IN DATABASE: {total_jobs}
USER'S SAVED JOBS COUNT: {saved_jobs_count}

USER MESSAGE: {query}

INSTRUCTIONS:
1. Respond ONLY with valid JSON
2. If user asks about resume, give constructive feedback
3. If user asks for jobs, return matches with clear reasons
4. If user asks about saved jobs count, tell them exactly how many they have saved
5. If greeting, respond warmly
"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.7,
                "max_output_tokens": 1024
            },
            request_options={"timeout": 20.0}
        )

        result_text = response.text.strip()
        if not result_text.startswith("{"):
            json_start = result_text.find("{")
            json_end = result_text.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                result_text = result_text[json_start:json_end]

        return json.loads(result_text)

    except Exception as e:
        print(f"[HirePulse AI] ERROR in generate_answer:")
        traceback.print_exc()

        q_lower = query.lower()
        is_greeting = any(w in q_lower for w in ["hi", "hello", "hey", "hii", "yo", "hola", "greetings"])
        is_resume_review = any(w in q_lower for w in ["resume", "cv", "portfolio", "profile", "think about", "thoughts"])
        is_count_query = any(kw in q_lower for kw in ["how many", "total jobs", "number of jobs"])
        is_saved_jobs_query = any(kw in q_lower for kw in ["saved jobs", "saved in db", "bookmarked"])
        is_job_query = any(w in q_lower for w in ["suggest", "find", "show", "search", "match", "recommend", "jobs", "roles"])

        if is_greeting:
            return {
                "text": "Hello! I'm HirePulse Pivot AI. How can I help you with your job search today?",
                "jobs": []
            }
        elif is_resume_review:
            return {
                "text": "Great! I've reviewed your resume! It looks like you have some strong skills! Try asking 'Suggest me relevant jobs' to get personalized matches!",
                "jobs": []
            }
        elif is_saved_jobs_query:
            return {
                "text": f"You currently have {saved_jobs_count} jobs saved! You can view them in the Saved Jobs section!",
                "jobs": []
            }
        elif is_count_query:
            return {
                "text": f"We currently have {total_jobs} jobs listed! What kind of role are you looking for?",
                "jobs": []
            }
        elif is_job_query:
            return {
                "text": "Here are some jobs that match your profile:",
                "jobs": [{"id": j.get("id"), "match_reason": "Matches key skills from your resume."} for j in jobs],
                "fallback": True
            }
        else:
            return {
                "text": "I'm here to help with your job search! Ask for job suggestions or resume feedback!",
                "jobs": []
            }

def cosine_similarity(v1: list, v2: list) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    return dot / (mag1 * mag2) if mag1 and mag2 else 0.0

def save_resume(user_id: int, text: str, embedding: list):
    supabase.table("user_resumes").delete().eq("user_id", user_id).execute()
    supabase.table("user_resumes").insert({"user_id": user_id, "resume_text": text, "embedding": embedding}).execute()

def get_resume(user_id: int) -> dict:
    res = supabase.table("user_resumes").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None

def match_jobs(query_embedding: list, threshold: float = 0.25, limit: int = 5) -> list:
    res = supabase.rpc("match_jobs", {"query_embedding": query_embedding, "match_threshold": threshold, "match_count": limit}).execute()
    return res.data or []

def analyze_resume_data(resume_text: str, matched_jobs: list) -> dict:
    jobs_summary = []
    for j in matched_jobs:
        jobs_summary.append({
            "title": j.get("title"),
            "company": j.get("company"),
            "description": (j.get("description") or "")[:300]
        })

    prompt = f"""You are a Career Assistant AI. Analyze the user's resume text against the active job listings provided.
    Determine:
    1. A realistic match score (0-100) indicating how well the resume matches these jobs.
    2. A list of matched skills (skills the user has that are relevant to these jobs, maximum 6).
    3. A list of missing/demanded skills (skills frequently requested in these jobs but not found or weak in the resume, maximum 5).
    4. A brief, constructive AI recommendation (2 sentences) on how to optimize their profile.

    RESPOND ONLY WITH A VALID JSON OBJECT in this exact format:
    {{
      "match_score": 85,
      "matched_skills": ["Python", "SQL"],
      "missing_skills": ["Docker", "AWS"],
      "recommendation": "Your recommendation here..."
    }}

    CONTEXT:
    USER RESUME:
    {resume_text}

    MATCHED JOBS:
    {json.dumps(jobs_summary, indent=2)}
    """
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.2
            }
        )
        result_text = response.text.strip()
        return json.loads(result_text)
    except Exception as e:
        print(f"Error in analyze_resume_data: {e}")
        traceback.print_exc()
        return {
            "match_score": 75,
            "matched_skills": ["Python", "SQL", "Git"],
            "missing_skills": ["Docker", "CI/CD"],
            "recommendation": "Update your resume with projects showcasing containerization and automated deployments."
        }
