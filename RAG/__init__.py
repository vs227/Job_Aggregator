import os
import json
import traceback
from database import supabase
from cache import cache_get, cache_set, cache_delete, hash_text
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
    "You are HirePulse Pivot AI, an expert career recruiter.\n\n"
    "CANDIDATE CONTEXT:\n{resume}\n"
    "SKILLS: {user_skills}\n"
    "MATCHED JOBS: {jobs_json}\n"
    "{history}\n\n"
    "USER QUERY: {query}\n\n"
    "RULES:\n"
    "1. ABSOLUTE TRUTH: Mention ONLY skills present in CANDIDATE CONTEXT/SKILLS.\n"
    "2. INTENT SEPARATION: If query asks about resume changes, resume advice, CV improvements, or career guidance, return 'jobs': [] and answer with specific resume recommendations. ONLY attach 'jobs' if the user explicitly asks for job openings or listings to apply for.\n"
    "3. NO MATCHES: If asking for jobs but no matches exist, instruct candidate to set an email alert in Job Alerts.\n"
    "4. FORMATTING: Use clear paragraphs and separate bullet points (`1. **Title**: text`) with double line breaks (`\n\n`)."
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
    import re
    text_lower = text.lower()
    found = []
    for s in KNOWN_SKILLS:
        pattern = r'(?<![a-zA-Z0-9_#+])' + re.escape(s) + r'(?![a-zA-Z0-9_#+])'
        if re.search(pattern, text_lower):
            found.append(s)
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
    # Check Redis cache for embedding (deterministic for same model + text)
    cache_key = f"emb:{hash_text(cleaned)}:{task}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    if task == "RETRIEVAL_QUERY":
        result = embeddings.embed_query(cleaned)
    else:
        result = embeddings.embed_documents([cleaned])[0]
    # Cache for 14 days (embeddings are deterministic)
    cache_set(cache_key, result, ttl_seconds=14 * 86400)
    return result


def get_embeddings_batch(texts):
    cleaned_texts = [" ".join(t.split()) for t in texts if t.strip()]
    if not cleaned_texts:
        return []
    return embeddings.embed_documents(cleaned_texts)


def save_resume(user_id, text, embedding):
    try:
        supabase.table("user_resumes").upsert(
            {"user_id": user_id, "resume_text": text, "embedding": embedding},
            on_conflict="user_id",
        ).execute()
    except Exception as e:
        print(f"Notice saving resume with embedding: {e}. Falling back to text-only save...")
        try:
            supabase.table("user_resumes").upsert(
                {"user_id": user_id, "resume_text": text},
                on_conflict="user_id",
            ).execute()
            print(f"Successfully saved resume text for user {user_id}")
        except Exception as ex:
            print(f"Critical error saving resume text: {ex}")


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
    # Check Redis cache first
    cache_key = f"user:{user_id}:resume"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    res = supabase.table("user_resumes").select("*").eq("user_id", user_id).execute()
    result = res.data[0] if res.data else None
    if result:
        # Cache for 24 hours (invalidated on resume upload)
        # Don't cache the embedding vector — it's large and not needed for display
        cache_data = {k: v for k, v in result.items() if k != "embedding"}
        cache_set(cache_key, cache_data, ttl_seconds=24 * 3600)
    return result


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


GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-1.5-flash",
]


def _call_gemini_structured(prompt_template, input_dict, pydantic_schema, temperature=0.2, max_tokens=400):
    for model_name in GEMINI_MODELS:
        try:
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=1
            ).with_structured_output(pydantic_schema)
            result = (prompt_template | llm).invoke(input_dict)
            return result.model_dump()
        except Exception as e:
            print(f"Gemini model '{model_name}' failed or rate-limited: {e}.")
    return None


