import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from database import supabase
from RAG import get_ai_profile

import json
import urllib.request

def _get_smtp_credentials():
    email = (
        os.getenv("SMTP_EMAIL") or
        os.getenv("SMTP_USER") or
        os.getenv("MAIL_USERNAME") or
        os.getenv("EMAIL_HOST_USER") or
        ""
    ).strip().strip('"').strip("'")

    password = (
        os.getenv("SMTP_PASSWORD") or
        os.getenv("SMTP_PASS") or
        os.getenv("MAIL_PASSWORD") or
        os.getenv("EMAIL_HOST_PASSWORD") or
        ""
    ).replace(" ", "").strip().strip('"').strip("'")

    return email, password


def _send_resend_api_email(to_email: str, subject: str, html_body: str, sender_name: str = "HirePulse AI") -> bool:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return False
    try:
        from_header = os.getenv("RESEND_FROM_EMAIL", "HirePulse AI <onboarding@resend.dev>")
        payload = json.dumps({
            "from": from_header,
            "to": [to_email],
            "subject": subject,
            "html": html_body
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "HirePulse/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status in (200, 201):
                print(f"[Resend HTTP API Success] Email sent to {to_email}")
                return True
    except Exception as e:
        print(f"[Resend HTTP API Error] Failed to send email via Resend API: {e}")
    return False


def _send_smtp_email(to_email: str, subject: str, text_body: str, html_body: str, sender_name: str = "HirePulse AI") -> bool:
    # 1. Try Resend HTTP API first if RESEND_API_KEY is present (bypasses Render outbound port blocks)
    if os.getenv("RESEND_API_KEY"):
        if _send_resend_api_email(to_email, subject, html_body, sender_name):
            return True

    smtp_email, smtp_password = _get_smtp_credentials()

    if not smtp_email or not smtp_password:
        print(f"[Email Error] No email credentials found in environment. Email to {to_email} skipped.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{smtp_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    # Try SSL Port 465 first
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=12) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        print(f"[Email Success] Sent email to {to_email} via SSL Port 465")
        return True
    except Exception as ssl_err:
        print(f"[Email Notice] SSL Port 465 failed for {to_email}: {ssl_err}. Trying TLS Port 587...")

    # Fallback to TLS Port 587
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=12) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        print(f"[Email Success] Sent email to {to_email} via TLS Port 587")
        return True
    except Exception as tls_err:
        print(f"[Email Error] Failed to send email to {to_email} via Port 587: {tls_err}")
        return False


def test_smtp_diagnostic(to_email: str) -> dict:
    smtp_email, smtp_password = _get_smtp_credentials()
    resend_key = os.getenv("RESEND_API_KEY", "").strip()

    results = {
        "to_email": to_email,
        "resend_api_key_set": bool(resend_key),
        "smtp_email_found": smtp_email,
        "smtp_password_length": len(smtp_password) if smtp_password else 0,
        "resend_api": None,
        "ssl_465": None,
        "tls_587": None,
        "success": False
    }

    if resend_key:
        resend_ok = _send_resend_api_email(to_email, "HirePulse Diagnostic Test", "<p>Test email via Resend API from Render</p>")
        results["resend_api"] = "SUCCESS" if resend_ok else "FAILED"
        if resend_ok:
            results["success"] = True
            return results

    if not smtp_email or not smtp_password:
        results["error"] = "No SMTP credentials set in environment"
        return results

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "HirePulse SMTP Diagnostic Test"
    msg["From"] = f"HirePulse AI <{smtp_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText("Test email from Render server.", "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        results["ssl_465"] = "SUCCESS"
        results["success"] = True
        return results
    except Exception as e:
        results["ssl_465"] = f"FAILED: {type(e).__name__}: {str(e)}"

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        results["tls_587"] = "SUCCESS"
        results["success"] = True
    except Exception as e:
        results["tls_587"] = f"FAILED: {type(e).__name__}: {str(e)}"

    return results




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

    return _send_smtp_email(to_email, f"Job Alert: {keyword.title()}", text_body, html_body, sender_name="HirePulse Alerts")


def send_otp_email(to_email, otp_code):
    text_body = f"Your HirePulse verification code is: {otp_code}\n\nThis code will expire in 10 minutes."
    html_body = f"""
    <div style="max-width:500px;margin:0 auto;font-family:sans-serif;background:#0c0c0c;color:#fafafa;padding:32px;border-radius:12px;border:1px solid rgba(255,255,255,0.1)">
        <h2 style="color:#ffffff;margin-top:0;font-size:1.4rem">Verify Your HirePulse Account</h2>
        <p style="color:#a3a3a3;font-size:0.95rem;line-height:1.5">Use the following 6-digit verification code to complete your registration:</p>
        <div style="font-size:2.2rem;font-weight:800;letter-spacing:8px;color:#3b82f6;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.2);padding:16px;text-align:center;border-radius:8px;margin:24px 0">
            {otp_code}
        </div>
        <p style="color:#737373;font-size:0.85rem;margin-bottom:0">This code will expire in 10 minutes. If you did not request this verification, please ignore this email.</p>
    </div>
    """
    return _send_smtp_email(to_email, f"{otp_code} is your HirePulse verification code", text_body, html_body, sender_name="HirePulse AI")


def send_password_reset_otp_email(to_email, otp_code):
    text_body = f"Your HirePulse password reset code is: {otp_code}\n\nThis code will expire in 10 minutes."
    html_body = f"""
    <div style="max-width:500px;margin:0 auto;font-family:sans-serif;background:#0c0c0c;color:#fafafa;padding:32px;border-radius:12px;border:1px solid rgba(255,255,255,0.1)">
        <h2 style="color:#ffffff;margin-top:0;font-size:1.4rem">Reset Your HirePulse Password</h2>
        <p style="color:#a3a3a3;font-size:0.95rem;line-height:1.5">Use the following 6-digit verification code to reset your password and verify your identity:</p>
        <div style="font-size:2.2rem;font-weight:800;letter-spacing:8px;color:#ef4444;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);padding:16px;text-align:center;border-radius:8px;margin:24px 0">
            {otp_code}
        </div>
        <p style="color:#737373;font-size:0.85rem;margin-bottom:0">This code will expire in 10 minutes. If you did not request a password reset, please ignore this email.</p>
    </div>
    """
    return _send_smtp_email(to_email, f"{otp_code} is your HirePulse password reset code", text_body, html_body, sender_name="HirePulse Security")



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


def _enrich_with_profile(jobs, profile):
    if not profile or not profile.get("skills"):
        return jobs
    user_skills = set(s.lower() for s in profile.get("skills", []))
    if not user_skills:
        return jobs

    enriched = []
    for job in jobs:
        job_copy = dict(job)
        job_skills = set(s.lower() for s in (job_copy.get("skills") or []))
        if job_skills:
            matched = list(user_skills.intersection(job_skills))
            missing = list(job_skills - user_skills)
            if matched:
                job_copy["_matched"] = matched
            if missing:
                job_copy["_missing"] = missing
        enriched.append(job_copy)
    return enriched



def match_and_send_alerts(new_jobs):
    if not new_jobs:
        return
    print(f"[Job Alerts] Checking {len(new_jobs)} newly imported jobs against user alert preferences...")
    try:
        res = supabase.table("alert_preferences").select("*, users(email, id)").eq("email_enabled", True).execute()
        if not res.data:
            print("[Job Alerts] No active user alert preferences found in database.")
            return

        sent_count = 0
        for pref in res.data:
            user = pref.get("users")
            if not user or not user.get("email"):
                continue

            matched = _filter_jobs(new_jobs, pref["keyword"], pref.get("location"), pref.get("min_salary"))
            if matched:
                print(f"[Job Alerts] Match found! Sending {len(matched)} job alert(s) to '{user['email']}' for keyword '{pref['keyword']}'")
                profile = get_ai_profile(user.get("id"))
                send_email(user["email"], pref["keyword"], _enrich_with_profile(matched, profile), profile)
                sent_count += 1

        print(f"[Job Alerts] Automatic email alert check completed. Sent {sent_count} alert email(s).")
    except Exception as e:
        print(f"[Job Alerts] Error during automatic alert processing: {e}")



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
