import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import os
import time
from dotenv import load_dotenv
import requests
from database import supabase
from RAG import get_embedding

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
TARGET_JOBS = 50

KEYWORDS = [
    "software developer", "data analyst", "web developer", "python",
    "java developer", "marketing manager", "sales executive",
    "human resources", "business analyst", "project manager",
    "content writer", "graphic designer", "accountant",
    "customer support", "operations manager", "mechanical engineer",
    "civil engineer", "electrical engineer", "digital marketing",
    "finance manager",
]

def get_or_create_source():
    existing = supabase.table("job_sources").select("*").eq("source_name", "Adzuna").execute()
    if existing.data:
        return existing.data[0]["id"]
    new = supabase.table("job_sources").insert({"source_name": "Adzuna", "source_url": "https://www.adzuna.in"}).execute()
    return new.data[0]["id"]

def clear_old_jobs():
    """Delete all outdated jobs (and saved_jobs referencing them) to ensure fresh data."""
    print("Deleting old/outdated jobs from Supabase...")
    try:
        supabase.table("saved_jobs").delete().neq("id", 0).execute()
        print("  Old saved_jobs references cleared.")
    except Exception as e:
        print(f"  [WARNING] Error clearing saved_jobs: {e}")

    try:
        supabase.table("jobs").delete().neq("id", 0).execute()
        print("  Outdated jobs deleted successfully.")
    except Exception as e:
        print(f"  [ERROR] Failed to delete old jobs: {e}")

def fetch_jobs(keyword, page=1):
    try:
        resp = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/in/search/{page}",
            params={"app_id": ADZUNA_APP_ID, "app_key": ADZUNA_APP_KEY,
                     "results_per_page": 20, "what": keyword},
            timeout=15
        )
        if resp.status_code == 401:
            print("  [ERROR] 401 - check ADZUNA_APP_ID / ADZUNA_APP_KEY in .env")
            return []
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        print(f"  [ERROR] {e}")
        return []

def refresh_and_import_jobs(target_jobs=50):
    print("==========================================")
    print(f"Starting 3-day job refresh (Target: {target_jobs} fresh jobs)...")
    print("==========================================")

    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("[FATAL] ADZUNA_APP_ID or ADZUNA_APP_KEY not set in .env")
        return

    # Delete existing outdated jobs first
    clear_old_jobs()

    source_id = get_or_create_source()
    inserted, skipped = 0, 0
    seen = set()
    new_jobs = []

    for keyword in KEYWORDS:
        if inserted >= target_jobs:
            break

        print(f"\nSearching: \"{keyword}\"")
        for job in fetch_jobs(keyword):
            if inserted >= target_jobs:
                break
            try:
                url = job.get("redirect_url", "")
                title = job.get("title", "").strip()
                company = (job.get("company") or {}).get("display_name", "Unknown").strip()
                location = (job.get("location") or {}).get("display_name", "India").strip()
                salary = int(job.get("salary_max") or job.get("salary_min") or 0) or None
                desc = (job.get("description") or "")[:500] or None

                if not title or not url:
                    continue
                if url in seen:
                    skipped += 1
                    continue
                seen.add(url)

                embedding = None
                try:
                    embedding = get_embedding(f"{title} {desc or ''}")
                except Exception as e:
                    print(f"  [WARNING] Failed to generate embedding: {e}")

                res = supabase.table("jobs").insert({
                    "title": title, "company": company, "location": location,
                    "salary": salary, "job_type": "Full-time",
                    "description": desc, "job_url": url, "source_id": source_id,
                    "embedding": embedding
                }).execute()

                if res.data:
                    new_jobs.append(res.data[0])

                inserted += 1
                print(f"  [{inserted}/{target_jobs}] Inserted: {title} at {company}")
            except Exception as e:
                print(f"  [ERROR] {e}")

        time.sleep(1)

    print(f"\nDone! {inserted} fresh jobs imported, replacing outdated jobs.")

    if new_jobs:
        try:
            from alerts import match_and_send_alerts
            match_and_send_alerts(new_jobs)
        except Exception as e:
            print(f"  [WARNING] Alert processing error: {e}")

def main():
    refresh_and_import_jobs(TARGET_JOBS)

if __name__ == "__main__":
    main()

