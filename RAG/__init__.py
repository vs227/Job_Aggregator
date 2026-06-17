import os
import json
import traceback
from database import supabase
from pydantic import BaseModel, Field
from typing import List
from pypdf import PdfReader
from docx import Document
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate

if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", max_retries=1)

PROFILE_PROMPT = ChatPromptTemplate.from_template(
    "Extract structured data from this resume.\n\n"
    "Rules:\n"
    "- top_skills: max 8 skills\n"
    "- preferred_roles: max 5 roles\n"
    "- only extract what's mentioned.\n\n"
    "RESUME:\n{resume_text}"
)

ANALYSIS_PROMPT = ChatPromptTemplate.from_template(
    "Analyze this resume against the list of matched jobs.\n\n"
    "Rules:\n"
    "- matched_skills: max 6 items\n"
    "- missing_skills: max 5 items\n\n"
    "RESUME:\n{resume_text}\n\n"
    "JOBS:\n{jobs_json}"
)

CHAT_PROMPT = ChatPromptTemplate.from_template(
    "You are HirePulse Pivot AI, an expert career assistant. Answer the user query using the resume context, chat history, and matched jobs.\n\n"
    "RESUME CONTEXT:\n{resume}\n{missing_text}\n\n"
    "MATCHED JOBS:\n{jobs_json}\n\n"
    "VALID JOB IDs (Only match/return jobs that have these IDs!): {valid_ids}\n"
    "TOTAL AVAILABLE JOBS: {total_jobs} | SAVED JOBS: {saved_jobs_count}\n\n"
    "USER QUERY: {query}\n\n"
    "RULES:\n"
    "1. Resume/CV related questions -> Provide constructive feedback or career advice.\n"
    "2. Job recommendation/matching questions -> Identify matches from the MATCHED JOBS list, provide reasons, and return them. Never invent or hallucinate job IDs outside of the VALID JOB IDs list!\n"
    "3. If query is a general greeting or unrelated to job recommendations/matching, keep 'jobs' empty.\n"
    "4. Mention missing skills in career advice if available."
)


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
    cleaned = " ".join(text.split())
    if task == "RETRIEVAL_QUERY":
        return embeddings.embed_query(cleaned)
    else:
        return embeddings.embed_documents([cleaned])[0]


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


class AIProfile(BaseModel):
    top_skills: List[str] = Field(description="Top skills from the resume, maximum 8 items")
    experience_level: str = Field(description="Experience level: fresher, junior, mid, or senior")
    preferred_roles: List[str] = Field(description="Preferred roles from the resume, maximum 5 items")
    education: str = Field(description="Highest degree or educational qualification details")
    projects_summary: str = Field(description="Brief summary of projects mentioned in the resume")


class ResumeAnalysis(BaseModel):
    match_score: int = Field(description="Match score out of 100 representing how well the resume matches the jobs")
    matched_skills: List[str] = Field(description="Skills present in both resume and jobs, maximum 6 items")
    missing_skills: List[str] = Field(description="Skills mentioned in the jobs but missing from the resume, maximum 5 items")
    recommendation: str = Field(description="Brief advice or career recommendation for the candidate")


class JobMatchReason(BaseModel):
    id: int = Field(description="The job ID from the valid jobs list")
    match_reason: str = Field(description="Reason why this job matches the query/resume")


class ChatResponse(BaseModel):
    text: str = Field(description="Constructive feedback, answer, or advice to the user")
    jobs: List[JobMatchReason] = Field(description="List of matched jobs with reasons. If no relevant jobs match or the user query is not about job recommendations/matching, return an empty list.")


def extract_ai_profile(resume_text):
    try:
        structured_llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=0.1,
            max_retries=1
        ).with_structured_output(AIProfile)
        result = (PROFILE_PROMPT | structured_llm).invoke({"resume_text": resume_text})
        return result.model_dump()
    except Exception as e:
        print(f"Profile extraction failed: {e}")
        skills = extract_skills_local(resume_text)
        return {
            "top_skills": skills[:8],
            "experience_level": "fresher",
            "preferred_roles": [],
            "education": "",
            "projects_summary": "",
        }


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
    jobs_summary = [
        {
            "title": j.get("title"),
            "company": j.get("company"),
            "description": (j.get("description") or "")[:300]
        }
        for j in matched_jobs
    ]
    try:
        structured_llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=0.2,
            max_retries=1
        ).with_structured_output(ResumeAnalysis)
        result = (ANALYSIS_PROMPT | structured_llm).invoke({
            "resume_text": resume_text,
            "jobs_json": json.dumps(jobs_summary, indent=2)
        })
        return result.model_dump()
    except Exception as e:
        print(f"Resume analysis error: {e}")
        traceback.print_exc()
        skills = extract_skills_local(resume_text)
        return {
            "match_score": 0,
            "matched_skills": skills[:6],
            "missing_skills": [],
            "recommendation": "AI service unavailable. Skills extracted locally from your resume.",
        }


def generate_answer(resume, jobs, query, total_jobs=0, saved_jobs_count=0, missing_skills=None):
    valid_ids = [j.get("id") for j in jobs]
    jobs_input = [
        {
            "id": j.get("id"),
            "title": j.get("title"),
            "company": j.get("company"),
            "description": (j.get("description") or "")[:400]
        }
        for j in jobs
    ]
    missing_text = f"\nMISSING SKILLS: {json.dumps(missing_skills)}" if missing_skills else ""
    
    try:
        structured_llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=0.7,
            max_retries=1
        ).with_structured_output(ChatResponse)
        result = (CHAT_PROMPT | structured_llm).invoke({
            "resume": resume,
            "missing_text": missing_text,
            "jobs_json": json.dumps(jobs_input, indent=2),
            "valid_ids": json.dumps(valid_ids),
            "total_jobs": total_jobs,
            "saved_jobs_count": saved_jobs_count,
            "query": query
        })
        return result.model_dump()
    except Exception as e:
        print(f"generate_answer error: {e}")
        traceback.print_exc()
        return _fallback(query, jobs, total_jobs, saved_count=saved_jobs_count)


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
