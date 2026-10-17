"""E-Bhai: a voice-first study buddy built on Sarvam AI.
Three tabs share one memory: Check-in (voice friend), Doubt (spoken-reasoning
misconception detector) and Journal (audio memoir).
"""
from __future__ import annotations

import hashlib
import pandas as pd
import streamlit as st

import memory
import sarvam_core

st.set_page_config(page_title="E-Bhai", page_icon="🎙️", layout="centered")

# If the chat API ever rejects the "system" role, set this to False.
USE_SYSTEM_ROLE = True

STYLE = {
    "English": "simple, friendly English",
    "Hindi": "Hindi written in Devanagari script",
    "Hinglish": "casual Hinglish (Hindi and English mixed, written in Roman script)",
}

COURSES = {
    "Abstract Algebra": "Gallian, Contemporary Abstract Algebra",
    "Real Analysis": "Tao, Analysis I",
    "C Programming": "an introductory C programming course",
}

DOUBT_PROMPT = """You are a patient tutor for {course} ({book}). A student has a doubt and explained their own thinking. Find the misconception in their thinking WITHOUT giving the full solution.
Reply with ONLY a JSON object (no other text) with these keys:
"misconception": one sentence naming the wrong belief, or "none found" if their thinking is correct,
"topic": short topic name (2-4 words),
"severity": integer 1-5 (1 = tiny slip, 5 = fundamental gap),
"socratic_hint": a guiding nudge of 2-3 sentences that does NOT reveal the answer,
"analogy": a short real-life or visual analogy,
"practice_question": one short practice question on the same idea.
Write all string values in {style}.
Doubt: {doubt}
Student's thinking: {thinking}"""


# ---------------------------------------------------------------- helpers
def safe(fn, *args, warn: bool = False, **kwargs):
    """Call fn; show a friendly message and return None on any failure."""
    show = st.warning if warn else st.error
    try:
        return fn(*args, **kwargs)
    except sarvam_core.SarvamError as e:
        show(str(e))
    except Exception as e:
        # Print to console for debugging, show generic msg to user
        print(f"Error in {fn.__name__}: {e}")
        show("Something went wrong. Please check your API key and internet connection.")
    return None


def commit(new_mem: dict) -> None:
    """Store memory in session state and persist it to disk (best effort)."""
    st.session_state.mem = new_mem
    try:
        memory.save(new_mem)
    except Exception:
        pass


def new_audio(key: str, clip) -> bytes | None:
    """Return a recording's bytes only the first time we see it."""
    if clip is None:
        return None
    data = clip.getvalue()
    digest = hashlib.md5(data).hexdigest()
    if st.session_state.get(f"seen_{key}") == digest:
        return None
    st.session_state[f"seen_{key}"] = digest
    return data


def transcribe(data: bytes) -> str | None:
    # 'language' and 'lang_code' are global variables defined later in the script
    # This function relies on them being set in the main body
    mode = "codemix" if language == "Hinglish" else "transcribe"
    with st.spinner("Listening..."):
        text = safe(sarvam_core.stt_bytes, data, mode)
        if text is not None and not text.strip():
            st.warning("I couldn't hear anything. Please record again.")
            return None
    return text


def speak(text: str) -> bytes | None:
    with st.spinner("Finding my voice..."):
        return safe(sarvam_core.tts, text, lang_code, speaker, warn=True)


def build_messages(system: str, history: list[dict], user_text: str) -> list[dict]:
    if USE_SYSTEM_ROLE:
        return [{"role": "system", "content": system}, *history,
                {"role": "user", "content": user_text}]
    return [*history, {"role": "user", "content": f"{system}\n\n{user_text}"}]


def ask(prompt: str, spinner: str = "Thinking...") -> str | None:
    with st.spinner(spinner):
        return safe(sarvam_core.chat, [{"role": "user", "content": prompt}])


# ------------------------------------------------------------ app state
try:
    sarvam_core.get_client()
except sarvam_core.SarvamError as e:
    st.error(f"{e}. Set SARVAM_API_KEY as an environment variable or in .streamlit/secrets.toml.")
    st.stop()

if "mem" not in st.session_state:
    st.session_state.mem = memory.load()
st.session_state.setdefault("chat", [])

# ---------------------------------------------------------------- sidebar
st.sidebar.title("E-Bhai")
with st.sidebar.expander("Export / import memory"):
    st.download_button("Export memory", data=memory.export_json(st.session_state.mem),
                       file_name="e-bhai-memory.json", mime="application/json")
    upload = st.file_uploader("Import memory (.json)", type="json")
    if upload is not None and st.button("Import now"):
        try:
            commit(memory.import_json(upload.getvalue().decode("utf-8")))
            st.rerun()
        except UnicodeDecodeError:
            st.error("That file isn't valid text JSON.")

