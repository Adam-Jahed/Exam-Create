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
