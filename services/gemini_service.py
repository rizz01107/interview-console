import os
import json
import re
import google.generativeai as genai

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_configured = False


def _ensure_configured():
    global _configured
    if _configured:
        return
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add it to your .env file (see .env.example), "
            "then restart the app."
        )
    genai.configure(api_key=api_key)
    _configured = True


def _get_model():
    _ensure_configured()
    return genai.GenerativeModel(MODEL_NAME)


def _generate(model, prompt):
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        msg = str(e)
        if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
            raise RuntimeError(
                f"Gemini rate limit / quota hit for model '{MODEL_NAME}'. "
                "Wait a minute and try again, or set GEMINI_MODEL=gemini-2.5-flash-lite "
                "in your .env for a higher free-tier quota."
            )
        if "404" in msg or "not found" in msg.lower():
            raise RuntimeError(
                f"Model '{MODEL_NAME}' isn't available on your account. "
                "Try setting GEMINI_MODEL=gemini-2.5-flash in your .env."
            )
        raise RuntimeError(f"Gemini request failed: {msg}")


def _extract_json(raw_text):
    """Gemini sometimes wraps JSON in markdown fences or adds preamble text."""
    text = raw_text.strip()
    text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text.strip()).strip()
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        text = match.group(1)
    return json.loads(text)


def analyze_resume(resume_text, target_role):
    model = _get_model()
    prompt = f"""You are an expert technical recruiter analyzing a resume for a candidate
applying to: "{target_role}".

Resume text:
---
{resume_text[:6000]}
---

Return ONLY a JSON object (no markdown fences, no preamble) with this exact shape:
{{
  "name": "candidate's name if found, else 'Candidate'",
  "skills": ["skill1", "skill2", "..."],
  "experience_summary": "2-3 sentence summary of work/internship experience",
  "projects_summary": "2-3 sentence summary of key projects, naming them",
  "seniority_level": "fresher | junior | mid | senior"
}}"""
    response_text = _generate(model, prompt)
    return _extract_json(response_text)


def generate_questions(candidate_profile, session_type, target_role, num_questions=6):
    """session_type: 'behavioral' or 'technical'"""
    skills = candidate_profile.get("skills", [])
    experience = candidate_profile.get("experience_summary", "")
    projects = candidate_profile.get("projects_summary", "")

    if session_type == "technical":
        focus = """Generate a mix of:
- Data Structures & Algorithms questions (conceptual or problem-statement style, no need for runnable code)
- Machine Learning / AI concept questions directly relevant to the candidate's listed skills
- At least one question that references one of the candidate's actual projects by name and probes their technical decisions in it"""
    else:
        focus = """Generate a mix of:
- Classic behavioral questions (teamwork, conflict, failure, leadership, time management)
- At least two questions that reference the candidate's actual projects or experience by name
- One question about why they want this specific role"""

    prompt = f"""You are a senior interview panelist preparing interview questions for a candidate
applying to: "{target_role}".

Candidate skills: {", ".join(skills) if skills else "Not specified"}
Candidate experience: {experience or "Not specified"}
Candidate projects: {projects or "Not specified"}

{focus}

Generate exactly {num_questions} questions. Return ONLY a JSON array (no markdown fences, no preamble),
each item shaped as:
{{"category": "behavioral|dsa|ml_concept|project", "question_text": "the question"}}"""

    model = _get_model()
    response_text = _generate(model, prompt)
    return _extract_json(response_text)


def evaluate_answer(question_text, answer_text, category, target_role):
    prompt = f"""You are an expert interview coach evaluating a candidate's spoken/written answer
during a mock interview for: "{target_role}".

Question ({category}): {question_text}

Candidate's answer:
---
{answer_text[:3000] if answer_text.strip() else "(No answer was given)"}
---

Evaluate honestly but constructively. Return ONLY a JSON object (no markdown fences, no preamble):
{{
  "score": <integer 1-10>,
  "strengths": ["short point", "short point"],
  "improvements": ["short actionable point", "short actionable point"],
  "ideal_answer_points": ["key point a strong answer would cover", "..."]
}}"""
    model = _get_model()
    response_text = _generate(model, prompt)
    return _extract_json(response_text)


def generate_overall_feedback(session_type, target_role, qa_pairs):
    """qa_pairs: list of dicts with question_text, score, category"""
    lines = []
    for qa in qa_pairs:
        lines.append(f"- [{qa.get('category')}] Score {qa.get('score')}/10: {qa.get('question_text')}")
    summary_block = "\n".join(lines)

    prompt = f"""You are an interview coach. A candidate just completed a {session_type} mock interview
for "{target_role}". Here is the per-question breakdown:

{summary_block}

Write a short overall performance summary (4-6 sentences) in a direct, encouraging but honest tone.
Mention 1-2 clear strength patterns and 1-2 clear areas to improve before the real interview.
Return ONLY plain text, no JSON, no markdown headers."""
    model = _get_model()
    response_text = _generate(model, prompt)
    return response_text.strip()
