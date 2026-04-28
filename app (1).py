import json
import os
import re
from datetime import datetime
from typing import Any

import streamlit as st
from openai import OpenAI

from db import (
    create_user,
    delete_exam,
    get_exam,
    init_db,
    list_exams,
    save_exam,
    update_user_theme,
    user_stats,
    verify_user,
)
from theme import theme_css

MODEL = "gpt-4o-mini"

client = OpenAI(
    api_key=os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"],
)

init_db()


# ---------------- Helpers ----------------

def _extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start_obj = text.find("{")
    start_arr = text.find("[")
    candidates = [i for i in (start_obj, start_arr) if i != -1]
    if candidates:
        text = text[min(candidates):]
    return json.loads(text)


def suggest_title(source_text: str) -> str:
    snippet = source_text.strip().splitlines()
    first = next((s for s in snippet if s.strip()), "Untitled exam").strip()
    first = re.sub(r"\s+", " ", first)
    if len(first) > 60:
        first = first[:57].rstrip() + "..."
    return first or "Untitled exam"


def _normalize_question(q: dict) -> dict | None:
    if not isinstance(q, dict):
        return None
    question = str(q.get("question", "")).strip()
    model_answer = str(q.get("model_answer", "")).strip()
    if not question or not model_answer:
        return None
    qtype = str(q.get("type", "open")).lower().strip()
    if qtype not in ("open", "mc"):
        qtype = "open"
    key_points = q.get("key_points", []) or []
    if isinstance(key_points, str):
        key_points = [key_points]
    key_points = [str(k).strip() for k in key_points if str(k).strip()]
    out = {
        "question": question,
        "type": qtype,
        "model_answer": model_answer,
        "key_points": key_points,
    }
    if qtype == "mc":
        choices = q.get("choices", []) or []
        if not isinstance(choices, list):
            return None
        choices = [str(c).strip() for c in choices if str(c).strip()]
        if len(choices) < 3:
            return None
        try:
            correct_idx = int(q.get("correct_choice", -1))
        except (TypeError, ValueError):
            return None
        if not 0 <= correct_idx < len(choices):
            return None
        out["choices"] = choices
        out["correct_choice"] = correct_idx
    return out


# ---------------- AI calls ----------------

def _is_topic_only(source_text: str) -> bool:
    """A short, heading-style input (no full paragraph) is treated as a topic prompt."""
    text = source_text.strip()
    if len(text) < 200 and "\n\n" not in text and len(text.split()) <= 25:
        return True
    return False


def generate_questions(
    source_text: str,
    num_questions: int,
    difficulty: str,
    include_mc: bool,
) -> list[dict]:
    if include_mc:
        format_block = (
            "Mix question types: roughly half should be open-response and half should be "
            "multiple choice (4 plausible options each, exactly one correct). For each item, "
            "include a `type` field of either 'open' or 'mc'.\n"
            "- For OPEN questions, return: question, type='open', model_answer (2-4 sentences), "
            "key_points (2-4 strings).\n"
            "- For MC questions, return: question, type='mc', choices (array of 4 strings), "
            "correct_choice (zero-based index of the correct choice), model_answer (1-2 "
            "sentences explaining why the correct choice is right), key_points (1-3 strings)."
        )
    else:
        format_block = (
            "All questions must be open-response (no multiple choice). For each, return: "
            "question, type='open', model_answer (2-4 sentences), key_points (2-4 strings)."
        )

    system = (
        "You are an expert exam writer. You write exam-style questions that test true "
        "understanding of a subject. Avoid trivia and yes/no questions. Each question "
        "should require the student to explain, compare, apply, or analyze a concept. "
        "Multiple-choice options must be plausible — no obviously-wrong distractors. "
        "Do NOT include the answer in the question."
    )

    if _is_topic_only(source_text):
        source_block = (
            f"The student gave only a TOPIC HEADING (no full study text). Use your own "
            f"general knowledge of this topic to write a fair, well-rounded exam that covers "
            f"the most important sub-topics a student studying this subject would be expected "
            f"to know. Stay accurate and avoid niche trivia.\n\n"
            f"TOPIC: \"\"\"\n{source_text}\n\"\"\""
        )
    else:
        source_block = (
            f"Base the questions ONLY on the study material below.\n\n"
            f"STUDY MATERIAL:\n\"\"\"\n{source_text}\n\"\"\""
        )

    user = (
        f"Create exactly {num_questions} {difficulty.lower()}-difficulty exam questions.\n\n"
        f"{source_block}\n\n{format_block}\n\n"
        f"Return ONLY valid JSON in this exact shape:\n"
        f'{{"questions": [{{"question": "...", "type": "open", "model_answer": "...", '
        f'"key_points": ["..."]}}]}}'
    )
    return _call_question_generator(system, user)


