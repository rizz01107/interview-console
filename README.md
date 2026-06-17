# Interview Console — AI Interview Prep Agent

A Flask web app that turns your resume into a personalized mock interview. Upload your
resume (PDF or pasted text), pick a target role and round type, and the app uses Gemini
to generate questions based on your actual skills/projects, score your answers live, and
track your progress over time on a dashboard.

## Features

- **Resume-aware questions** — extracts skills, experience, and projects from your resume
  and builds questions around them instead of generic ones.
- **Mock interview console** — one question at a time, terminal-style, with a live score
  gauge after each answer (strengths / improvements / what an ideal answer covers).
- **Behavioral + Technical rounds** — behavioral covers teamwork/conflict/motivation style
  questions; technical mixes DSA concepts, ML concepts, and project-specific deep dives.
- **Dashboard** — score trend chart, behavioral vs technical averages, full session history.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Get a free Gemini API key: https://aistudio.google.com/apikey

3. Copy `.env.example` to `.env` and add your key:
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```
   GEMINI_API_KEY=your_actual_key_here
   FLASK_SECRET_KEY=any_random_string
   ```

4. Run the app:
   ```bash
   python app.py
   ```
   Open http://127.0.0.1:5000

## How it works

1. **New Session** — upload your resume PDF (or paste text), set a target role, choose
   Behavioral or Technical. The app calls Gemini once to extract a structured profile
   (skills/experience/projects), saves it, then calls Gemini again to generate ~6
   personalized questions.
2. **Interview Console** — answer one question at a time. Each submission is scored
   1–10 by Gemini with strengths, improvements, and what a strong answer would cover.
3. **Report** — after the last question, Gemini writes a short overall performance
   summary and the session is saved.
4. **Dashboard** — see your score trend across all sessions, averages by round type,
   and jump back into any past report.

## Project structure

```
app.py                     Flask routes
database.py                SQLite schema + queries
services/gemini_service.py Gemini prompts: resume analysis, question gen, scoring
services/resume_parser.py  PDF text extraction (pdfplumber)
templates/                 Jinja templates
static/css/style.css       Visual design (navy/electric-blue "console" theme)
data/interview_prep.db     SQLite database (created automatically on first run)
```

## Notes

- This is a single-user local app — no login system. Flask session cookie tracks your
  current candidate profile so the dashboard groups your own sessions.
- Each new resume upload creates a fresh candidate profile; old sessions stay linked to
  whichever profile they were created under.
- The technical round evaluates explanations/approach, not by executing code — Gemini
  judges correctness and reasoning from what you type.