profile = st.session_state.mem["profile"]
langs = list(sarvam_core.LANG_CODES)
saved_lang = profile.get("language", "Hinglish")
name = st.sidebar.text_input("Your name", value=profile.get("name", ""))
language = st.sidebar.selectbox(
    "Language", langs, index=langs.index(saved_lang) if saved_lang in langs else 0)
speaker = st.sidebar.text_input(
    "Voice (speaker)", value="simran_en_customer",
    help="Only simran_en_customer is verified. Check the Bulbul docs for other voices.",
).strip() or "simran_en_customer"
lang_code = sarvam_core.LANG_CODES.get(language, "hi-IN")

if name != profile.get("name", "") or language != saved_lang:
    profile["name"], profile["language"] = name, language
    commit(st.session_state.mem)

st.title("E-Bhai 🎙️")
st.caption("Talk it out. Think out loud. I'll remember.")
tab_checkin, tab_doubt, tab_journal = st.tabs(["Check-in", "Doubt", "Journal"])

# ------------------------------------------------------------ check-in
def checkin_system_prompt() -> str:
    return (
        "You are E-Bhai, a supportive big-brother style study buddy for a college student.  "
        f"Speak in {STYLE.get(language, STYLE['English'])}. Reply in at most 3 short sentences.  "
        "Include exactly one light, friendly joke and one concrete small nudge  "
        "(for example a 10-minute task, water, a break or sleep). Ask at most one question.  "
        "Use the notes below naturally when relevant; never list them or mention that you have notes.  "
        "You are not a doctor and must not diagnose. If the user seems unsafe or in distress,  "
        "gently suggest talking to someone they trust or a helpline.\n\n"
        f"Notes about the user:\n{memory.build_context(st.session_state.mem)}"
    )


def handle_checkin(user_text: str) -> None:
    history = st.session_state.chat[-6:]
    messages = build_messages(checkin_system_prompt(), history, user_text)
    with st.spinner("E-Bhai is thinking..."):
        reply = safe(sarvam_core.chat, messages)
        if not reply:
            return
    st.session_state.chat += [{"role": "user", "content": user_text},
                              {"role": "assistant", "content": reply}]
    st.session_state.ci_audio = speak(reply)

    raw = ask(
        'Read this message from a student. Reply with ONLY JSON like '
        '{"mood": "one word", "summary": "one short sentence"}.\n\nMessage: ' + user_text,
        "Saving your check-in...")
    data = sarvam_core.extract_json(raw or "") or {}
    mood = str(data.get("mood") or "unknown")[:30]
    summary = str(data.get("summary") or user_text)[:200]
    commit(memory.add_checkin(st.session_state.mem, mood, summary))


with tab_checkin:
    clip = st.audio_input("Tap to talk to E-Bhai", key="ci_clip")
    data = new_audio("ci_clip", clip)
    if data:
        heard = transcribe(data)
        if heard:
            handle_checkin(heard)

    with st.form("ci_form", clear_on_submit=True):
        typed = st.text_input("Or type here")
        if st.form_submit_button("Send") and typed.strip():
            handle_checkin(typed.strip())

    for msg in st.session_state.chat[-6:]:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.write(msg["content"])

    if st.session_state.get("ci_audio"):
        st.audio(st.session_state.ci_audio, format="audio/wav")

    if not st.session_state.chat:
        st.info("Say hi! Tell me how your day is going.")

# --------------------------------------------------------------- doubt
def diagnose(course: str, doubt: str, thinking: str) -> None:
    prompt = DOUBT_PROMPT.format(course=course, book=COURSES[course], doubt=doubt,
                                 thinking=thinking, style=STYLE.get(language, STYLE["English"]))
    raw = ask(prompt, "Reading your reasoning...")
    if raw is None:
        return

    data = sarvam_core.extract_json(raw)
    result = {"course": course, "doubt": doubt, "thinking": thinking,
              "data": data, "raw": raw, "full": None, "got_it": False, "audio": None}

    if data:
        try:
            severity = max(1, min(5, int(data.get("severity", 3))))
        except (TypeError, ValueError):
            severity = 3
        data["severity"] = severity

        topic = str(data.get("topic") or course)
        misconception = str(data.get("misconception") or "")
        mem = st.session_state.mem

        if misconception.lower().startswith("none"):
            mem = memory.update_mastery(mem, topic, 5)
        else:
            mem = memory.add_error(mem, course, topic, misconception,
                                   str(data.get("socratic_hint") or ""))
            mem = memory.update_mastery(mem, topic, -4 * severity)
        commit(mem)
        result["audio"] = speak(str(data.get("socratic_hint") or ""))

    st.session_state.doubt_result = result


