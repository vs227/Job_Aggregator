import os
import json
import traceback
from database import supabase
from pydantic import BaseModel, Field
from typing import List
from pypdf import PdfReader
from docx import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate

if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", max_retries=2)

PROFILE_PROMPT = ChatPromptTemplate.from_template(
    "Extract structured candidate data from this resume.\n\n"
    "Rules:\n"
    "- top_skills: extract all technical, programming, tools, and professional skills mentioned.\n"
    "- preferred_roles: max 5 suitable roles based on experience\n"
    "- experience_level: fresher, junior, mid, or senior\n"
    "- education: highest degree or details\n"
    "- projects_summary: brief summary of candidate projects\n\n"
    "RESUME:\n{resume_text}"
)

ANALYSIS_PROMPT = ChatPromptTemplate.from_template(
    "You are a senior technical recruiter and career strategist.\n"
    "Analyze the full resume against the current available job market requirements.\n\n"
    "RESUME:\n{resume_text}\n\n"
    "AVAILABLE JOB MARKET SNAPSHOT:\n{jobs_json}\n\n"
    "RULES:\n"
    "1. extracted_skills: Extract ALL technical skills, programming languages, frameworks, databases, tools, and platforms found anywhere in the resume.\n"
    "2. match_score: Calculate an accurate alignment score (0-100) based on how well the resume matches job market demand.\n"
    "3. recommendation: Provide 2-3 specific, actionable, highly practical AI career recommendations to optimize this candidate's resume for top job postings (e.g. key missing frameworks, project enhancements, framing strategy)."
)

CHAT_PROMPT = ChatPromptTemplate.from_template(
    "You are HirePulse Pivot AI, an expert career recruiter and matchmaker.\n"
    "Your goal is to answer the candidate's query thoughtfully and provide job suggestions ONLY when explicitly requested.\n\n"
    "CANDIDATE RESUME CONTEXT:\n{resume}\n\n"
    "CANDIDATE TOP SKILLS:\n{user_skills}\n\n"
    "MATCHED JOBS CANDIDATES:\n{jobs_json}\n\n"
    "VALID JOB IDs: {valid_ids}\n"
    "TOTAL DB JOBS: {total_jobs} | SAVED JOBS: {saved_jobs_count}\n\n"
    "USER QUERY: {query}\n\n"
    "STRICT FACTUAL & INTENT RULES:\n"
    "1. ABSOLUTE TRUTH RULE: Rely ONLY on the exact skills, programming languages, tools, and experience listed in CANDIDATE TOP SKILLS and CANDIDATE RESUME CONTEXT. NEVER invent, hallucinate, assume, or list any programming language (such as C++, C#, Ruby, etc.) or skill that is NOT explicitly present in CANDIDATE TOP SKILLS or RESUME CONTEXT!\n"
    "2. ONLY attach/return jobs in the 'jobs' list if the user explicitly asks for job suggestions, recommendations, or matches (e.g. 'suggest me jobs', 'show matching jobs', 'recommend roles', 'find jobs', 'jobs for me').\n"
    "3. If the user query is a greeting ('hi', 'hello'), a resume question, career advice, or technical question, KEEP THE 'jobs' LIST COMPLETELY EMPTY ([])! Focus strictly on answering in 'text'.\n"
    "4. When the user DOES explicitly ask to suggest jobs, evaluate each candidate job against their top skills and return ONLY suitable jobs with custom match reasons.\n"
    "5. NO MATCHING JOBS RULE: If there are no suitable jobs matching the user's profile in the candidate jobs list or if 'jobs' is empty, state clearly in 'text': 'Currently, there are no suitable job postings matching your profile in our database. Please set an email alert for your preferred roles in the **Job Alerts** section so you get notified instantly when new matching positions are added!'"
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


def chunk_resume_text(text, chunk_size=800, chunk_overlap=100):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    docs = splitter.create_documents([text])
    return [doc.page_content for doc in docs]


def get_embedding(text, task="RETRIEVAL_DOCUMENT"):
    cleaned = " ".join(text.split())
    if task == "RETRIEVAL_QUERY":
        return embeddings.embed_query(cleaned)
    else:
        return embeddings.embed_documents([cleaned])[0]


def get_embeddings_batch(texts):
    cleaned_texts = [" ".join(t.split()) for t in texts if t.strip()]
    if not cleaned_texts:
        return []
    return embeddings.embed_documents(cleaned_texts)


def save_resume(user_id, text, embedding):
    supabase.table("user_resumes").upsert(
        {"user_id": user_id, "resume_text": text, "embedding": embedding},
        on_conflict="user_id",
    ).execute()


def save_resume_chunks(user_id, chunks, embeddings_list):
    try:
        supabase.table("user_resume_chunks").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"Notice clearing previous resume chunks: {e}")

    rows = []
    for idx, (content, emb) in enumerate(zip(chunks, embeddings_list)):
        rows.append({
            "user_id": user_id,
            "chunk_index": idx,
            "content": content,
            "token_count": len(content.split()),
            "embedding": emb
        })
    if rows:
        try:
            supabase.table("user_resume_chunks").insert(rows).execute()
            print(f"Successfully saved {len(rows)} vector chunks for user {user_id} to Supabase pgvector.")
        except Exception as e:
            print(f"Notice saving vector chunks: {e}")


