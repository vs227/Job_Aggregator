import os
import resend
from database import supabase
from RAG import get_ai_profile

resend.api_key = os.getenv("RESEND_API_KEY")


def _enrich_with_profile(jobs, profile):
    if not profile:
        return jobs
    user_skills = {s.lower() for s in (profile.get("top_skills") or [])}
    missing = {s.lower() for s in (profile.get("missing_skills") or [])}
    for job in jobs:
        text = f"{(job.get('title') or '')} {(job.get('description') or '')}".lower()
        job["_matched"] = [s for s in user_skills if s in text]
        job["_missing"] = [s for s in missing if s in text]
    return jobs


def send_email(to_email, keyword, jobs, profile=None):
    jobs_html = ""
    text_body = f"Job Alerts for '{keyword.title()}'\n\n"

    for job in jobs[:10]:
        salary = f"Rs. {job['salary']}" if job.get("salary") else "Not specified"
        extra_html = ""
        if job.get("_matched"):
            extra_html += f'<p style="margin:5px 0 0;color:#16a34a;font-size:.85rem">✓ {", ".join(job["_matched"])}</p>'
        if job.get("_missing"):
            extra_html += f'<p style="margin:2px 0 0;color:#ea580c;font-size:.85rem">To learn: {", ".join(job["_missing"])}</p>'

        jobs_html += f"""
        <div style="margin-bottom:20px;padding:15px;border:1px solid #e2e8f0;border-radius:8px;background:#fff">
            <h3 style="margin:0 0 10px"><a href="{job['job_url']}" style="color:#2563eb;text-decoration:none;font-size:1.1rem;font-weight:600">{job['title']}</a></h3>
            <p style="margin:0 0 5px;color:#475569;font-size:.95rem"><strong>Company:</strong> {job['company']}</p>
            <p style="margin:0 0 5px;color:#475569;font-size:.95rem"><strong>Location:</strong> {job['location']}</p>
            <p style="margin:0;color:#475569;font-size:.95rem"><strong>Salary:</strong> {salary}</p>
            {extra_html}
        </div>"""
        text_body += f"- {job['title']} at {job['company']}\n  Location: {job['location']}\n  Salary: {salary}\n  Link: {job['job_url']}\n\n"

    score_html = ""
    if profile and profile.get("job_fit_score"):
        score_html = f'<p style="color:#475569;margin-bottom:5px">Profile match: <strong>{profile["job_fit_score"]}%</strong></p>'

    html_body = f"""
    <div style="max-width:600px;margin:0 auto;font-family:sans-serif;background:#f8fafc;padding:20px;border-radius:12px">
        <h2 style="color:#1e293b;margin-top:0;border-bottom:2px solid #3b82f6;padding-bottom:10px">Job Alerts for '{keyword.title()}'</h2>
        {score_html}
        <p style="color:#475569;margin-bottom:20px">Jobs matching your preference:</p>
        {jobs_html}
    </div>"""

    try:
        resend.Emails.send({"from": "onboarding@resend.dev", "to": to_email, "subject": f"Job Alert: {keyword.title()}", "html": html_body, "text": text_body})
    except Exception as e:
        print(f"Email error to {to_email}: {e}")


def _filter_jobs(jobs, keyword, location=None, min_salary=None):
    matched = []
    kw = keyword.strip().lower()
    for job in jobs:
        title = (job.get("title") or "").lower()
        company = (job.get("company") or "").lower()
        desc = (job.get("description") or "").lower()

        if kw not in title and kw not in company and kw not in desc:
            continue
        if location and location.strip().lower() not in (job.get("location") or "").lower():
            continue
        if min_salary:
            try:
                if not job.get("salary") or int(job["salary"]) < int(min_salary):
                    continue
            except (ValueError, TypeError):
                continue
        matched.append(job)
    return matched


def match_and_send_alerts(new_jobs):
    if not new_jobs:
        return
    res = supabase.table("alert_preferences").select("*, users(email, id)").eq("email_enabled", True).execute()
    if not res.data:
        return

    for pref in res.data:
        user = pref.get("users")
        if not user or not user.get("email"):
            continue

        matched = _filter_jobs(new_jobs, pref["keyword"], pref.get("location"), pref.get("min_salary"))
        if matched:
            profile = get_ai_profile(user.get("id"))
            send_email(user["email"], pref["keyword"], _enrich_with_profile(matched, profile), profile)


def send_immediate_alerts(user_id, keyword, location=None, min_salary=None):
    res_user = supabase.table("users").select("email").eq("id", user_id).execute()
    if not res_user.data:
        return

    res_jobs = supabase.table("jobs").select("*").order("id", desc=True).limit(100).execute()
    if not res_jobs.data:
        return

    matched = _filter_jobs(res_jobs.data, keyword, location, min_salary)
    if matched:
        profile = get_ai_profile(user_id)
        send_email(res_user.data[0]["email"], keyword, _enrich_with_profile(matched, profile), profile)
