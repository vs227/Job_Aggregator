# Job Aggregator

A modern job aggregation portal featuring a FastAPI backend, a React + Vite frontend, Supabase database storage and authentication, AI-powered resume parsing and query matching using Gemini, and automated email notifications via Resend.

---

## Project Structure

* `.github/workflows/scraper.yml` - GitHub Actions workflow to run scrapers on a cron schedule
* `main.py` - FastAPI application exposing backend API endpoints
* `alerts.py` - Job matching engine and Resend email notification service
* `auth.py` - JWT authentication utility configuration
* `database.py` - Supabase client configuration
* `RAG/` - AI-powered resume embedding generation, matching, and chat analysis module
* `scrapers/` - Automated job scrapers and database injection tools
* `frontend/` - React frontend application compiled using Vite

---

## Environment Variables (`.env`)

Create a `.env` file in the root directory:

```env
SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_KEY="your-anon-key"
JWT_SECRET="your-jwt-secret-key"
JWT_ALGORITHM="HS256"
ADZUNA_APP_ID="your-adzuna-app-id"
ADZUNA_APP_KEY="your-adzuna-app-key"
GEMINI_API_KEY="your-gemini-api-key"
RESEND_API_KEY="re_your-resend-api-key"
```

For the frontend, create an `.env` file in the `frontend/` directory:

```env
VITE_API_URL="http://localhost:8000"
```

---

## Setup & Local Running

### Backend

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. Start the FastAPI development server:
   ```bash
   uvicorn main:app --reload
   ```

### Scrapers

To run the job scraper and trigger matches to user alerts manually:
```bash
python scrapers/main.py
```

### Frontend

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Run the development server:
   ```bash
   npm run dev
   ```

---

## Production Deployment (Free Tier)

This project is configured to run fully on free tier services:

1. **Database & Auth (Supabase)**: Permanent free Postgres tier.
2. **Backend API (Render)**: Deploy as a **Web Service** using Python, build command `pip install -r requirements.txt`, and start command `uvicorn main:app --host 0.0.0.0 --port $PORT`. Add the environment variables from the root `.env` to Render.
3. **Frontend Client (Vercel)**: Deploy the `frontend/` subfolder as a static site. Set `VITE_API_URL` to your Render backend domain.
4. **Scraper Cron (GitHub Actions)**: Add your credentials under GitHub **Settings -> Secrets and variables -> Actions** to automatically trigger job collection and email alerts every 4 days.
