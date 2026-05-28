import os
import time
import streamlit as st
from dotenv import load_dotenv
from rag_engine import RAGEngine
from utils import (
    save_chat_history_db,
    load_chat_history_db,
    get_all_sessions_db,
    delete_session_db,
    rename_session_db,
    export_session_md,          # [Phase 1] Chat export
    log_query,                  # [Phase 2] Analytics logging
    get_analytics,              # [Phase 2] Analytics dashboard
)
import uuid
import base64

# -------------------------------------------------------------
# 1. System Configuration
# -------------------------------------------------------------
load_dotenv()
st.set_page_config(page_title="Cyber-RAG Enterprise", page_icon="🛡️", layout="wide")

def local_css(file_name):
    file_path = os.path.join(os.path.dirname(__file__), file_name)
    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def get_base64_img(img_path):
    abs_path = os.path.join(os.path.dirname(__file__), img_path)
    if os.path.exists(abs_path):
        with open(abs_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

# UI Assets
user_img_base64 = get_base64_img("assets/user_avatar.png")
ai_img_base64 = get_base64_img("assets/ai_avatar.png")
local_css("style.css")

# -------------------------------------------------------------
# 2. RAG Engine Setup
# -------------------------------------------------------------
@st.cache_resource
def get_cyber_engine_v4():
    e = RAGEngine()
    _, status_msg = e.init_system()
    return e, status_msg

engine, _init_status = get_cyber_engine_v4()

# -------------------------------------------------------------
# 3. Sidebar
# -------------------------------------------------------------
with st.sidebar:
    st.markdown(f"""
    <div class="sidebar-title">Cyber-RAG 🛡️</div>
    <div class="sidebar-subtitle">Enterprise Intelligence</div>
    <div class="sidebar-divider"></div>
    """, unsafe_allow_html=True)

    # Show system init status
    if engine.graph:
        if engine.retriever is None:
            st.warning("🌐 โหมด Web Search Only (ไม่พบ Vector DB)")
        else:
            st.success("✅ ระบบ RAG พร้อมใช้งาน")
    else:
        st.error(f"❌ ระบบยังไม่พร้อม: {_init_status}")
        if "Ollama" in _init_status:
            st.info("💡 ตรวจสอบว่า Ollama รันอยู่หรือไม่")

    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

    # [Phase 1] Export current session as Markdown
    if st.session_state.get("messages"):
        sess_title = ""
        for sess in get_all_sessions_db():
            if sess.session_id == st.session_state.get("session_id", ""):
                sess_title = sess.title or "chat_export"
                break
        md_content = export_session_md(st.session_state.session_id, sess_title)
        safe_name = "".join(c if c.isalnum() or c in "_- " else "_" for c in sess_title[:30]).strip()
        st.download_button(
            label="📥 Export Chat (.md)",
            data=md_content,
            file_name=f"{safe_name or 'chat_export'}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    st.divider()

    # 3.2 RAG System & Upload
    with st.expander("📊 ระบบ RAG (RAG System)", expanded=False):
        st.markdown("**📤 อัปโหลดเอกสารใหม่**")
        # [Phase 1] Added .docx and .md support
        uploaded_files = st.file_uploader(
            "เลือกไฟล์ (PDF, TXT, DOCX, MD):",
            accept_multiple_files=True,
            type=['pdf', 'txt', 'docx', 'md']
        )

        # Folder selection for upload
        target_folders = engine.available_folders
        dest_folder = st.selectbox("เลือกโฟล์เดอร์ปลายทาง:", options=target_folders)

        if st.button("🚀 เริ่มการอัปโหลด"):
            if uploaded_files:
                for uploaded_file in uploaded_files:
                    save_path = os.path.join("data", dest_folder, uploaded_file.name)
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                st.success(f"✅ อัปโหลดสำเร็จ {len(uploaded_files)} ไฟล์!")
                # [Phase 1] Progress bar during re-index (Bug Fix #4: uses lock internally)
                reindex_bar = st.progress(0, text="⚙️ กำลัง re-index...")
                engine.init_system(
                    progress_callback=lambda v, msg: reindex_bar.progress(v, text=msg)
                )
                st.rerun()
            else:
                st.warning("⚠️ กรุณาเลือกไฟล์ก่อนกดอัปโหลด")

        st.divider()
        st.markdown("**🔍 ตั้งค่าการค้นหา**")
        folder_options = ["ทั้งหมด"] + engine.available_folders
        selected_folder = st.selectbox("ค้นหาจากโฟลเดอร์:", options=folder_options, index=0, key="search_folder")
        st.session_state.selected_folder = selected_folder
        engine.scan_data_stats(filter_folder=selected_folder)
        st.write(f"📄 **จำนวนเอกสาร:** {engine.doc_count} ไฟล์")
        st.write(f"🔄 **อัปเดตล่าสุด:** {engine.last_sync}")

    st.divider()

    # 3.3 Chat History
    search_query = st.text_input("🔍 ค้นหาประวัติแชท", placeholder="พิมพ์เพื่อค้นหา...")
    sessions = get_all_sessions_db(search_query)
    
    for sess in sessions:
        col1, col2, col3 = st.columns([0.65, 0.17, 0.17])
        with col1:
            title_label = sess.title if sess.title else "New Chat"
            if st.button(f"📄 {title_label}", key=f"load_{sess.session_id}", use_container_width=True):
                st.session_state.session_id = sess.session_id
                st.session_state.messages = load_chat_history_db(sess.session_id)
                st.rerun()
        with col2:
            if st.button("✏️", key=f"ren_{sess.session_id}", use_container_width=True):
                st.session_state.renaming_id = sess.session_id
        with col3:
            if st.button("🗑️", key=f"del_{sess.session_id}", use_container_width=True):
                if delete_session_db(sess.session_id):
                    if st.session_state.get("session_id") == sess.session_id:
                        st.session_state.session_id = str(uuid.uuid4())
                        st.session_state.messages = []
                    st.rerun()

    if "renaming_id" in st.session_state:
        new_name = st.text_input("ชื่อหัวข้อใหม่:")
        if st.button("ตกลง"):
            rename_session_db(st.session_state.renaming_id, new_name)
            del st.session_state.renaming_id
            st.rerun()

    st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)

# -------------------------------------------------------------
# 4. Main Tabs — Chat | Analytics
# -------------------------------------------------------------
tab_chat, tab_analytics = st.tabs(["💬 Chat", "📊 Analytics"])

with tab_chat:
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    if "messages" not in st.session_state:
        st.session_state.messages = load_chat_history_db(st.session_state.session_id)

    # Greeting
    greeting_placeholder = st.empty()
    if not st.session_state.messages:
        with greeting_placeholder.container():
            st.markdown("""
            <div class="greeting-container">
                <div class="plan-pill">CYBER-RAG ENTERPRISE</div>
                <div class="greeting-text">🛡️ How can I assist you today?</div>
            </div>
            """, unsafe_allow_html=True)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "sources" in message and message["sources"]:
                with st.expander("📚 อ้างอิงแหล่งที่มา"):
                    for src in message["sources"]:
                        st.caption(f"📍 {src}")

    # [Phase 2] Input lives inside tab_chat
    prompt = st.chat_input("Ask about cybersecurity...")
    if prompt:
        greeting_placeholder.empty()
        st.session_state.messages.append({"role": "user", "content": prompt})
        save_chat_history_db(st.session_state.session_id, "user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            status_placeholder = st.empty()
            response_placeholder = st.empty()
            full_response = ""
            all_docs = []
            used_web = False
            t_start = time.time()

            status_placeholder.info("🔍 กำลังค้นหาข้อมูลจากคลังความรู้...")

            filter_folder = st.session_state.get("selected_folder", "ทั้งหมด")
            # [Phase 2] 3-tuple: gen_chunk, docs, is_web
            for gen_chunk, docs, is_web in engine.query_stream(prompt, filter_folder=filter_folder):
                if docs:
                    all_docs = docs
                if is_web:
                    used_web = True
                    status_placeholder.warning("🌐 ไม่พบในคลัง กำลังใช้ DuckDuckGo แทน...")
                elif docs:
                    status_placeholder.success(f"✅ พบข้อมูลที่เกี่ยวข้อง {len(docs)} ส่วน")

                if gen_chunk:
                    full_response += gen_chunk
                    response_placeholder.markdown(full_response + "▌")

            response_time_ms = int((time.time() - t_start) * 1000)
            response_placeholder.markdown(full_response)
            status_placeholder.empty()

            # Citations with Confidence Score + web badge
            sources = []
            if all_docs:
                web_label = "🌐 DuckDuckGo" if used_web else "📚"
                with st.expander(f"{web_label} อ้างอิงแหล่งที่มา (Sources)"):
                    unique_sources = set()
                    for doc in all_docs:
                        src_name = os.path.basename(doc.metadata.get("source", "Unknown"))
                        page = doc.metadata.get("page", 0) + 1
                        score = doc.metadata.get("relevance_score", None)
                        score_str = f"  `🎯 {score:.0%}`" if score is not None else ""
                        source_label = f"{src_name} (หน้า {page})"
                        if source_label not in unique_sources:
                            st.markdown(f"**📍 {source_label}**{score_str}")
                            st.caption(f"\"{doc.page_content[:200]}...\"")
                            unique_sources.add(source_label)
                            sources.append(source_label)

            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response,
                "sources": sources
            })
            save_chat_history_db(st.session_state.session_id, "assistant", full_response, sources=sources)

            # [Phase 2] Log query for analytics
            log_query(
                session_id=st.session_state.session_id,
                query=prompt,
                response_ms=response_time_ms,
                doc_count=len(all_docs),
                folder=filter_folder,
                used_web=used_web,
            )