def generate_weakness_questions(
    source_text: str,
    weak_items: list[dict],
    memo: str,
    num_questions: int,
    difficulty: str,
    include_mc: bool,
) -> list[dict]:
    """Generate a fresh, targeted test focused on the user's weak areas."""
    system = (
        "You are an expert exam writer who creates targeted remediation tests. "
        "Given a student's previous mistakes, you write NEW exam-style questions that "
        "drill the same underlying concepts from a different angle. Do NOT repeat the "
        "previous questions verbatim. Avoid trivia and yes/no questions. Multiple-choice "
        "options must be plausible — no obviously-wrong distractors."
    )
    if include_mc:
        format_block = (
            "Mix question types: roughly half open-response and half multiple choice "
            "(4 plausible options each, exactly one correct). Use a `type` field of "
            "'open' or 'mc' on each item, and include `choices` + `correct_choice` for MC."
        )
    else:
        format_block = "All questions must be open-response (type='open')."

    weak_payload = [
        {
            "question": w["question"],
            "type": w.get("type", "open"),
            "model_answer": w["model_answer"],
            "key_points": w.get("key_points", []),
            "student_answer": w.get("student_answer", ""),
            "feedback": w.get("feedback", ""),
        }
        for w in weak_items
    ]
    user = (
        f"Create exactly {num_questions} {difficulty.lower()}-difficulty exam questions that "
        f"target the WEAK AREAS shown below. The questions must come from the same study "
        f"material but approach the weak concepts from new angles so the student actually "
        f"has to think.\n\n{format_block}\n\n"
        f"Provide a model_answer (2-4 sentences for open; 1-2 for mc) and key_points (1-3) "
        f"for each item.\n\n"
        f"Return ONLY valid JSON in this exact shape:\n"
        f'{{"questions": [{{"question": "...", "type": "open", "model_answer": "...", '
        f'"key_points": ["..."]}}]}}\n\n'
        f"STUDY MEMO FROM LAST TEST:\n\"\"\"\n{memo}\n\"\"\"\n\n"
        f"WEAK QUESTIONS FROM LAST TEST:\n{json.dumps(weak_payload, ensure_ascii=False)}\n\n"
        f"FULL STUDY MATERIAL:\n\"\"\"\n{source_text}\n\"\"\""
    )
    return _call_question_generator(system, user)


def _call_question_generator(system: str, user: str) -> list[dict]:
    resp = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=8192,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    data = _extract_json(content)
    raw = data.get("questions", []) or []
    cleaned = []
    for q in raw:
        norm = _normalize_question(q)
        if norm:
            cleaned.append(norm)
    return cleaned


