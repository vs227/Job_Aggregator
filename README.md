# HirePulse Pivot AI

A job aggregator and AI career assistant that matches user resumes with job listings using Google Gemini and vector search.

## 🚀 Features

*   **Job Scraper**: Automatically imports job postings from the Adzuna API.
*   **Resume Analysis**: Upload PDF/DOCX resumes for skill gap analysis and fit scoring.
*   **AI Chat**: Talk directly to the AI about jobs that match your profile.
*   **Job Alerts**: Set custom search filters to receive automated email notifications.
*   **Modern Frontend**: Responsive glassmorphic UI with light and dark mode toggles.

## ⚙️ Quick Start

### 1. Configure Environments

Create a `.env` in the root folder:
```env
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key
JWT_SECRET=your-jwt-secret
JWT_ALGORITHM=HS256
GEMINI_API_KEY=your-gemini-key
RESEND_API_KEY=your-resend-key
ADZUNA_APP_ID=your-adzuna-id
ADZUNA_APP_KEY=your-adzuna-key