def extract_ai_profile(resume_text):
    res_dict = _call_gemini_structured(PROFILE_PROMPT, {"resume_text": resume_text}, AIProfile, temperature=0.1)
    if res_dict:
        return res_dict
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
        print(f"Successfully saved AI profile for user {user_id}")
    except Exception as e:
        print(f"Notice saving AI profile with on_conflict: {e}. Trying standard upsert...")
        try:
            supabase.table("user_ai_profiles").upsert(data).execute()
        except Exception as ex:
            print(f"Critical error saving AI profile: {ex}")


def get_ai_profile(user_id):
    # Check Redis cache first
    cache_key = f"user:{user_id}:ai_profile"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    res = supabase.table("user_ai_profiles").select("*").eq("user_id", user_id).execute()
    result = res.data[0] if res.data else None
    if result:
        # Cache for 24 hours (invalidated on resume upload)
        cache_set(cache_key, result, ttl_seconds=24 * 3600)
    return result


def analyze_resume_data(resume_text, matched_jobs):
    jobs_summary = [
        {
            "title": j.get("title"),
            "company": j.get("company"),
            "description": (j.get("description") or "")[:250]
        }
        for j in matched_jobs[:5]
    ]
    res_dict = _call_gemini_structured(ANALYSIS_PROMPT, {
        "resume_text": resume_text,
        "jobs_json": json.dumps(jobs_summary, indent=2)
    }, ResumeAnalysis, temperature=0.2)

    if res_dict:
        if not res_dict.get("extracted_skills"):
            res_dict["extracted_skills"] = extract_skills_local(resume_text)
        return res_dict

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


