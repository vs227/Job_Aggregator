import os
from dotenv import load_dotenv
load_dotenv()

import smtplib
from email.mime.multipart import MIMEMultipart

from email.mime.text import MIMEText
from database import supabase
from RAG import get_ai_profile

import json
import base64
import urllib.request
import urllib.error
import urllib.parse

def _get_sender_email():
    return (
        os.getenv("SENDER_EMAIL") or
        os.getenv("SMTP_EMAIL") or
        os.getenv("SMTP_USER") or
        "parasff0007@gmail.com"
    ).strip().strip('"').strip("'")


# ─── Gmail API over HTTPS (Port 443 — NOT blocked by Render) ─────────

def _get_gmail_access_token() -> str:
    """Exchange refresh token for a fresh access token via Google OAuth2."""
    client_id = os.getenv("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "").strip()

    if not all([client_id, client_secret, refresh_token]):
        return ""

    try:
        payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("access_token", "")
    except Exception as e:
        print(f"[Gmail API] Failed to get access token: {e}")
        return ""


def _send_gmail_api_email(to_email: str, subject: str, text_body: str, html_body: str, sender_name: str = "HirePulse AI") -> dict:
    """Send email via Gmail REST API over HTTPS (port 443). Not blocked by Render."""
    access_token = _get_gmail_access_token()
    if not access_token:
        return {"ok": False, "error": "Gmail API credentials not configured (need GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN)"}

    sender_email = _get_sender_email()

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    # Gmail API requires base64url-encoded raw message
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    try:
        payload = json.dumps({"raw": raw_message}).encode("utf-8")
        req = urllib.request.Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            resp_data = json.loads(resp_body) if resp_body else {}
            msg_id = resp_data.get("id", "unknown")
            print(f"[Gmail API Success] Email sent to {to_email} | id={msg_id}")
            return {"ok": True, "id": msg_id, "method": "gmail_api", "response": resp_data}
    except urllib.error.HTTPError as he:
        err_body = ""
        try:
            err_body = he.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(f"[Gmail API HTTP Error] {he.code}: {err_body}")
        return {"ok": False, "http_error": he.code, "detail": err_body, "method": "gmail_api"}
    except Exception as e:
        print(f"[Gmail API Error] {e}")
        return {"ok": False, "error": str(e), "method": "gmail_api"}

# ─── Brevo HTTPS API ─────────────────────────────────────────────────

def _send_brevo_api_email(to_email: str, subject: str, html_body: str, text_body: str = "", sender_name: str = "HirePulse AI") -> dict:
    """Returns dict with 'ok' bool and 'detail' info."""
    api_key = (os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY") or "").strip()
    if not api_key:
        print("[Email Warning] BREVO_API_KEY is not set in environment.")
        return {"ok": False, "error": "BREVO_API_KEY not set"}
    sender_email = _get_sender_email()
    try:
        payload_dict = {
            "sender": {"name": sender_name, "email": sender_email},
            "replyTo": {"name": sender_name, "email": sender_email},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_body
        }

        if text_body:
            payload_dict["textContent"] = text_body

        payload = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            resp_body = response.read().decode("utf-8", errors="replace")
            resp_data = {}
            try:
                resp_data = json.loads(resp_body)
            except Exception:
                pass
            if response.status in (200, 201):
                msg_id = resp_data.get("messageId", "unknown")
                print(f"[Brevo API Success] Email sent to {to_email} | messageId={msg_id} | status={response.status}")
                return {"ok": True, "messageId": msg_id, "status": response.status, "response": resp_data}
            else:
                print(f"[Brevo API Unexpected] status={response.status} body={resp_body}")
                return {"ok": False, "status": response.status, "response": resp_data}
    except urllib.error.HTTPError as he:
        err_body = ""
        try:
            err_body = he.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(f"[Brevo API HTTP Error] {he.code}: {err_body}")
        return {"ok": False, "http_error": he.code, "detail": err_body}
    except Exception as e:
        print(f"[Brevo API Error] Failed to send email via Brevo API: {e}")
        return {"ok": False, "error": str(e)}


# ─── Unified Email Sender (Priority: Gmail API → Brevo → SMTP) ──────

def _send_smtp_email(to_email: str, subject: str, text_body: str, html_body: str, sender_name: str = "HirePulse AI") -> bool:
    # 1st Priority: Gmail API over HTTPS (works on Render, emails from real Gmail)
    if os.getenv("GMAIL_REFRESH_TOKEN"):
        result = _send_gmail_api_email(to_email, subject, text_body, html_body, sender_name=sender_name)
        if result.get("ok"):
            return True
        print(f"[Email] Gmail API failed, trying fallbacks... ({result})")

    # 2nd Priority: Brevo HTTPS API
    if os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY"):
        result = _send_brevo_api_email(to_email, subject, html_body, text_body=text_body, sender_name=sender_name)
        return result.get("ok", False)

    # 3rd Priority: Direct Gmail SMTP (works locally, blocked on Render free tier)
    smtp_email = _get_sender_email()
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip()

    if not smtp_password:
        print(f"[Email Error] No email method available. Email to {to_email} skipped.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{smtp_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=12) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        return True
    except Exception as err:
        print(f"[SMTP Error] Failed to send email: {err}")
        return False


def _brevo_api_get(endpoint: str) -> dict:
    """Helper: make a GET request to Brevo API."""
    api_key = (os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY") or "").strip()
    if not api_key:
        return {"error": "BREVO_API_KEY not set"}
    try:
        req = urllib.request.Request(
            f"https://api.brevo.com/v3/{endpoint}",
            headers={
                "api-key": api_key,
                "Accept": "application/json"
            },
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as he:
        err_body = ""
        try:
            err_body = he.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"error": f"HTTP {he.code}", "detail": err_body}
    except Exception as e:
        return {"error": str(e)}


def test_smtp_diagnostic(to_email: str) -> dict:
    brevo_key = (os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY") or "").strip()
    sender_email = _get_sender_email()

    results = {
        "to_email": to_email,
        "sender_email": sender_email,
        "brevo_api_key_set": bool(brevo_key),
        "brevo_api_key_prefix": brevo_key[:12] + "..." if brevo_key else None,
    }

    if not brevo_key:
        results["error"] = "BREVO_API_KEY missing in environment variables"
        return results

    # 1. Check Brevo account info
    results["account_info"] = _brevo_api_get("account")

    # 2. Check verified senders
    results["senders"] = _brevo_api_get("senders")

    # 3. Try sending a test email and capture full response
    send_result = _send_brevo_api_email(
        to_email,
        "HirePulse Diagnostic Test",
        "<div style='font-family:sans-serif;padding:20px'><h2>Diagnostic Test</h2><p>This is a test email sent from your Render deployment via Brevo API.</p><p>If you see this, email delivery is working!</p></div>",
        text_body="HirePulse Diagnostic Test - If you see this, Brevo email delivery is working!",
    )
    results["send_result"] = send_result
    results["success"] = send_result.get("ok", False)

    # 4. Check recent transactional events for this email
    try:
        results["recent_events"] = _brevo_api_get(f"smtp/statistics/events?limit=5&email={to_email}")
    except Exception:
        results["recent_events"] = "could not fetch"

    return results


def get_email_status_diagnostic(to_email: str = None) -> dict:
    gmail_client_id = os.getenv("GMAIL_CLIENT_ID", "").strip()
    gmail_client_secret = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
    gmail_refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "").strip()
    brevo_key = (os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY") or "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip()

    gmail_configured = bool(gmail_client_id and gmail_client_secret and gmail_refresh_token)
    brevo_configured = bool(brevo_key)
    smtp_configured = bool(smtp_password)

    active_method = "None"
    if gmail_configured:
        active_method = "Gmail API (HTTPS)"
    elif brevo_configured:
        active_method = "Brevo API (HTTPS - Check Spam folder)"
    elif smtp_configured:
        active_method = "Gmail SMTP (Blocked on Render free tier)"

    res = {
        "active_method": active_method,
        "env_vars_check": {
            "GMAIL_CLIENT_ID": f"{gmail_client_id[:12]}..." if gmail_client_id else "NOT SET ❌",
            "GMAIL_CLIENT_SECRET": "SET ✅" if gmail_client_secret else "NOT SET ❌",
            "GMAIL_REFRESH_TOKEN": f"{gmail_refresh_token[:10]}..." if gmail_refresh_token else "NOT SET ❌",
            "BREVO_API_KEY": f"{brevo_key[:10]}..." if brevo_key else "NOT SET ❌",
            "SMTP_PASSWORD": "SET ✅" if smtp_password else "NOT SET ❌",
        },
        "gmail_api_configured": gmail_configured,
        "brevo_api_configured": brevo_configured,
    }

    if gmail_configured:
        token = _get_gmail_access_token()
        res["gmail_token_generated"] = bool(token)
        if not token:
            res["gmail_token_error"] = "Failed to exchange refresh token for access token. Check credentials."

    if to_email:
        res["test_send_target"] = to_email
        send_res = _send_smtp_email(to_email, "HirePulse OTP Test", "Your test OTP is 123456", "<div style='font-family:sans-serif;padding:20px'><h2>HirePulse Test</h2><p>Your verification code is <strong>123456</strong>.</p></div>")
        res["test_send_success"] = send_res

    return res



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
    <div style="max-width:500px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#ffffff;color:#111827;padding:32px;border-radius:12px;border:1px solid #e5e7eb;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05)">
        <h2 style="color:#111827;margin-top:0;font-size:1.4rem;font-weight:700">Verify Your HirePulse Account</h2>
        <p style="color:#4b5563;font-size:0.95rem;line-height:1.5">Use the following 6-digit verification code to complete your registration:</p>
        <div style="font-size:2.2rem;font-weight:800;letter-spacing:8px;color:#2563eb;background:#eff6ff;border:1px solid #bfdbfe;padding:16px;text-align:center;border-radius:8px;margin:24px 0">
            {otp_code}
        </div>
        <p style="color:#6b7280;font-size:0.85rem;margin-bottom:0">This code will expire in 10 minutes. If you did not request this verification, please ignore this email.</p>
    </div>
    """
    return _send_smtp_email(to_email, f"Your HirePulse verification code is {otp_code}", text_body, html_body, sender_name="HirePulse AI")


def send_password_reset_otp_email(to_email, otp_code):
    text_body = f"Your HirePulse password reset code is: {otp_code}\n\nThis code will expire in 10 minutes."
    html_body = f"""
    <div style="max-width:500px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#ffffff;color:#111827;padding:32px;border-radius:12px;border:1px solid #e5e7eb;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05)">
        <h2 style="color:#111827;margin-top:0;font-size:1.4rem;font-weight:700">Reset Your HirePulse Password</h2>
        <p style="color:#4b5563;font-size:0.95rem;line-height:1.5">Use the following 6-digit verification code to reset your password and verify your identity:</p>
        <div style="font-size:2.2rem;font-weight:800;letter-spacing:8px;color:#dc2626;background:#fef2f2;border:1px solid #fecaca;padding:16px;text-align:center;border-radius:8px;margin:24px 0">
            {otp_code}
        </div>
        <p style="color:#6b7280;font-size:0.85rem;margin-bottom:0">This code will expire in 10 minutes. If you did not request a password reset, please ignore this email.</p>
    </div>
    """
    return _send_smtp_email(to_email, f"Your HirePulse password reset code is {otp_code}", text_body, html_body, sender_name="HirePulse Security")





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
