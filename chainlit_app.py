import os
import time
import uuid
import shutil
from dotenv import load_dotenv
import chainlit as cl
from chainlit.input_widget import Select
from rag_engine import RAGEngine
from utils import (
    save_chat_history_db,
    log_query,
    get_analytics,
)

load_dotenv()

# ─────────────────────────────────────────────
# Singleton RAG Engine (init once at startup)
# ─────────────────────────────────────────────
_engine: RAGEngine = None

def get_engine() -> RAGEngine:
    global _engine
    if _engine is None:
        _engine = RAGEngine()
        _engine.init_system()
    return _engine

engine = get_engine()


# ─────────────────────────────────────────────
# Chat Start
# ─────────────────────────────────────────────
@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("session_id", str(uuid.uuid4()))
    cl.user_session.set("filter_folder", "ทั้งหมด")

    # Build folder options for settings
    folders = ["ทั้งหมด"] + engine.available_folders
    settings = await cl.ChatSettings([
        Select(
            id="filter_folder",
            label="🔍 ค้นหาจากโฟลเดอร์",
            values=folders,
            initial_value="ทั้งหมด",
        )
    ]).send()
    cl.user_session.set("filter_folder", settings.get("filter_folder", "ทั้งหมด"))

    # System status message
    if engine.graph:
        if engine.retriever is None:
            status = "🌐 **โหมด Web Search Only** — ไม่พบ Vector Database\nระบบใช้ DuckDuckGo ค้นหาแทน"
        else:
            engine.scan_data_stats()
            status = (
                f"✅ **ระบบ RAG พร้อมใช้งาน**\n"
                f"📄 เอกสาร: **{engine.doc_count} ไฟล์** | 🔄 อัปเดต: **{engine.last_sync}**"
            )
    else:
        status = "❌ **ระบบยังไม่พร้อม** — ตรวจสอบว่า Ollama รันอยู่หรือไม่"

    await cl.Message(
        content=(
            f"## 🛡️ Cyber-RAG Enterprise\n\n"
            f"{status}\n\n---\n"
            f"💬 ถามคำถามด้านความปลอดภัยไซเบอร์ได้เลย\n"
            f"📎 แนบไฟล์ (PDF, TXT, DOCX, MD) เพื่อเพิ่มเข้าคลังความรู้\n"
            f"⚙️ กด Settings (ล่างซ้าย) เพื่อเลือกโฟลเดอร์\n"
            f"📊 พิมพ์ `/analytics` เพื่อดูสถิติการใช้งาน"
        ),
        author="Cyber-RAG 🛡️",
    ).send()


# ─────────────────────────────────────────────
# Settings Update (folder filter)
# ─────────────────────────────────────────────
@cl.on_settings_update
async def on_settings_update(settings):
    folder = settings.get("filter_folder", "ทั้งหมด")
    cl.user_session.set("filter_folder", folder)
    await cl.Message(
        content=f"✅ เปลี่ยนโฟลเดอร์ค้นหาเป็น: **{folder}**",
        author="System",
    ).send()


# ─────────────────────────────────────────────
# Main Message Handler
# ─────────────────────────────────────────────
@cl.on_message
async def on_message(message: cl.Message):
    session_id = cl.user_session.get("session_id")
    filter_folder = cl.user_session.get("filter_folder", "ทั้งหมด")

    # ── File Upload ──────────────────────────
    if message.elements:
        uploaded = []
        for el in message.elements:
            if hasattr(el, "path") and el.path:
                folder = filter_folder if filter_folder != "ทั้งหมด" else "uploads"
                dest_dir = os.path.join("data", folder)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy(el.path, os.path.join(dest_dir, el.name))
                uploaded.append(el.name)

        if uploaded:
            await cl.Message(
                content=f"✅ อัปโหลดสำเร็จ: `{'`, `'.join(uploaded)}`\n⚙️ กำลัง re-index...",
                author="System",
            ).send()
            engine.init_system()
            engine.scan_data_stats()
            await cl.Message(
                content=f"✅ Re-index เสร็จสิ้น! มีเอกสาร **{engine.doc_count} ไฟล์** แล้ว",
                author="System",
            ).send()
        return

    # ── Commands ─────────────────────────────
    cmd = message.content.strip().lower()
    if cmd in ["/analytics", "/สถิติ"]:
        data = get_analytics(days=7)
        await cl.Message(
            content=(
                f"## 📊 Analytics — 7 วันล่าสุด\n\n"
                f"| Metric | Value |\n|---|---|\n"
                f"| 💬 Total Queries | {data['total_queries']} |\n"
                f"| ⏱️ Avg Response | {data['avg_response_ms']:,} ms |\n"
                f"| 🌐 Web Search | {data['web_ratio']}% |\n"
                f"| 📁 Sessions | {data['total_sessions']} |"
            ),
            author="Analytics 📊",
        ).send()
        return

    # ── Guard ────────────────────────────────
    if not engine.graph:
        await cl.Message(
            content="❌ ระบบยังไม่พร้อม กรุณาตรวจสอบว่า Ollama รันอยู่",
            author="System",
        ).send()
        return

    save_chat_history_db(session_id, "user", message.content)

    # ── Streaming Response ────────────────────
    t_start = time.time()
    msg = cl.Message(content="", author="Cyber-RAG 🛡️")
    await msg.send()

    full_response = ""
    all_docs = []
    used_web = False

    try:
        for gen_chunk, docs, is_web in engine.query_stream(
            message.content, filter_folder=filter_folder
        ):
            if docs:
                all_docs = docs
            if is_web:
                used_web = True
            if gen_chunk:
                await msg.stream_token(gen_chunk)
                full_response += gen_chunk
    except Exception as e:
        await msg.stream_token(f"\n\n❌ Error: {e}")

    await msg.update()

    # ── Sources ───────────────────────────────
    if all_docs:
        unique: dict = {}
        for doc in all_docs:
            src = os.path.basename(doc.metadata.get("source", "Unknown"))
            page = doc.metadata.get("page", 0) + 1
            score = doc.metadata.get("relevance_score", None)
            label = f"{src} (หน้า {page})"
            if label not in unique:
                unique[label] = score

        lines = []
        for label, score in unique.items():
            s = f" `🎯 {score:.0%}`" if score is not None else ""
            lines.append(f"- 📍 **{label}**{s}")

        src_type = "🌐 DuckDuckGo" if used_web else "📚 Vector DB"
        await cl.Message(
            content=f"**{src_type} — แหล่งอ้างอิง:**\n\n" + "\n".join(lines),
            author="Sources",
        ).send()

    # ── Log ───────────────────────────────────
    response_ms = int((time.time() - t_start) * 1000)
    save_chat_history_db(session_id, "assistant", full_response)
    log_query(
        session_id=session_id,
        query=message.content,
        response_ms=response_ms,
        doc_count=len(all_docs),
        folder=filter_folder,
        used_web=used_web,
    )
