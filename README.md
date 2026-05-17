# Cyber-RAG Chatbot ✸

A local RAG (Retrieval-Augmented Generation) chatbot designed for Cybersecurity manuals, featuring a premium "Claude-like" UI, Hybrid Search, and Real-time Streaming.

---

## 🌟 Features

- **Claude-inspired UI**: Minimalist dark theme using Streamlit and custom CSS.
- **Hybrid Search**: Combines Semantic Vector Search (ChromaDB) and Keyword Search (BM25) for high-accuracy retrieval of technical terms.
- **Local LLM Integration**: Powered by **Ollama** (supports llama3.2, qwen2.5, etc.) for 100% privacy.
- **Token Streaming**: Real-time response generation for a smoother user experience.
- **Document Management**: Built-in PDF uploader and re-indexing system in the sidebar.
- **Chat Persistence**: Saves and loads conversation history locally.
- **Grounding & Sources**: Citations and specific page numbers from your PDF documents.

## 🛠️ Tech Stack

- **Frontend**: Streamlit + Custom CSS
- **RAG Framework**: LangChain
- **Embeddings**: Ollama (model: `nomic-embed-text`)
- **LLM**: Ollama (model: `llama3.2`)
- **Vector Database**: ChromaDB
- **Keyword Search**: rank_bm25
- **Container**: Docker / Docker Compose

## 🚀 Getting Started

### Prerequisites

1. Install [Ollama](https://ollama.com/).
2. Pull required models:
   ```bash
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```

### Option A — Run Locally

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/cyber-rag-chatbot.git
   cd cyber-rag-chatbot
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

5. Run the app:
   ```bash
   streamlit run app.py
   ```

6. Open your browser at `http://localhost:8501`

### Option B — Run with Docker

```bash
cp .env.example .env
# Edit .env with your values
docker compose up --build
```

Open your browser at `http://localhost:8501`

## 📁 Project Structure

```
cyber-rag-chatbot/
├── app.py              # Main Streamlit UI entry point
├── rag_engine.py       # Core RAG logic and hybrid search implementation
├── style.css           # Custom styling for the Claude-inspired look
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container definition
├── docker-compose.yml  # Multi-service container orchestration
├── .env.example        # Environment variable template
├── assets/             # UI avatars and static images
├── data/               # Place your PDF documents here for indexing
└── chroma_db/          # Auto-generated vector store (git-ignored)
```

## 🔧 Environment Variables

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description | Required |
|---|---|---|
| `API_KEY` | Internal API key for the app | Yes |
| `LANGCHAIN_API_KEY` | LangSmith API key for tracing | Optional |
| `LANGCHAIN_TRACING_V2` | Enable LangSmith tracing | Optional |
| `LANGCHAIN_PROJECT` | LangSmith project name | Optional |
| `OPENAI_API_KEY` | OpenAI API key (if switching from Ollama) | Optional |

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
