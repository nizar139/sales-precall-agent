import streamlit as st
import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()

try:
    BACKEND_URL = st.secrets.get("BACKEND_URL")
except:
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
 
# Try env / Streamlit secrets first (local dev + CI), otherwise ask the user
_env_key = os.getenv("INTERNAL_API_KEY")
 
if _env_key:
    INTERNAL_API_KEY = _env_key
else:
    INTERNAL_API_KEY = st.text_input(
        "Enter access key",
        type="password",
        placeholder="Paste your API key to continue"
    )
    if not INTERNAL_API_KEY:
        st.stop()
 
headers = {"x-api-key": INTERNAL_API_KEY}
 
st.set_page_config(
    page_title="Sales Pre-Call Agent",
    page_icon="📋",
    layout="wide"
)
 
# ── Session state ────────────────────────────────────────────────────
if "brief" not in st.session_state:
    st.session_state.brief = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "has_research" not in st.session_state:
    st.session_state.has_research = False
if "tool_logs" not in st.session_state:
    st.session_state.tool_logs = []  # list of {"tool", "input", "output", "cached", "source"}
 
# ── Layout ───────────────────────────────────────────────────────────
left, right = st.columns([3, 2], gap="large")
 
# ══════════════════════════════════════════════
# LEFT: Research Panel
# ══════════════════════════════════════════════
with left:
    st.title("📋 Pre-Call Research")
 
    with st.form("research_form"):
        prompt_input = st.text_area(
            "Describe your call",
            placeholder=(
                "e.g. I'm calling meta.com — I'm selling a headless CMS platform\n\n"
                "or: Research stripe.com, we sell data observability tools and they're a Snowflake customer\n\n"
                "or: acme.com — pitching our Salesforce CPQ integration"
            ),
            height=120,
            label_visibility="collapsed"
        )
        submitted = st.form_submit_button("🔍 Research", use_container_width=True, type="primary")
 
    if submitted and prompt_input.strip():
        st.session_state.brief = None
        st.session_state.chat_history = []
        st.session_state.has_research = False
        st.session_state.tool_logs = []
 
        brief_placeholder = st.empty()
        status_placeholder = st.empty()
 
        try:
            with httpx.Client(timeout=120) as client:
                with client.stream(
                    "POST",
                    f"{BACKEND_URL}/research",
                    json={"prompt": prompt_input.strip()},
                    headers=headers
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
 
                        if event["type"] == "tool_log":
                            st.session_state.tool_logs.append({**event, "source": "research"})
                            tool_name = event["tool"]
                            cached_tag = " ✦ cached" if event.get("cached") else ""
                            status_placeholder.caption(f"⚙ {tool_name}{cached_tag}")
 
                        elif event["type"] == "brief":
                            st.session_state.brief = event["content"]
                            st.session_state.has_research = True
                            status_placeholder.empty()
 
                        elif event["type"] == "error":
                            st.error(event["message"])
 
        except httpx.ConnectError:
            st.error("Cannot connect to backend. Is the FastAPI server running?")
        except Exception as e:
            st.error(f"Error: {e}")
 
    elif submitted:
        st.warning("Please describe your call before researching.")
 
    if st.session_state.brief:
        st.divider()
        filename = "brief.md"
        st.download_button(
            label="⬇ Export .md",
            data=st.session_state.brief,
            file_name=filename,
            mime="text/markdown",
            use_container_width=False
        )
        st.markdown(st.session_state.brief)
    elif not submitted:
        st.info("Describe your call above — include the company domain and what you're selling.")
 
# ══════════════════════════════════════════════
# RIGHT: Chat Panel
# ══════════════════════════════════════════════
with right:
    st.title("💬 Follow-Up")
 
    if not st.session_state.has_research:
        st.caption("Research a company first to unlock the chat.")
    else:
        st.caption("Ask anything — tech stack details, more contacts, similar companies…")
 
        chat_container = st.container(height=450)
        with chat_container:
            if not st.session_state.chat_history:
                st.markdown("*Brief loaded. Ask a follow-up question.*")
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
 
        user_input = st.chat_input("Ask a follow-up...")
 
        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
 
            answer = ""
            status_placeholder = st.empty()
 
            try:
                with httpx.Client(timeout=60) as client:
                    with client.stream(
                        "POST",
                        f"{BACKEND_URL}/chat",
                        json={"message": user_input},
                        headers=headers
                    ) as resp:
                        resp.raise_for_status()
                        for line in resp.iter_lines():
                            if not line.startswith("data: "):
                                continue
                            event = json.loads(line[6:])
 
                            if event["type"] == "tool_log":
                                st.session_state.tool_logs.append({**event, "source": "chat"})
                                cached_tag = " ✦ cached" if event.get("cached") else ""
                                status_placeholder.caption(f"⚙ {event['tool']}{cached_tag}")
 
                            elif event["type"] == "message":
                                answer = event["content"]
                                status_placeholder.empty()
 
                            elif event["type"] == "error":
                                answer = f"Error: {event['message']}"
 
            except Exception as e:
                answer = f"Connection error: {e}"
 
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()
 
# ══════════════════════════════════════════════
# BOTTOM: Tool Log Panel
# ══════════════════════════════════════════════
if st.session_state.tool_logs:
    st.divider()
    with st.expander(f"🛠 Tool Calls ({len(st.session_state.tool_logs)})", expanded=False):
        for i, log in enumerate(st.session_state.tool_logs):
            source_tag = "research" if log.get("source") == "research" else "chat"
            cached_tag = "✦ cached" if log.get("cached") else "live"
            col1, col2 = st.columns([1, 4])
            with col1:
                st.markdown(f"`{log['tool']}`")
                st.caption(f"{source_tag} · {cached_tag}")
            with col2:
                with st.expander("input / output", expanded=False):
                    st.json(log.get("input", {}))
                    text = log.get("output", "")
                    st.json(text)
            if i < len(st.session_state.tool_logs) - 1:
                st.divider()