def _call_mistral_llm(resume_slice, user_skills, jobs_json, query, history=""):
    import requests
    mistral_key = os.environ.get("MISTRAL_API_KEY")
    if not mistral_key:
        print("No MISTRAL_API_KEY found in environment.")
        return None

    headers = {
        "Authorization": f"Bearer {mistral_key}",
        "Content-Type": "application/json"
    }
    history_part = f"\n{history}\n" if history else ""
    prompt_text = (
        f"You are HirePulse Pivot AI, an expert career recruiter.\n\n"
        f"CANDIDATE CONTEXT:\n{resume_slice}\n"
        f"SKILLS: {user_skills}\n"
        f"MATCHED JOBS: {jobs_json}\n"
        f"{history_part}\n"
        f"USER QUERY: {query}\n\n"
        f"RULES:\n"
        f"1. ABSOLUTE TRUTH: Mention ONLY skills present in CANDIDATE CONTEXT/SKILLS.\n"
        f"2. INTENT SEPARATION: If query asks for resume advice/feedback, return 'jobs': [] and detailed text advice. ONLY attach 'jobs' if user explicitly asks for job suggestions.\n"
        f"3. FORMATTING: Use clear paragraphs and separate bullet points (`1. **Title**: text`) with double line breaks (`\n\n`).\n\n"
        f"Return ONLY a valid JSON object matching format: {{\"text\": \"your advice\", \"jobs\": []}}"
    )
    mistral_models = ["mistral-small-latest"]
    for model in mistral_models:
        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt_text}],
            "temperature": 0.2,
            "max_tokens": 400
        }
        try:
            print(f"Trying single Mistral AI model: {model}...")
            resp = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                raw_content = data["choices"][0]["message"]["content"]
                cleaned = raw_content.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                parsed = json.loads(cleaned.strip())
                return {
                    "text": parsed.get("text", "Here are recommendations based on your candidate profile:"),
                    "jobs": parsed.get("jobs", [])
                }
            else:
                print(f"Mistral API model {model} returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"Mistral API model {model} failover error: {e}")
    return None


def generate_answer(resume, jobs, query, total_jobs=0, saved_jobs_count=0, user_skills=None, history=""):
    if user_skills is None:
        user_skills = extract_skills_local(resume)

    filtered_jobs = _rank_and_filter_jobs(jobs, user_skills)

    jobs_input = [
        {
            "id": j.get("id"),
            "title": j.get("title"),
            "company": j.get("company")
        }
        for j in filtered_jobs
    ]

    resume_slice = resume[:600]
    skills_str = ", ".join(user_skills[:4])
    jobs_json = json.dumps(jobs_input[:3])

    res_dict = _call_gemini_structured(CHAT_PROMPT, {
        "resume": resume_slice,
        "user_skills": skills_str,
        "jobs_json": jobs_json,
        "history": history if history else "",
        "query": query
    }, ChatResponse, temperature=0.2, max_tokens=400)

    if res_dict:
        return res_dict

    print("Gemini API rate limit or error across all models. Instant failover to Mistral AI...")
    mistral_res = _call_mistral_llm(resume_slice, skills_str, jobs_json, query, history=history)
    if mistral_res:
        return mistral_res

    print("Mistral AI failover complete/exhausted. Using intelligent local fallback...")
    return _fallback(query, filtered_jobs, total_jobs, saved_count=saved_jobs_count, user_skills=user_skills)


def _fallback(query, jobs, total_jobs, saved_count, user_skills=None):
    skills_fmt = ", ".join(user_skills[:5]) if user_skills else "your technical domain"
    query_lower = query.strip().lower()

    # Check for simple greeting intent
    greetings = {"hi", "hii", "hello", "hey", "hi there", "hello there", "good morning", "good evening"}
    if query_lower in greetings or any(query_lower.startswith(g) for g in ["hi ", "hii ", "hello ", "hey "]):
        return {
            "text": f"Hello! How can I assist you with your career or resume optimization today? Feel free to ask for job recommendations, resume feedback, or skill guidance tailored to your background in **{skills_fmt}**.",
            "jobs": []
        }

    # Check for Resume Feedback / Resume Change Intent
    resume_keywords = ["resume", "cv", "profile", "change", "improve", "feedback", "advice", "audit", "format", "summary", "edit"]
    is_resume_query = any(w in query_lower for w in resume_keywords)

    # Explicit Job Search Intent ONLY
    job_keywords = ["job", "jobs", "opening", "openings", "vacancy", "vacancies", "position", "positions", "hiring", "apply", "recommend jobs", "suggest jobs", "find jobs"]
    is_job_request = not is_resume_query and any(w in query_lower for w in job_keywords)

    if is_resume_query:
        text = (
            f"Here are key recommendations to optimize your resume based on your extracted background (**{skills_fmt}**):\n\n"
            f"1. **Quantify Project Achievements**: Replace general task descriptions with concrete metrics (e.g. latency reductions, percentage efficiency gains, dataset sizes).\n\n"
            f"2. **Highlight Technical Stack**: Ensure your proficiencies in {skills_fmt} are positioned prominently in your technical summary and project bullets.\n\n"
            f"3. **Use Strong Action Verbs**: Begin bullet points with impactful verbs like *Architected*, *Engineered*, *Deployed*, and *Optimized*."
        )
        return {"text": text, "jobs": []}

    attached_jobs = []
    if is_job_request and jobs:
        for j in jobs[:3]:
            attached_jobs.append({
                "id": j.get("id"),
                "match_reason": f"Matches key skill requirements in {skills_fmt}."
            })
        text = (
            f"Based on your candidate profile and extracted skills (**{skills_fmt}**), "
            f"here are top matching opportunities curated from our live market listings:\n\n"
            f"1. **Target Role Alignment**: These roles closely match your core technical background in {skills_fmt}.\n\n"
            f"2. **Optimization Suggestion**: Tailor your resume summary for these target roles to increase recruiter engagement."
        )
    else:
        text = (
            f"Here is career guidance tailored for your candidate profile (**{skills_fmt}**):\n\n"
            f"1. **Resume Impact**: Highlight technical achievements with concrete metrics and project outcomes.\n\n"
            f"2. **Skill Showcase**: Ensure your proficiencies in {skills_fmt} are positioned clearly in your candidate summary.\n\n"
            f"3. **Job Search Strategy**: Browse target positions in Job Listings or set automated Job Alerts to get matching roles."
        )

    return {
        "text": text,
        "jobs": attached_jobs
    }

