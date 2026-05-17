<!-- cSpell:disable -->
<!-- markdownlint-disable -->
# 🔐 Cyber-RAG Chatbot

> ⚡ Enterprise-grade Retrieval-Augmented Generation for Cybersecurity — powered by Local LLMs, built for analysts and students who need precise, cited answers from technical documents.

[![Streamlit](https://img.shields.io/badge/Streamlit-UI_Framework-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![LangChain](https://img.shields.io/badge/LangChain-RAG_Framework-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)
[![Ollama](https://img.shields.io/badge/Ollama-llama3.2-black?logo=ollama&logoColor=white)](https://ollama.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-E85D27)](https://www.trychroma.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Option A — Run Locally](#option-a--run-locally)
  - [Option B — Run with Docker](#option-b--run-with-docker)
  - [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [References / Useful Resources](#references--useful-resources)

---

## Overview

**Cyber-RAG Chatbot** is a fully local, privacy-first Retrieval-Augmented Generation (RAG) platform built for Cybersecurity documents. It connects to your own collection of PDFs — textbooks, manuals, threat reports — and uses a **locally-hosted LLM (Llama 3.2 via Ollama)** to deliver accurate, page-cited answers in real time, without sending any data to external services.

The system uses a **Hybrid Search** strategy (Semantic Vector Search + BM25 Keyword Search) to handle both conceptual queries and precise technical term lookups. The interface is inspired by Claude's minimalist dark theme, built with a custom Streamlit UI.

> 🔗 Demo on YouTube: *(link coming soon)*
> 📦 Open-source | `cyber-rag-chatbot`

<img width="800" alt="Cyber-RAG Chatbot – System Overview" src="assets/ai_avatar.png" />

---

## Key Features

| Feature | Description |
|---|---|
| 🧠 Hybrid Search | Combines Semantic Vector Search (ChromaDB) + Keyword Search (BM25) for high precision |
| 🤖 Local LLM | Uses Llama 3.2 (3B) via Ollama — fully offline, fully private, no API cost |
| ⚡ Token Streaming | Real-time response generation for a smooth, ChatGPT-like experience |
| 📄 PDF Management | Built-in sidebar uploader and instant re-indexing system |
| 🔖 Grounding & Citations | Every answer includes source document names and specific page numbers |
| 💾 Chat Persistence | Conversation history saved and reloaded automatically via SQLite |
| 🎨 Claude-inspired UI | Minimalist dark theme with custom CSS styling |
| 🐳 Docker Ready | Single-command deployment with Docker Compose |

---

## Architecture

The system operates on a modular RAG pipeline designed for accuracy and extensibility:

```text
                 ┌─────────────────────────────────────────────┐
                 │            PDF Document Collection           │
                 │   (Cybersecurity Manuals, Threat Reports)    │
                 └──────────────┬──────────────────────────────┘
                                │ Upload & Index
                                ▼
                 ┌─────────────────────────────────────────────┐
                 │              RAG Engine (rag_engine.py)      │
                 │   Text Splitting → Embedding → ChromaDB      │
                 └──────────┬─────────────────┬────────────────┘
                            │                 │
              ┌─────────────▼───┐   ┌─────────▼──────────────┐
              │  Vector Search  │   │    BM25 Keyword Search  │
              │  (ChromaDB +    │   │  (rank_bm25 — precise   │
              │  nomic-embed)   │   │   technical term match) │
              └──────┬──────────┘   └────────────┬───────────┘
                     │                           │
                     └──────────┬────────────────┘
                                │ Merged & Re-ranked Context
                                ▼
                 ┌─────────────────────────────────────────────┐
                 │              Ollama (llama3.2)               │
                 │    Streaming LLM Response with Citations     │
                 └──────────────┬──────────────────────────────┘
                                │ Answer + Sources
                                ▼
                 ┌─────────────────────────────────────────────┐
                 │           Streamlit Chat Interface           │
                 │     (app.py + style.css — Claude Theme)      │
                 └─────────────────────────────────────────────┘
```

### Module Responsibilities

- **`app.py`** — Main Streamlit UI entry point: chat interface, PDF uploader, session management.
- **`rag_engine.py`** — Core RAG logic: document loading, chunking, embedding, hybrid retrieval, and LLM streaming.
- **`style.css`** — Custom styling that gives the app its Claude-inspired dark aesthetic.
- **`docker-compose.yml`** — Deploys the Streamlit app in an isolated container connected to the host's Ollama instance.

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI Framework | [Streamlit](https://streamlit.io/) + Custom CSS |
| RAG Framework | [LangChain](https://www.langchain.com/) |
| Local LLM | [Ollama](https://ollama.com/) + `llama3.2:3b` |
| Embeddings | [Ollama](https://ollama.com/) + `nomic-embed-text` |
| Vector Database | [ChromaDB](https://www.trychroma.com/) |
| Keyword Search | [rank_bm25](https://github.com/dorianbrown/rank_bm25) |
| Chat Persistence | SQLite via SQLAlchemy |
| Containerization | Docker & Docker Compose |

---

## Getting Started

### Prerequisites

Before running the project, ensure the following are available:

- ✅ **Python 3.10+** — for local development.
- ✅ **Docker & Docker Compose** — for containerized deployment.
- ✅ **Ollama** — installed and running on your host machine.
- ✅ **Ollama Models** — pulled before first run.

Pull required models:
```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

---

### Option A — Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/Taeaps561/cyber-rag-chatbot.git
cd cyber-rag-chatbot

# 2. Create and activate a virtual environment
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env with your values

# 5. Run the app
streamlit run app.py
```

Open your browser at `http://localhost:8501`

---

### Option B — Run with Docker

```bash
# 1. Clone the repository
git clone https://github.com/Taeaps561/cyber-rag-chatbot.git
cd cyber-rag-chatbot

# 2. Set up environment variables
cp .env.example .env
# Edit .env with your values

# 3. Start the container
docker compose up --build -d
```

Open your browser at `http://localhost:8501`

---

### Configuration

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description | Required |
|---|---|---|
| `API_KEY` | Internal API key for the application | Yes |
| `LANGCHAIN_TRACING_V2` | Enable LangSmith tracing (`true`/`false`) | Optional |
| `LANGCHAIN_API_KEY` | LangSmith API key for observability | Optional |
| `LANGCHAIN_PROJECT` | LangSmith project name | Optional |
| `OPENAI_API_KEY` | OpenAI API key (if switching from Ollama) | Optional |

---

## Usage

Once running and configured, the system will automatically:

1. Load any PDFs placed in the `data/` folder into the vector store on first run.
2. Use the sidebar uploader to add new documents and trigger re-indexing at any time.
3. Type your cybersecurity question into the chat — receive a streamed answer with source citations.
4. Use the sidebar to clear chat history or manage indexed documents.

---

## Project Structure

```text
cyber-rag-chatbot/
│
├── app.py                    # Main Streamlit UI entry point
├── rag_engine.py             # Core RAG logic and hybrid search implementation
├── style.css                 # Custom CSS — Claude-inspired dark theme
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container definition
├── docker-compose.yml        # Container orchestration
├── .env.example              # Environment variable template (safe to commit)
├── .env                      # Your local secrets (git-ignored)
├── assets/
│   ├── ai_avatar.png         # AI message avatar
│   └── user_avatar.png       # User message avatar
├── data/                     # Place your PDF documents here (git-ignored)
│   ├── Class_Materials/      # Example: lecture slides
│   └── Network_Intelligence/ # Example: threat intelligence reports
└── chroma_db/                # Auto-generated vector store (git-ignored)
```

---

## References / Useful Resources

- [LangChain Documentation](https://python.langchain.com/docs/)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [Ollama API Reference](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [rank_bm25 GitHub](https://github.com/dorianbrown/rank_bm25)

---

## My Notes

> 📝 This project was built as a hands-on exploration of local-first RAG systems, combining hybrid search strategies with privacy-preserving LLM inference. It is designed to demonstrate how powerful AI-assisted knowledge retrieval can be achieved entirely on local hardware without any cloud dependency.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

*Built with ❤️ for defenders and learners — by an analyst who hates sending data to the cloud.*