with tab_doubt:
    course = st.selectbox("Course", list(COURSES))
    doubt = st.text_area("What's your doubt?", key="doubt_text", height=80)
    clip = st.audio_input("Or explain your thinking out loud", key="doubt_clip")
    data = new_audio("doubt_clip", clip)
    if data:
        heard = transcribe(data)
        if heard:
            st.session_state.doubt_thinking = heard

    thinking = st.text_area("Explain YOUR thinking first (why do you believe it works?)",
                            key="doubt_thinking", height=120)

    if st.button("Diagnose my thinking", type="primary"):
        if not doubt.strip() or not thinking.strip():
            st.warning("Add your doubt and your own reasoning first. That's the whole point!")
        else:
            diagnose(course, doubt.strip(), thinking.strip())

    res = st.session_state.get("doubt_result")
    if res:
        d = res["data"]
        if d:
            st.markdown(f"**Topic:** {d.get('topic', '-')}  ·  **Severity:** {d['severity']}/5")
            st.info(f"**Where it slipped:** {d.get('misconception', '')}")
            st.markdown(f"**Hint:** {d.get('socratic_hint', '')}")
            if res.get("audio"):
                st.audio(res["audio"], format="audio/wav")
            with st.expander("Analogy and practice question"):
                st.markdown(f"**Analogy:** {d.get('analogy', '')}")
                st.markdown(f"**Practice:** {d.get('practice_question', '')}")
        else:
            st.markdown(res["raw"])

        c1, c2 = st.columns(2)
        if c1.button("Reveal full explanation"):
            full = ask(
                f"Explain clearly, step by step, in {STYLE.get(language, STYLE['English'])}, "
                f"this {res['course']} doubt.\nDoubt: {res['doubt']}\n"
                f"Student's thinking: {res['thinking']}", "Writing the full explanation...")
            if full:
                res["full"] = full

        if d and c2.button("I got it now", disabled=res["got_it"]):
            res["got_it"] = True
            commit(memory.update_mastery(st.session_state.mem, str(d.get("topic") or res["course"]), 15))
            st.toast("Nice! Mastery went up.")

        if res.get("full"):
            st.markdown(res["full"])

    st.subheader("Your mastery")
    mastery = st.session_state.mem.get("mastery", {})
    if mastery:
        st.bar_chart(pd.Series(mastery, name="mastery"))
    else:
        st.caption("Nothing yet. Your first diagnosed doubt will show up here.")

# ------------------------------------------------------------- journal
def save_journal_entry() -> None:
    text = st.session_state.get("journal_text", "").strip()
    if text:
        commit(memory.add_journal(st.session_state.mem, text))
        st.session_state.journal_text = ""
        st.toast("Saved to your journal.")


with tab_journal:
    clip = st.audio_input("Dictate today's entry", key="journal_clip")
    data = new_audio("journal_clip", clip)
    if data:
        heard = transcribe(data)
        if heard:
            st.session_state.journal_text = heard

    st.text_area("Today's entry", key="journal_text", height=140)
    st.button("Save entry", on_click=save_journal_entry)

    entries = st.session_state.mem.get("journal", [])
    if not entries:
        st.info("No entries yet. Write or dictate your first one above.")
    else:
        # Fix for Slider Error: Ensure min < max
        max_val = min(len(entries), 14)
        default_val = min(len(entries), 5)
        
        if max_val < 1:
            n = 1
        elif max_val == 1:
            n = 1
            st.write("Using your single journal entry for the memoir.")
        else:
            n = st.slider("Entries to include in the memoir", 1, max_val, default_val)

        if st.button("Generate my audio memoir"):
            diary = "\n".join(f"{e.get('date', '')}: {e.get('text', '')}" for e in entries[-n:])
            story = ask(
                "Write a warm recap of about 150 words, in first person, as if the writer is "
                "speaking aloud about their recent days, based on these diary entries. Use "
                f"natural spoken sentences, no bullet points or headings. Language: "
                f"{STYLE.get(language, STYLE['English'])}.\n\nEntries:\n{diary}",
                "Writing your memoir...")
            if story:
                st.session_state.memoir = {"text": story, "audio": speak(story)}

        memoir = st.session_state.get("memoir")
        if memoir:
            st.write(memoir["text"])
            if memoir.get("audio"):
                st.audio(memoir["audio"], format="audio/wav")
                st.download_button("Download audio", data=memoir["audio"],
                                   file_name="e-bhai-memoir.wav", mime="audio/wav")

        with st.expander("All entries"):
            for e in reversed(entries):
                st.markdown(f"**{e.get('date', '')}**  \n{e.get('text', '')}")