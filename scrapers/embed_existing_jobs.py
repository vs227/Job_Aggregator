import os
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from database import supabase
from RAG import get_embedding

def embed_all():
    jobs = supabase.table("jobs").select("id, title, description").is_("embedding", "null").execute().data
    print(f"Found {len(jobs)} jobs without embeddings.")
    for i, job in enumerate(jobs):
        text = f"{job['title']} {job['description'] or ''}"
        try:
            emb = get_embedding(text)
            supabase.table("jobs").update({"embedding": emb}).eq("id", job["id"]).execute()
            print(f"[{i+1}/{len(jobs)}] Embedded: {job['title']}")
            time.sleep(0.5)
        except Exception as e:
            print(f"Error embedding job {job['id']}: {e}")
            time.sleep(2)

if __name__ == "__main__":
    embed_all()