def get_resume(user_id):
    res = supabase.table("user_resumes").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


def match_jobs(query_embedding, threshold=0.20, limit=8):
    res = supabase.rpc("match_jobs", {
        "query_embedding": query_embedding,
        "match_threshold": threshold,
        "match_count": limit,
    }).execute()
    return res.data or []


class AIProfile(BaseModel):
    top_skills: List[str] = Field(description="All skills extracted from the resume")
    experience_level: str = Field(description="Experience level: fresher, junior, mid, or senior")
    preferred_roles: List[str] = Field(description="Preferred roles from the resume, maximum 5 items")
    education: str = Field(description="Highest degree or educational qualification details")
    projects_summary: str = Field(description="Brief summary of projects mentioned in the resume")


class ResumeAnalysis(BaseModel):
    match_score: int = Field(description="Match score out of 100 representing job alignment")
    extracted_skills: List[str] = Field(description="Complete list of skills extracted from the resume")
    recommendation: str = Field(description="Specific, high-quality AI optimization recommendations to improve resume for target jobs")


class JobMatchReason(BaseModel):
    id: int = Field(description="The job ID from the valid jobs list")
    match_reason: str = Field(description="Specific reason explaining why this job strictly matches the user's skills")


class ChatResponse(BaseModel):
    text: str = Field(description="Constructive feedback, answer, or advice to the user")
    jobs: List[JobMatchReason] = Field(description="List of strictly suitable matched jobs with custom reasons. Return [] if user did NOT explicitly ask for job recommendations.")


def extract_ai_profile(resume_text):
    try:
        structured_llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.1,
            max_retries=1
        ).with_structured_output(AIProfile)
        result = (PROFILE_PROMPT | structured_llm).invoke({"resume_text": resume_text})
        return result.model_dump()
    except Exception as e:
        print(f"Profile extraction fallback: {e}")
        skills = extract_skills_local(resume_text)
        return {
            "top_skills": skills,
            "experience_level": "fresher",
            "preferred_roles": [],
            "education": "",
            "projects_summary": "",
        }


def save_ai_profile(user_id, profile):
    rec = profile.get("recommendation", "")
    data = {
        "user_id": user_id,
        "top_skills": profile.get("top_skills", []),
        "experience_level": profile.get("experience_level", "fresher"),
        "preferred_roles": profile.get("preferred_roles", []),
        "education": profile.get("education", ""),
        "projects_summary": profile.get("projects_summary", ""),
        "job_fit_score": profile.get("job_fit_score", 0),
        "missing_skills": [rec] if rec else profile.get("missing_skills", []),
    }
    try:
        supabase.table("user_ai_profiles").upsert(data, on_conflict="user_id").execute()
    except Exception as e:
        print(f"Notice saving AI profile: {e}")



def get_ai_profile(user_id):
    res = supabase.table("user_ai_profiles").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


def analyze_resume_data(resume_text, matched_jobs):
    jobs_summary = [
        {
            "title": j.get("title"),
            "company": j.get("company"),
            "description": (j.get("description") or "")[:250]
        }
        for j in matched_jobs[:5]
    ]
    try:
        structured_llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.2,
            max_retries=2
        ).with_structured_output(ResumeAnalysis)
        result = (ANALYSIS_PROMPT | structured_llm).invoke({
            "resume_text": resume_text,
            "jobs_json": json.dumps(jobs_summary, indent=2)
        })
        res_dict = result.model_dump()
        if not res_dict.get("extracted_skills"):
            res_dict["extracted_skills"] = extract_skills_local(resume_text)
        return res_dict
    except Exception as e:
        print(f"Resume analysis LLM error: {e}")
        traceback.print_exc()
        skills = extract_skills_local(resume_text)
        return {
            "match_score": 75 if skills else 50,
            "extracted_skills": skills,
            "recommendation": "Highlight core project metrics, clarify system design experience, and align key skills with current market postings.",
        }


