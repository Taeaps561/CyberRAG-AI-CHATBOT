import os
import logging
import requests
import threading
from datetime import datetime
from typing import List, TypedDict, Dict, Any, Optional, Tuple, Iterator, Union
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain_community.document_compressors.flashrank_rerank import FlashrankRerank
from langgraph.graph import StateGraph, END

# Disable LangChain Tracing
os.environ["LANGCHAIN_TRACING_V2"] = "false"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CyberRAGEngine")

class AgentState(TypedDict):
    question: str
    expanded_query: str
    generation: str
    documents: List[Any]
    status: str
    filter_folder: Optional[str]
    web_search_needed: bool    # [Phase 2] flag set by grade_docs node
    used_web_search: bool      # [Phase 2] recorded for analytics

class RAGEngine:
    def __init__(self, model_name: str = "llama3.2", embed_model: str = "nomic-embed-text"):
        self.data_dir = os.path.join(os.path.dirname(__file__), "data")
        self.db_dir = os.path.join(os.path.dirname(__file__), "chroma_db")
        self.model_name = model_name
        self.embed_model = embed_model
        self.vectorstore = None
        self.retriever = None
        self.graph = None
        self.is_advanced_ready = False
        self._init_lock = threading.Lock()  # [Bug Fix #4] prevent concurrent double-init

        # Stats
        self.doc_count = 0
        self.last_sync = "Never"
        self.available_folders = []

        self.llm = ChatOllama(
            model=self.model_name,
            temperature=0,
            base_url="http://127.0.0.1:11434",
            timeout=120,
            num_ctx=2048,   # [Bug Fix #1] was 512 (too low) — 2048 for proper context window
            num_thread=2
        )
        # Strict Expert Prompt
        self.system_prompt = """คุณคือผู้เชี่ยวชาญด้าน Cybersecurity และ Networking ระดับสูง 
หน้าที่ของคุณคือตอบคำถามจากบริบท (Context) ที่ให้มาเท่านั้น
กฎเหล็ก:
1. ตอบเป็นภาษาไทยที่สุภาพและเป็นทางการเท่านั้น ห้ามใช้ภาษาอื่นปน
2. หากข้อมูลในบริบทขัดแย้งกัน ให้ยึดตามหลักการทางเทคนิคที่ถูกต้องที่สุด (เช่น OSI Layer 3 คือ Network Layer เสมอ)
3. หากหาคำตอบไม่เจอจริงๆ ให้บอกว่าไม่พบข้อมูลในคลังความรู้
4. ห้ามเดาหรือสร้างข้อมูลเท็จ (Hallucination)"""

    def check_ollama(self) -> bool:
        try:
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
            return response.status_code == 200
        except: return False

    def init_system(self, progress_callback=None) -> Tuple[Optional[Any], str]:
        """[Bug Fix #4] Use lock to prevent concurrent double-init. Supports progress_callback(float, str).
        [No-Doc Mode] If no chroma_db is found, system still starts in Web-Search-only mode."""
        if self._init_lock.locked():
            return self.graph, "Already initializing, please wait..."
        with self._init_lock:
            if not self.check_ollama():
                return None, "Ollama is not responding."
            def _cb(v, msg):
                if progress_callback: progress_callback(v, msg)
            _cb(0.1, "🔍 กำลังสแกนเอกสาร...")
            self.scan_data_stats()
            try:
                if os.path.exists(os.path.join(self.db_dir, "chroma.sqlite3")):
                    _cb(0.3, "⚙️ กำลังโหลด Embeddings...")
                    embeddings = OllamaEmbeddings(model=self.embed_model, base_url="http://127.0.0.1:11434")
                    _cb(0.6, "🗄️ กำลังเชื่อมต่อ Vector Database...")
                    self.vectorstore = Chroma(persist_directory=self.db_dir, embedding_function=embeddings)
                    self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 8})
                    threading.Thread(target=self._init_advanced_features, args=(embeddings,), daemon=True).start()
                else:
                    # [No-Doc Mode] No vector DB found — run in Web Search only mode
                    _cb(0.6, "⚠️ ไม่พบ Vector Database — เปิดโหมด Web Search อย่างเดียว")
                    self.retriever = None
                _cb(0.85, "🔗 กำลัง Build LangGraph...")
                self._build_graph()
                _cb(1.0, "✅ พร้อมใช้งาน (โหมด Web Search)" if self.retriever is None else "✅ พร้อมใช้งาน!")
                return self.graph, "Success"
            except Exception as e:
                return None, f"Error: {e}"

    def scan_data_stats(self, filter_folder: str = "ทั้งหมด"):
        """[Phase 1] Added .docx and .md to supported extensions."""
        try:
            filtered_count = 0
            folders = set()
            newest_time = 0
            supported_ext = ('.pdf', '.txt', '.docx', '.md')
            for root, dirs, files in os.walk(self.data_dir):
                rel_path = os.path.relpath(root, self.data_dir)
                if rel_path != "." and "\\" not in rel_path and "/" not in rel_path:
                    folders.add(rel_path)
                # [Bug Fix #2] use os.path comparison instead of bare 'in' to avoid partial folder name matches
                in_filter = (
                    filter_folder == "ทั้งหมด" or
                    os.path.normcase(root).startswith(os.path.normcase(os.path.join(self.data_dir, filter_folder)))
                )
                if in_filter:
                    for file in files:
                        if file.endswith(supported_ext):
                            filtered_count += 1
                            mtime = os.path.getmtime(os.path.join(root, file))
                            if mtime > newest_time: newest_time = mtime
            self.doc_count = filtered_count
            self.available_folders = sorted(list(folders))
            if newest_time > 0: self.last_sync = datetime.fromtimestamp(newest_time).strftime("%Y-%m-%d %H:%M")
        except Exception as e: logger.error(f"Stat scan failed: {e}")

    def _init_advanced_features(self, embeddings):
        """[Phase 1] Added .docx and .md loader support alongside pdf/txt."""
        try:
            docs = []
            allowed = {
                "pdf":  (PyPDFLoader, "**/*.pdf"),
                "txt":  (TextLoader,  "**/*.txt"),
            }
            # Lazy-load optional loaders so missing packages don't crash the engine
            try:
                from langchain_community.document_loaders import UnstructuredWordDocumentLoader
                allowed["docx"] = (UnstructuredWordDocumentLoader, "**/*.docx")
            except ImportError:
                logger.warning("UnstructuredWordDocumentLoader not available — .docx skipped")
            try:
                from langchain_community.document_loaders import UnstructuredMarkdownLoader
                allowed["md"] = (UnstructuredMarkdownLoader, "**/*.md")
            except ImportError:
                logger.warning("UnstructuredMarkdownLoader not available — .md skipped")

            for ext, (loader_cls, glob) in allowed.items():
                try:
                    loader = DirectoryLoader(
                        self.data_dir, glob=glob, loader_cls=loader_cls, silent_errors=True
                    )
                    docs.extend(loader.load())
                except Exception as load_err:
                    logger.warning(f"Loader [{ext}] failed: {load_err}")

            if not docs: return
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            splits = text_splitter.split_documents(docs)
            vector_retriever = self.vectorstore.as_retriever(search_kwargs={"k": 8})
            bm25_retriever = BM25Retriever.from_documents(splits)
            bm25_retriever.k = 5
            ensemble = EnsembleRetriever(retrievers=[vector_retriever, bm25_retriever], weights=[0.6, 0.4])
            compressor = FlashrankRerank(model="ms-marco-MiniLM-L-12-v2", top_n=5)
            self.retriever = ContextualCompressionRetriever(base_compressor=compressor, base_retriever=ensemble)
            self.is_advanced_ready = True
            logger.info(f"Advanced retriever ready with {len(splits)} chunks")
        except Exception as e: logger.error(f"Stage 2 Failed: {e}")

    def _build_graph(self):
        """[Phase 2] Graph now has grade_docs + conditional web_search fallback."""
        workflow = StateGraph(AgentState)
        workflow.add_node("rewrite",    self.node_rewrite)
        workflow.add_node("retrieve",   self.node_retrieve)
        workflow.add_node("grade_docs", self.node_grade_docs)
        workflow.add_node("web_search", self.node_web_search)
        workflow.add_node("generate",   self.node_generate)
        workflow.set_entry_point("rewrite")
        workflow.add_edge("rewrite",    "retrieve")
        workflow.add_edge("retrieve",   "grade_docs")
        workflow.add_conditional_edges(
            "grade_docs",
            self._route_after_grade,
            {"web_search": "web_search", "generate": "generate"},
        )
        workflow.add_edge("web_search", "generate")
        workflow.add_edge("generate",   END)
        self.graph = workflow.compile()

    def node_rewrite(self, state: AgentState) -> Dict[str, Any]:
        """Expands the query to get better retrieval results."""
        prompt = f"ขยายความคำถามต่อไปนี้ให้เป็นประโยคคำถามที่ชัดเจนสำหรับการค้นหาข้อมูลทางเทคนิค (ตอบแค่ประโยคที่ขยายแล้วเท่านั้น): {state['question']}"
        expanded = self.llm.invoke(prompt).content
        return {"expanded_query": expanded, "status": "🧠 กำลังวิเคราะห์คำถาม..."}

    def node_retrieve(self, state: AgentState) -> Dict[str, Any]:
        """[Bug Fix #2] Replaced bare 'in' string match with os.path comparison for reliable folder filtering.
        [No-Doc Mode] If retriever is None, return empty docs to trigger web_search fallback."""
        if self.retriever is None:
            return {"documents": [], "status": "⚠️ ไม่มีคลังเอกสาร — กำลังค้นหาจากเว็บ..."}
        query = state.get("expanded_query", state["question"])
        folder_filter = state.get("filter_folder")
        documents = self.retriever.invoke(query)
        if folder_filter and folder_filter != "ทั้งหมด":
            filter_root = os.path.normcase(os.path.join(self.data_dir, folder_filter))
            filtered = []
            for d in documents:
                src = os.path.normcase(d.metadata.get("source", ""))
                if src.startswith(filter_root):
                    filtered.append(d)
            documents = filtered
        return {"documents": documents, "status": "🔍 ค้นหาข้อมูลทางเทคนิค..."}

    def node_generate(self, state: AgentState) -> Dict[str, Any]:
        context = "\n\n".join([f"[Source: {os.path.basename(d.metadata.get('source',''))}]\n{d.page_content}" for d in state["documents"]])
        template = f"{self.system_prompt}\n\nContext:\n{{context}}\n\nQuestion: {{question}}\nAnswer:"
        prompt = PromptTemplate(template=template, input_variables=["context", "question"])
        chain = prompt | self.llm | StrOutputParser()
        generation = chain.invoke({"context": context, "question": state["question"]})
        return {"generation": generation, "status": "เสร็จสิ้น"}

    # ------------------------------------------------------------------
    # [Phase 2] New nodes: grade_docs, web_search, routing
    # ------------------------------------------------------------------

    def node_grade_docs(self, state: AgentState) -> Dict[str, Any]:
        """Decide if retrieved documents are sufficient; if not, trigger web search fallback."""
        docs = state.get("documents", [])
        if not docs:
            logger.info("grade_docs: no local documents found — routing to web_search")
            return {"web_search_needed": True, "used_web_search": False,
                    "status": "🌐 ไม่พบข้อมูลในคลัง กำลังค้นหาจากเว็บ..."}
        logger.info(f"grade_docs: {len(docs)} docs found — proceeding to generate")
        return {"web_search_needed": False, "used_web_search": False,
                "status": "✅ พบข้อมูลอ้างอิงในคลังความรู้"}

    def _route_after_grade(self, state: AgentState) -> str:
        """Routing function for conditional edge after grade_docs."""
        return "web_search" if state.get("web_search_needed") else "generate"

    def node_web_search(self, state: AgentState) -> Dict[str, Any]:
        """Fallback: search the web using DuckDuckGo when local docs are insufficient."""
        try:
            from duckduckgo_search import DDGS
            from langchain_core.documents import Document
            query = state.get("expanded_query") or state["question"]
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=4))
            snippets = []
            for r in results:
                body = r.get("body", "")
                href = r.get("href", "")
                if body:
                    snippets.append(f"{body}\n[URL: {href}]")
            combined = "\n\n".join(snippets) or "No web results found."
            web_doc = Document(
                page_content=combined,
                metadata={"source": "DuckDuckGo Web Search", "page": 0, "relevance_score": None}
            )
            logger.info(f"web_search: fetched {len(results)} results")
            return {"documents": [web_doc], "used_web_search": True,
                    "status": "🌐 ใช้ผลการค้นหาจากเว็บ (DuckDuckGo)"}
        except Exception as e:
            logger.error(f"web_search failed: {e}")
            from langchain_core.documents import Document
            return {"documents": [Document(page_content="Web search unavailable.",
                                           metadata={"source": "Error", "page": 0})],
                    "used_web_search": True, "status": "⚠️ Web search ล้มเหลว"}

    def query_stream(self, prompt: str, filter_folder: str = None):
        """[Phase 2] Yields (gen_chunk, docs, used_web) — caller uses used_web for badge + analytics."""
        if not self.graph:
            yield "System not ready.", [], False
            return
        inputs = {
            "question": prompt,
            "documents": [],
            "filter_folder": filter_folder,
            "web_search_needed": False,
            "used_web_search": False,
        }
        try:
            final_used_web = False
            for output in self.graph.stream(inputs):
                for key, value in output.items():
                    if value.get("used_web_search"):
                        final_used_web = True
                    if "generation" in value:
                        yield value["generation"], value.get("documents", []), final_used_web
        except Exception as e:
            error_msg = str(e).lower()
            if any(kw in error_msg for kw in ["out of memory", "cuda error", "resource allocation", "exit code 2"]):
                yield "⚠️ **Error: Hardware Resource Limit (GPU/CUDA).**\n\nระบบ Ollama เกิดการขัดข้องเนื่องจากทรัพยากรเครื่องไม่เพียงพอ (Exit Code 2)\n\n**วิธีแก้ไขที่แนะนำ:**\n1. ปิดหน้าต่าง Chrome/Browser ที่เปิดค้างไว้เยอะๆ\n2. ปิดโปรแกรมอื่นๆ ที่ใช้การ์ดจอ\n3. **Restart Ollama Desktop** (ปิดแล้วเปิดใหม่)\n4. ลองพิมพ์คำถามที่สั้นและกระชับขึ้น\n\n*(ระบบได้จำกัดการใช้ทรัพยากรขั้นสูงสุดแล้ว หากยังพบปัญหา โปรดลองรีสตาร์ทคอมพิวเตอร์)*", []
            else:
                yield f"⚠️ **An error occurred:** {str(e)}", []