def grade_test(source_text: str, items: list[dict]) -> dict:
    system = (
        "You are a fair, encouraging exam grader. For OPEN-RESPONSE questions you judge "
        "whether the student communicates the central concept correctly, NOT word-for-word "
        "matching, and award partial credit when part of the idea is right. For MULTIPLE "
        "CHOICE questions, score 10 if their selected choice index equals correct_choice, "
        "otherwise 0; the feedback should state which choice they selected and which one "
        "was correct. Be specific. Never reward made-up facts."
    )
    payload = {
        "study_material": source_text,
        "questions": [
            {
                "n": i + 1,
                "question": it["question"],
                "type": it.get("type", "open"),
                "model_answer": it["model_answer"],
                "key_points": it.get("key_points", []),
                "choices": it.get("choices"),
                "correct_choice": it.get("correct_choice"),
                "student_answer": it["student_answer"],
                "student_choice": it.get("student_choice"),
            }
            for i, it in enumerate(items)
        ],
    }
    user = (
        "Grade each student answer below. For EACH question, return:\n"
        "- score: integer 0-10 (MC: 10 if correct, 0 if wrong/blank; open: partial credit allowed)\n"
        "- verdict: one of 'correct', 'partial', 'incorrect'\n"
        "- feedback: 1-2 sentences on what was right and what was missing or wrong\n\n"
        "Then write an overall study memo addressed directly to the student ('You ...'). "
        "The memo should: (1) acknowledge what they understand well, (2) call out their "
        "specific mistakes by topic, (3) recommend 3-5 concrete topics or concepts to review "
        "from the study material, (4) end with one motivating sentence. Keep the memo under "
        "250 words.\n\n"
        "Return ONLY valid JSON of this exact shape:\n"
        '{"results": [{"n": 1, "score": 0, "verdict": "...", "feedback": "..."}], '
        '"memo": "..."}\n\n'
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    resp = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=8192,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    return _extract_json(content)


def collect_weak_items(questions: list[dict], answers: dict, graded: dict) -> list[dict]:
    results = graded.get("results", []) or []
    by_n = {int(r.get("n", 0)): r for r in results if isinstance(r, dict)}
    weak = []
    for i, q in enumerate(questions):
        r = by_n.get(i + 1, {})
        verdict = str(r.get("verdict", "")).lower()
        score = int(r.get("score", 0) or 0)
        if verdict in ("partial", "incorrect") or score < 7:
            weak.append({
                **q,
                "student_answer": answers.get(i, "") if isinstance(answers, dict) else "",
                "feedback": r.get("feedback", ""),
                "score": score,
                "verdict": verdict,
            })
    return weak


# ---------------- State ----------------

def init_state():
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("page", "home")
    st.session_state.setdefault("stage", "input")
    st.session_state.setdefault("source_text", "")
    st.session_state.setdefault("num_questions", 5)
    st.session_state.setdefault("difficulty", "Medium")
    st.session_state.setdefault("include_mc", False)
    st.session_state.setdefault("title", "")
    st.session_state.setdefault("questions", [])
    st.session_state.setdefault("answers", {})
    st.session_state.setdefault("graded", None)
    st.session_state.setdefault("viewing_exam_id", None)
    st.session_state.setdefault("saved_exam_id", None)
    st.session_state.setdefault("retake_target", None)
    st.session_state.setdefault("has_reviewed", False)


def reset_exam_state():
    st.session_state.stage = "input"
    st.session_state.source_text = ""
    st.session_state.title = ""
    st.session_state.num_questions = 5
    st.session_state.difficulty = "Medium"
    st.session_state.include_mc = False
    st.session_state.questions = []
    st.session_state.answers = {}
    st.session_state.graded = None
    st.session_state.saved_exam_id = None
    st.session_state.has_reviewed = False


def current_theme() -> str:
    user = st.session_state.user
    if user and user.get("theme") in ("light", "dark"):
        return user["theme"]
    return "dark"


def compute_score(questions: list[dict], graded: dict) -> tuple[int, int, int]:
    results = (graded or {}).get("results", []) or []
    by_n = {int(r.get("n", 0)): r for r in results if isinstance(r, dict)}
    total = sum(int(by_n.get(i + 1, {}).get("score", 0) or 0) for i in range(len(questions)))
    max_score = len(questions) * 10
    pct = round((total / max_score) * 100) if max_score else 0
    return total, max_score, pct


# ---------------- UI sections ----------------

def render_brand():
    st.markdown(
        """
        <div class="ec-brand-wrap">
            <div class="ec-brand-left">
                <div class="ec-brand-mark">EC</div>
                <div class="ec-brand-text">
                    <div class="ec-brand-title">Exam Create</div>
                    <div class="ec-brand-tagline">Study · Practice · Master</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_auth():
    render_brand()
    st.subheader("Sign in to start creating exams")

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])
    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Email", key="login_email", placeholder="you@example.com")
            p = st.text_input("Password", type="password", key="login_pw")
            submitted = st.form_submit_button("Log in", type="primary")
            if submitted:
                user = verify_user(u, p)
                if user:
                    st.session_state.user = user
                    st.session_state.page = "home"
                    st.rerun()
                else:
                    st.error("Incorrect email or password.")

    with tab_signup:
        with st.form("signup_form"):
            u = st.text_input("Email", key="signup_email", placeholder="you@example.com")
            p = st.text_input("Choose a password", type="password", key="signup_pw")
            submitted = st.form_submit_button("Create account", type="primary")
            if submitted:
                ok, msg = create_user(u, p)
                if ok:
                    user = verify_user(u, p)
                    st.session_state.user = user
                    st.session_state.page = "home"
                    st.success("Account created. Welcome!")
                    st.rerun()
                else:
                    st.error(msg)


def render_sidebar():
    user = st.session_state.user
    with st.sidebar:
        st.markdown(f"**Signed in as** `{user.get('email', user.get('username', ''))}`")
        st.markdown("**Appearance**")
        current = current_theme()
        choice = st.radio(
            "Theme",
            ["Light", "Dark"],
            index=0 if current == "light" else 1,
            horizontal=True,
            label_visibility="collapsed",
            key="theme_radio",
        )
        new_theme = "light" if choice == "Light" else "dark"
        if new_theme != current:
            st.session_state.user["theme"] = new_theme
            update_user_theme(user["id"], new_theme)
            st.rerun()
        st.divider()
        if st.button("Log out", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def render_progress_panel():
    stats = user_stats(st.session_state.user["id"])

    def stat(label: str, value: str, sub: str = "") -> str:
        sub_html = f'<div class="ec-stat-sub">{sub}</div>' if sub else ""
        return (
            f'<div class="ec-stat">'
            f'<div class="ec-stat-label">{label}</div>'
            f'<div class="ec-stat-value">{value}</div>{sub_html}'
            f'</div>'
        )

    avg = "—" if stats["average_score"] is None else f'{stats["average_score"]}%'
    best = "—" if stats["best_score"] is None else f'{stats["best_score"]}%'

    grid = (
        '<div class="ec-stat-grid">'
        + stat("Tests taken", str(stats["total_tests"]),
               f'{stats["tests_today"]} today · {stats["tests_this_week"]} this week')
        + stat("Average score", avg, f'Best: {best}')
        + stat("Daily average", f'{stats["daily_average"]}',
               'tests / day since first test')
        + stat("Weekly average", f'{stats["weekly_average"]}',
               'tests / week since first test')
        + '</div>'
    )
    st.markdown("### Your progress")
    st.markdown(grid, unsafe_allow_html=True)


def render_home():
    render_progress_panel()

    if st.session_state.retake_target is not None:
        target = st.session_state.retake_target
        st.success(
            f"Loaded a fresh test targeting your weak areas from "
            f"**{target.get('source_title', 'your last exam')}**."
        )

    st.subheader("New exam")
    st.write(
        "Paste any study material below — class notes, an article, a textbook chapter — "
        "**or just a topic heading** like *History of WW2* or *Photosynthesis* and a test "
        "will be built from general knowledge of that subject. Answer each question in your "
        "own words; you don't need to match the wording exactly, just get the central idea "
        "across."
    )

    st.session_state.source_text = st.text_area(
        "Study material or topic",
        value=st.session_state.source_text,
        height=260,
        placeholder=(
            "Paste your notes or article — or just type a topic like "
            "'History of WW2' or 'Photosynthesis'..."
        ),
    )

    st.session_state.title = st.text_input(
        "Exam title (optional)",
        value=st.session_state.title,
        placeholder="e.g. Chapter 4 — Cellular Respiration",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.session_state.num_questions = st.slider(
            "Number of questions", 3, 15, value=st.session_state.num_questions
        )
    with col2:
        st.session_state.difficulty = st.selectbox(
            "Difficulty",
            ["Easy", "Medium", "Hard"],
            index=["Easy", "Medium", "Hard"].index(st.session_state.difficulty),
        )

    st.session_state.include_mc = st.checkbox(
        "Include multiple-choice questions",
        value=st.session_state.include_mc,
        help="When enabled, roughly half of the questions will be multiple choice.",
    )

    disabled = len(st.session_state.source_text.strip()) < 3
    if disabled:
        st.caption("Enter a topic heading or paste study material to begin.")

    if st.button("Generate test", type="primary", disabled=disabled):
        with st.spinner("Writing your exam..."):
            try:
                qs = generate_questions(
                    st.session_state.source_text,
                    st.session_state.num_questions,
                    st.session_state.difficulty,
                    st.session_state.include_mc,
                )
            except Exception as e:
                st.error(f"Couldn't generate the test: {e}")
                return
        if not qs:
            st.error("No questions were generated. Try adding more material or different content.")
            return
        st.session_state.questions = qs
        st.session_state.answers = {i: "" for i in range(len(qs))}
        if not st.session_state.title.strip():
            st.session_state.title = suggest_title(st.session_state.source_text)
        st.session_state.stage = "test"
        st.session_state.has_reviewed = False
        st.session_state.retake_target = None
        st.rerun()


def render_test():
    st.subheader(st.session_state.title or "Your test")
    type_summary = ""
    mc_count = sum(1 for q in st.session_state.questions if q.get("type") == "mc")
    if mc_count:
        type_summary = f" · {mc_count} multiple-choice"
    st.caption(
        f"{len(st.session_state.questions)} questions · "
        f"{st.session_state.difficulty} difficulty{type_summary}"
    )
    st.info(
        "Answer each question in your own words for open responses, or pick the best option "
        "for multiple choice. You don't need to match wording word-for-word — just get the "
        "central idea across."
    )

    for i, q in enumerate(st.session_state.questions):
        st.markdown(f"**Question {i + 1}.** {q['question']}")
        if q.get("type") == "mc":
            choices = q.get("choices", [])
            options = ["— Select an answer —"] + list(choices)
            current = st.session_state.answers.get(i, "")
            try:
                current_idx = options.index(current) if current in options else 0
            except ValueError:
                current_idx = 0
            picked = st.radio(
                label=f"Your answer to question {i + 1}",
                options=options,
                index=current_idx,
                key=f"mc_answer_{i}",
                label_visibility="collapsed",
            )
            st.session_state.answers[i] = "" if picked == options[0] else picked
        else:
            st.session_state.answers[i] = st.text_area(
                label=f"Your answer to question {i + 1}",
                value=st.session_state.answers.get(i, ""),
                key=f"answer_{i}",
                height=120,
                label_visibility="collapsed",
                placeholder="Type your answer here...",
            )
        st.divider()

    answered = sum(1 for v in st.session_state.answers.values() if v and str(v).strip())
    total = len(st.session_state.questions)
    st.caption(f"Answered: {answered} / {total}")

    if st.button("Submit for grading", type="primary", disabled=answered == 0):
        items = []
        for i, q in enumerate(st.session_state.questions):
            ans = st.session_state.answers.get(i, "")
            ans_str = str(ans).strip() if ans else ""
            student_choice = None
            if q.get("type") == "mc":
                try:
                    student_choice = q["choices"].index(ans_str) if ans_str else None
                except ValueError:
                    student_choice = None
            items.append({**q, "student_answer": ans_str, "student_choice": student_choice})

        with st.spinner("Grading your test and writing your memo..."):
            try:
                graded = grade_test(st.session_state.source_text, items)
            except Exception as e:
                st.error(f"Grading failed: {e}")
                return

        st.session_state.graded = graded
        total_score, max_score, _ = compute_score(st.session_state.questions, graded)
        try:
            exam_id = save_exam(
                user_id=st.session_state.user["id"],
                title=st.session_state.title or suggest_title(st.session_state.source_text),
                difficulty=st.session_state.difficulty,
                source_text=st.session_state.source_text,
                questions=st.session_state.questions,
                answers=st.session_state.answers,
                graded=graded,
                total_score=total_score,
                max_score=max_score,
            )
            st.session_state.saved_exam_id = exam_id
        except Exception as e:
            st.warning(f"Results computed, but couldn't save to history: {e}")

        st.session_state.stage = "completed"
        st.session_state.has_reviewed = False
        st.rerun()


def render_completed():
    st.subheader("Test submitted")
    st.caption(st.session_state.title or "")

    total, max_score, pct = compute_score(
        st.session_state.questions, st.session_state.graded or {}
    )
    st.metric("Overall score", f"{total} / {max_score}", f"{pct}%")
    st.progress(pct / 100 if max_score else 0)

    st.write("What would you like to do next?")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Review", type="primary", use_container_width=True):
            st.session_state.has_reviewed = True
            st.session_state.stage = "review"
            st.rerun()
    with col2:
        if st.button("Home", use_container_width=True):
            reset_exam_state()
            st.session_state.page = "home"
            st.rerun()
    with col3:
        if st.button("Retake Test", use_container_width=True):
            st.session_state.answers = {i: "" for i in range(len(st.session_state.questions))}
            st.session_state.graded = None
            st.session_state.saved_exam_id = None
            st.session_state.has_reviewed = False
            st.session_state.stage = "test"
            st.rerun()


def render_results_view(
    title: str,
    difficulty: str,
    questions: list[dict],
    answers: dict,
    graded: dict,
    created_at: str | None = None,
):
    st.subheader(title)
    meta = f"{len(questions)} questions · {difficulty} difficulty"
    if created_at:
        try:
            ts = datetime.fromisoformat(created_at).strftime("%b %d, %Y · %I:%M %p UTC")
            meta += f" · {ts}"
        except ValueError:
            pass
    st.caption(meta)

    results = graded.get("results", []) or []
    memo = graded.get("memo", "") or ""
    by_n = {int(r.get("n", 0)): r for r in results if isinstance(r, dict)}

    total, max_score, pct = compute_score(questions, graded)
    st.metric("Overall score", f"{total} / {max_score}", f"{pct}%")
    st.progress(pct / 100 if max_score else 0)

    st.markdown("### Memo")
    st.markdown(memo or "_No memo available._")

    st.markdown("### Question-by-question feedback")
    for i, q in enumerate(questions):
        r = by_n.get(i + 1, {})
        score = int(r.get("score", 0) or 0)
        verdict = str(r.get("verdict", "")).lower()
        feedback = r.get("feedback", "")
        if verdict == "correct":
            badge = "Correct"
        elif verdict == "partial":
            badge = "Partial credit"
        else:
            badge = "Incorrect"
        type_tag = " · MC" if q.get("type") == "mc" else ""
        with st.expander(f"Q{i + 1} — {badge} ({score}/10){type_tag}", expanded=verdict != "correct"):
            st.markdown(f"**Question:** {q['question']}")
            user_ans = answers.get(i, "") if isinstance(answers, dict) else ""
            st.markdown(f"**Your answer:** {str(user_ans).strip() if user_ans else '_(blank)_'}")
            if q.get("type") == "mc" and isinstance(q.get("choices"), list):
                correct_idx = q.get("correct_choice")
                if isinstance(correct_idx, int) and 0 <= correct_idx < len(q["choices"]):
                    st.markdown(f"**Correct choice:** {q['choices'][correct_idx]}")
            st.markdown(f"**Feedback:** {feedback}")
            with st.popover("Show model answer"):
                st.markdown(q["model_answer"])
                if q.get("key_points"):
                    st.markdown("**Key points:**")
                    for kp in q["key_points"]:
                        st.markdown(f"- {kp}")


def start_weakness_retake(
    source_text: str,
    title: str,
    difficulty: str,
    questions: list[dict],
    answers: dict,
    graded: dict,
    include_mc: bool,
):
    weak = collect_weak_items(questions, answers, graded)
    if not weak:
        st.info("Nice work — you don't have any weak areas to retake from this test.")
        return False
    memo = (graded or {}).get("memo", "") or ""
    target_count = max(3, min(len(weak) + 2, 10))
    with st.spinner("Building a fresh test on your weak areas..."):
        try:
            new_qs = generate_weakness_questions(
                source_text=source_text,
                weak_items=weak,
                memo=memo,
                num_questions=target_count,
                difficulty=difficulty,
                include_mc=include_mc,
            )
        except Exception as e:
            st.error(f"Couldn't build the targeted test: {e}")
            return False
    if not new_qs:
        st.error("Couldn't build a targeted test from those weak areas. Try again.")
        return False

    st.session_state.source_text = source_text
    st.session_state.title = f"Weak-areas retake — {title}"
    st.session_state.difficulty = difficulty
    st.session_state.include_mc = include_mc
    st.session_state.num_questions = len(new_qs)
    st.session_state.questions = new_qs
    st.session_state.answers = {i: "" for i in range(len(new_qs))}
    st.session_state.graded = None
    st.session_state.saved_exam_id = None
    st.session_state.has_reviewed = False
    st.session_state.stage = "test"
    st.session_state.page = "home"
    st.session_state.viewing_exam_id = None
    st.session_state.retake_target = {"source_title": title}
    return True


def render_review():
    render_results_view(
        title=st.session_state.title or "Review",
        difficulty=st.session_state.difficulty,
        questions=st.session_state.questions,
        answers=st.session_state.answers,
        graded=st.session_state.graded or {},
    )

    st.divider()
    st.markdown("### What's next?")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Practice my weak areas", type="primary", use_container_width=True):
            ok = start_weakness_retake(
                source_text=st.session_state.source_text,
                title=st.session_state.title or "Untitled",
                difficulty=st.session_state.difficulty,
                questions=st.session_state.questions,
                answers=st.session_state.answers,
                graded=st.session_state.graded or {},
                include_mc=st.session_state.include_mc,
            )
            if ok:
                st.rerun()
    with col2:
        if st.button("Retake Test", use_container_width=True):
            st.session_state.answers = {i: "" for i in range(len(st.session_state.questions))}
            st.session_state.graded = None
            st.session_state.saved_exam_id = None
            st.session_state.has_reviewed = False
            st.session_state.stage = "test"
            st.rerun()
    with col3:
        if st.button("Home", use_container_width=True):
            reset_exam_state()
            st.session_state.page = "home"
            st.rerun()


def render_history():
    st.subheader("Your exam history")
    user = st.session_state.user

    if st.session_state.viewing_exam_id is not None:
        exam = get_exam(user["id"], st.session_state.viewing_exam_id)
        if not exam:
            st.warning("That exam couldn't be found.")
            st.session_state.viewing_exam_id = None
            st.rerun()
            return
        if st.button("← Back to history"):
            st.session_state.viewing_exam_id = None
            st.rerun()
        render_results_view(
            title=exam["title"],
            difficulty=exam["difficulty"],
            questions=exam["questions"],
            answers=exam["answers"],
            graded=exam["graded"],
            created_at=exam["created_at"],
        )
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Practice these weak areas", type="primary", use_container_width=True):
                exam_has_mc = any(q.get("type") == "mc" for q in exam["questions"])
                ok = start_weakness_retake(
                    source_text=exam["source_text"],
                    title=exam["title"],
                    difficulty=exam["difficulty"],
                    questions=exam["questions"],
                    answers=exam["answers"],
                    graded=exam["graded"],
                    include_mc=exam_has_mc,
                )
                if ok:
                    st.rerun()
        with col2:
            with st.expander("Show original study material"):
                st.write(exam["source_text"])
        return

    exams = list_exams(user["id"])
    if not exams:
        st.info("You haven't taken any exams yet. Head to the **Home** tab to make one.")
        return

    for exam in exams:
        try:
            ts = datetime.fromisoformat(exam["created_at"]).strftime("%b %d, %Y · %I:%M %p UTC")
        except ValueError:
            ts = exam["created_at"]
        pct = round((exam["total_score"] / exam["max_score"]) * 100) if exam["max_score"] else 0

        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                st.markdown(f"**{exam['title']}**")
                st.caption(f"{ts} · {exam['difficulty']} · {exam['num_questions']} questions")
            with cols[1]:
                st.metric("Score", f"{exam['total_score']}/{exam['max_score']}", f"{pct}%",
                          label_visibility="collapsed")
            with cols[2]:
                if st.button("View", key=f"view_{exam['id']}", use_container_width=True):
                    st.session_state.viewing_exam_id = exam["id"]
                    st.rerun()
            with cols[3]:
                if st.button("Delete", key=f"del_{exam['id']}", use_container_width=True):
                    delete_exam(user["id"], exam["id"])
                    st.rerun()


# ---------------- Routing ----------------

def render_app():
    render_brand()
    render_sidebar()

    # Hide Home/History tabs while the user is actively taking a test.
    show_tabs = st.session_state.stage != "test"
    if show_tabs:
        tab_labels = ["Home", "History"]
        page_to_idx = {"home": 0, "history": 1}
        idx = page_to_idx.get(st.session_state.page, 0)
        selection = st.radio(
            "Navigation",
            tab_labels,
            index=idx,
            horizontal=True,
            label_visibility="collapsed",
        )
        new_page = "home" if selection == "Home" else "history"
        if new_page != st.session_state.page:
            st.session_state.page = new_page
            st.session_state.viewing_exam_id = None
            st.rerun()
        st.write("")

    if st.session_state.page == "home":
        if st.session_state.stage == "input":
            render_home()
        elif st.session_state.stage == "test":
            render_test()
        elif st.session_state.stage == "completed":
            render_completed()
        elif st.session_state.stage == "review":
            render_review()
    else:
        render_history()


def main():
    st.set_page_config(page_title="Exam Create", page_icon="📝", layout="centered")
    init_state()
    st.markdown(theme_css(current_theme()), unsafe_allow_html=True)
    if st.session_state.user is None:
        render_auth()
    else:
        render_app()


if __name__ == "__main__":
    main()
