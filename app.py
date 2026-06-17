import os
import json
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, jsonify, session as flask_session

import database as db
from services import gemini_service
from services.resume_parser import extract_text_from_pdf

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")


@app.context_processor
def inject_gemini_status():
    return {"gemini_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip())}

with app.app_context():
    db.init_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start_session():
    target_role = request.form.get("target_role", "AI/ML Engineer").strip() or "AI/ML Engineer"
    session_type = request.form.get("session_type", "behavioral")
    resume_file = request.files.get("resume_file")
    pasted_text = request.form.get("resume_text", "").strip()

    resume_text = ""
    if resume_file and resume_file.filename.lower().endswith(".pdf"):
        try:
            resume_text = extract_text_from_pdf(resume_file)
        except Exception as e:
            return render_template("index.html", error=f"Could not read PDF: {e}")
    elif pasted_text:
        resume_text = pasted_text

    if not resume_text:
        return render_template("index.html", error="Please upload a PDF resume or paste your resume text.")

    try:
        profile = gemini_service.analyze_resume(resume_text, target_role)
    except Exception as e:
        return render_template("index.html", error=f"Resume analysis failed: {e}")

    candidate_id = db.create_candidate(
        name=profile.get("name", "Candidate"),
        target_role=target_role,
        resume_text=resume_text,
        skills=profile.get("skills", []),
        experience_summary=profile.get("experience_summary", ""),
        projects_summary=profile.get("projects_summary", ""),
    )
    flask_session["candidate_id"] = candidate_id
    flask_session["target_role"] = target_role

    try:
        questions = gemini_service.generate_questions(profile, session_type, target_role)
    except Exception as e:
        return render_template("index.html", error=f"Question generation failed: {e}")

    session_id = db.create_session(candidate_id, session_type)
    db.add_questions(session_id, questions)

    return redirect(url_for("interview", session_id=session_id))


@app.route("/interview/<int:session_id>")
def interview(session_id):
    session_row = db.get_session(session_id)
    if not session_row:
        return redirect(url_for("index"))
    questions = db.get_questions_for_session(session_id)
    questions_json = [
        {"id": q["id"], "question_text": q["question_text"], "category": q["category"], "order_index": q["order_index"]}
        for q in questions
    ]
    return render_template(
        "interview.html",
        session=session_row,
        questions_json=json.dumps(questions_json),
        target_role=flask_session.get("target_role", "AI/ML Engineer"),
    )


@app.route("/api/answer", methods=["POST"])
def api_answer():
    data = request.get_json(force=True)
    question_id = data.get("question_id")
    answer_text = (data.get("answer_text") or "").strip()

    question = db.get_question(question_id)
    if not question:
        return jsonify({"error": "Question not found"}), 404

    target_role = flask_session.get("target_role", "AI/ML Engineer")

    try:
        evaluation = gemini_service.evaluate_answer(
            question["question_text"], answer_text, question["category"], target_role
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    db.save_answer(
        question_id=question_id,
        answer_text=answer_text,
        score=evaluation.get("score", 0),
        strengths=evaluation.get("strengths", []),
        improvements=evaluation.get("improvements", []),
        ideal_points=evaluation.get("ideal_answer_points", []),
    )

    return jsonify(evaluation)


@app.route("/api/finish/<int:session_id>", methods=["POST"])
def api_finish(session_id):
    session_row = db.get_session(session_id)
    if not session_row:
        return jsonify({"error": "Session not found"}), 404

    qa_rows = db.get_answers_for_session(session_id)
    scored = [r for r in qa_rows if r["score"] is not None]
    overall_score = round(sum(r["score"] for r in scored) / len(scored), 1) if scored else 0

    qa_pairs = [
        {"question_text": r["question_text"], "score": r["score"], "category": r["category"]}
        for r in scored
    ]

    target_role = flask_session.get("target_role", "AI/ML Engineer")
    try:
        overall_feedback = gemini_service.generate_overall_feedback(
            session_row["session_type"], target_role, qa_pairs
        )
    except Exception as e:
        overall_feedback = "Could not generate summary feedback: " + str(e)

    db.complete_session(session_id, overall_score, overall_feedback)
    return jsonify({"redirect": url_for("result", session_id=session_id)})


@app.route("/result/<int:session_id>")
def result(session_id):
    session_row = db.get_session(session_id)
    if not session_row:
        return redirect(url_for("index"))
    qa_rows = db.get_answers_for_session(session_id)
    parsed_rows = []
    for r in qa_rows:
        parsed_rows.append({
            "question_text": r["question_text"],
            "category": r["category"],
            "answer_text": r["answer_text"],
            "score": r["score"],
            "strengths": json.loads(r["strengths"]) if r["strengths"] else [],
            "improvements": json.loads(r["improvements"]) if r["improvements"] else [],
            "ideal_points": json.loads(r["ideal_points"]) if r["ideal_points"] else [],
        })
    return render_template("result.html", session=session_row, qa_rows=parsed_rows)


@app.route("/dashboard")
def dashboard():
    candidate_id = flask_session.get("candidate_id")
    sessions = db.get_all_sessions(candidate_id)
    score_history = db.get_completed_sessions_with_scores(candidate_id)

    chart_labels = [s["completed_at"][:10] for s in score_history]
    chart_scores = [s["overall_score"] for s in score_history]

    behavioral_scores = [s["overall_score"] for s in score_history if s["session_type"] == "behavioral"]
    technical_scores = [s["overall_score"] for s in score_history if s["session_type"] == "technical"]
    avg_behavioral = round(sum(behavioral_scores) / len(behavioral_scores), 1) if behavioral_scores else 0
    avg_technical = round(sum(technical_scores) / len(technical_scores), 1) if technical_scores else 0

    return render_template(
        "dashboard.html",
        sessions=sessions,
        chart_labels=json.dumps(chart_labels),
        chart_scores=json.dumps(chart_scores),
        avg_behavioral=avg_behavioral,
        avg_technical=avg_technical,
        total_sessions=len(sessions),
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