# =============================================================
# [Phase 2] Analytics Tab
# =============================================================
with tab_analytics:
    st.markdown("## 📊 Analytics Dashboard")
    days_range = st.selectbox(
        "ช่วงเวลา:", [7, 14, 30], index=0,
        format_func=lambda x: f"ย้อนหลัง {x} วัน",
        key="analytics_days"
    )
    data = get_analytics(days=days_range)

    # KPI metrics row
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💬 Total Queries", data["total_queries"])
    k2.metric("⏱️ Avg Response", f"{data['avg_response_ms']:,} ms")
    k3.metric("🌐 Web Search", f"{data['web_ratio']}%")
    k4.metric("📠 Sessions", data["total_sessions"])

    st.divider()

    # Daily activity bar chart
    st.markdown("**📅 Daily Query Activity**")
    if data["daily_counts"]:
        import pandas as pd
        df_daily = pd.DataFrame(data["daily_counts"]).set_index("day")
        st.bar_chart(df_daily["count"])
    else:
        st.info("⚠️ ยังไม่มีข้อมูล — เริ่มใช้งาน chatbot เพื่อดูสถิติ")

    st.divider()

    # Top queries table
    st.markdown("**🔍 Top Queries**")
    if data["top_queries"]:
        import pandas as pd
        df_top = pd.DataFrame(data["top_queries"]).rename(
            columns={"query": "💬 Query", "freq": "🔢 Count"}
        )
        st.dataframe(df_top, use_container_width=True, hide_index=True)
    else:
        st.info("ยังไม่มีประวัติการใช้งาน")
