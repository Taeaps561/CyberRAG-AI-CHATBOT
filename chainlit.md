# 🛡️ Cyber-RAG Enterprise

ระบบ RAG ด้านความปลอดภัยไซเบอร์ ขับเคลื่อนด้วย Ollama + LangChain

## วิธีใช้งาน

| คำสั่ง | ผล |
|---|---|
| พิมพ์คำถาม | ค้นหาจากคลังเอกสาร หรือ Web Search |
| แนบไฟล์ (📎) | อัปโหลด PDF/TXT/DOCX/MD เพิ่มความรู้ |
| `/analytics` | ดูสถิติการใช้งาน |
| ⚙️ Settings | เลือกโฟลเดอร์ที่ต้องการค้นหา |

## Tech Stack
- 🤖 **Ollama** + `llama3.2` — Local LLM
- 🔗 **LangChain** + **LangGraph** — RAG Pipeline  
- 🗄️ **ChromaDB** + **BM25** — Hybrid Search
- 🌐 **DuckDuckGo** — Web Search Fallback
- 💬 **Chainlit** — Chat UI