def _rank_and_filter_jobs(jobs, user_skills):
    if not user_skills or not jobs:
        return jobs[:5]

    skills_lower = {s.lower() for s in user_skills}
    scored = []

    for j in jobs:
        title = (j.get("title") or "").lower()
        desc = (j.get("description") or "").lower()
        text = f"{title} {desc}"

        matched_count = sum(1 for s in skills_lower if s in text)
        title_match = sum(2 for s in skills_lower if s in title)
        score = matched_count + title_match

        scored.append((score, j))

    scored.sort(key=lambda x: x[0], reverse=True)
    filtered = [j for score, j in scored if score > 0]
    return filtered[:5] if filtered else [j for score, j in scored[:3]]


def generate_answer(resume, jobs, query, total_jobs=0, saved_jobs_count=0, user_skills=None):
    if user_skills is None:
        user_skills = extract_skills_local(resume)

    q_lower = query.lower().strip()
    job_keywords = ["suggest", "recommend", "find job", "show job", "match job", "job suggestion", "job match", "get job", "looking for job", "jobs for me", "roles", "opportunity", "opportunities", "jobs should i apply", "what jobs"]
    is_job_query = any(k in q_lower for k in job_keywords)

    candidate_jobs = jobs if is_job_query else []
    filtered_jobs = _rank_and_filter_jobs(candidate_jobs, user_skills) if is_job_query else []
    valid_ids = [j.get("id") for j in filtered_jobs]

    jobs_input = [
        {
            "id": j.get("id"),
            "title": j.get("title"),
            "company": j.get("company"),
            "description": (j.get("description") or "")[:250]
        }
        for j in filtered_jobs
    ]

    try:
        structured_llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.2,
            max_tokens=400,
            max_retries=2
        ).with_structured_output(ChatResponse)

        result = (CHAT_PROMPT | structured_llm).invoke({
            "resume": resume[:4000],
            "user_skills": ", ".join(user_skills),
            "jobs_json": json.dumps(jobs_input, indent=2),
            "valid_ids": json.dumps(valid_ids),
            "total_jobs": total_jobs,
            "saved_jobs_count": saved_jobs_count,
            "query": query
        })
        res_dict = result.model_dump()
        if not is_job_query:
            res_dict["jobs"] = []
        elif is_job_query and not res_dict.get("jobs"):
            if "job alert" not in res_dict.get("text", "").lower():
                res_dict["text"] = "Currently, there are no suitable job postings matching your profile in our database. Please set an email alert for your preferred roles in the **Job Alerts** section so you get notified instantly when new matching positions are added!"
        return res_dict
    except Exception as e:
        print(f"generate_answer error: {e}")
        err_msg = str(e).lower()
        if any(term in err_msg for term in ["429", "resourceexhausted", "quota", "rate limit", "exceeded"]):
            return {
                "text": "HirePulse AI service is currently receiving high demand. Please wait 15–30 seconds before asking another question.",
                "jobs": []
            }
        traceback.print_exc()
        return _fallback(query, filtered_jobs, total_jobs, saved_count=saved_jobs_count, user_skills=user_skills)


def _fallback(query, jobs, total_jobs, saved_count, user_skills=None):
    q = query.lower()
    if any(w in q for w in ["hi", "hello", "hey", "hii", "yo"]):
        return {"text": "Hello! I'm HirePulse Pivot AI. How can I help with your job search?", "jobs": []}
    if any(w in q for w in ["resume", "cv", "profile"]):
        return {"text": "I've reviewed your resume — great experience! Ask me for job recommendations or optimization advice.", "jobs": []}
    if any(w in q for w in ["saved jobs", "bookmarked"]):
        return {"text": f"You have {saved_count} saved jobs!", "jobs": []}
    if any(w in q for w in ["how many", "total jobs"]):
        return {"text": f"We have {total_jobs} jobs listed. What role are you looking for?", "jobs": []}
    if any(w in q for w in ["suggest", "find", "show", "match", "recommend", "jobs", "apply"]):
        if not jobs:
            return {
                "text": "Currently, there are no suitable job postings matching your profile in our database. Please set an email alert for your preferred roles in the **Job Alerts** section so you get notified instantly when new matching positions are added!",
                "jobs": []
            }
        skills_text = f" ({', '.join(user_skills[:3])})" if user_skills else ""
        return {"text": f"Here are the top jobs directly matching your skills{skills_text}:", "jobs": [{"id": j.get("id"), "match_reason": f"Matches your skills in {j.get('title', 'software')}"} for j in jobs], "fallback": True}
    return {"text": "Ask me for job suggestions or resume feedback!", "jobs": []}
