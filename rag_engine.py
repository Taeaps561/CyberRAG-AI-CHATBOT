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
        
        # Stats
        self.doc_count = 0
        self.last_sync = "Never"
        self.available_folders = []
        
        self.llm = ChatOllama(
            model=self.model_name, 
            temperature=0,
            base_url="http://127.0.0.1:11434",
            timeout=60,
            num_ctx=512,  # Ultra-conservative to fix cudaMalloc/OOM errors
            num_thread=1  # Maximum stability
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

    def init_system(self) -> Tuple[Optional[Any], str]:
        if not self.check_ollama():
            return None, "Ollama is not responding."
        self.scan_data_stats()
        try:
            embeddings = OllamaEmbeddings(model=self.embed_model, base_url="http://127.0.0.1:11434")
            if os.path.exists(os.path.join(self.db_dir, "chroma.sqlite3")):
                self.vectorstore = Chroma(persist_directory=self.db_dir, embedding_function=embeddings)
                self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 8}) # Increased K
                self._build_graph()
                threading.Thread(target=self._init_advanced_features, args=(embeddings,), daemon=True).start()
                return self.graph, "Success"
            return None, "Database not found."
        except Exception as e:
            return None, f"Error: {e}"

    def scan_data_stats(self, filter_folder: str = "ทั้งหมด"):
        try:
            filtered_count = 0
            folders = set()
            newest_time = 0
            for root, dirs, files in os.walk(self.data_dir):
                rel_path = os.path.relpath(root, self.data_dir)
                if rel_path != "." and "\\" not in rel_path and "/" not in rel_path:
                    folders.add(rel_path)
                if filter_folder == "ทั้งหมด" or filter_folder in root:
                    for file in files:
                        if file.endswith(('.pdf', '.txt')):
                            filtered_count += 1
                            mtime = os.path.getmtime(os.path.join(root, file))
                            if mtime > newest_time: newest_time = mtime
            self.doc_count = filtered_count
            self.available_folders = sorted(list(folders))
            if newest_time > 0: self.last_sync = datetime.fromtimestamp(newest_time).strftime("%Y-%m-%d %H:%M")
        except Exception as e: logger.error(f"Stat scan failed: {e}")

    def _init_advanced_features(self, embeddings):
        try:
            docs = []
            allowed = { "pdf": (PyPDFLoader, "**/*.pdf"), "txt": (TextLoader, "**/*.txt") }
            for ext, (loader_cls, glob) in allowed.items():
                loader = DirectoryLoader(self.data_dir, glob=glob, loader_cls=loader_cls)
                docs.extend(loader.load())
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
        except Exception as e: logger.error(f"Stage 2 Failed: {e}")

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("rewrite", self.node_rewrite)
        workflow.add_node("retrieve", self.node_retrieve)
        workflow.add_node("generate", self.node_generate)
        workflow.set_entry_point("rewrite")
        workflow.add_edge("rewrite", "retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", END)
        self.graph = workflow.compile()

    def node_rewrite(self, state: AgentState) -> Dict[str, Any]:
        """Expands the query to get better retrieval results."""
        prompt = f"ขยายความคำถามต่อไปนี้ให้เป็นประโยคคำถามที่ชัดเจนสำหรับการค้นหาข้อมูลทางเทคนิค (ตอบแค่ประโยคที่ขยายแล้วเท่านั้น): {state['question']}"
        expanded = self.llm.invoke(prompt).content
        return {"expanded_query": expanded, "status": "🧠 กำลังวิเคราะห์คำถาม..."}

    def node_retrieve(self, state: AgentState) -> Dict[str, Any]:
        query = state.get("expanded_query", state["question"])
        folder_filter = state.get("filter_folder")
        documents = self.retriever.invoke(query)
        if folder_filter and folder_filter != "ทั้งหมด":
            documents = [d for d in documents if folder_filter in d.metadata.get("source", "")]
        return {"documents": documents, "status": "🔍 ค้นหาข้อมูลทางเทคนิค..."}

    def node_generate(self, state: AgentState) -> Dict[str, Any]:
        context = "\n\n".join([f"[Source: {os.path.basename(d.metadata.get('source',''))}]\n{d.page_content}" for d in state["documents"]])
        template = f"{self.system_prompt}\n\nContext:\n{{context}}\n\nQuestion: {{question}}\nAnswer:"
        prompt = PromptTemplate(template=template, input_variables=["context", "question"])
        chain = prompt | self.llm | StrOutputParser()
        generation = chain.invoke({"context": context, "question": state["question"]})
        return {"generation": generation, "status": "เสร็จสิ้น"}

    def query_stream(self, prompt: str, filter_folder: str = None):
        if not self.graph:
            yield "System not ready.", []
            return
        inputs = {"question": prompt, "documents": [], "filter_folder": filter_folder}
        try:
            for output in self.graph.stream(inputs):
                for key, value in output.items():
                    if "generation" in value:
                        yield value["generation"], value.get("documents", [])
        except Exception as e:
            error_msg = str(e).lower()
            if any(kw in error_msg for kw in ["out of memory", "cuda error", "resource allocation", "exit code 2"]):
                yield "⚠️ **Error: Hardware Resource Limit (GPU/CUDA).**\n\nระบบ Ollama เกิดการขัดข้องเนื่องจากทรัพยากรเครื่องไม่เพียงพอ (Exit Code 2)\n\n**วิธีแก้ไขที่แนะนำ:**\n1. ปิดหน้าต่าง Chrome/Browser ที่เปิดค้างไว้เยอะๆ\n2. ปิดโปรแกรมอื่นๆ ที่ใช้การ์ดจอ\n3. **Restart Ollama Desktop** (ปิดแล้วเปิดใหม่)\n4. ลองพิมพ์คำถามที่สั้นและกระชับขึ้น\n\n*(ระบบได้จำกัดการใช้ทรัพยากรขั้นสูงสุดแล้ว หากยังพบปัญหา โปรดลองรีสตาร์ทคอมพิวเตอร์)*", []
            else:
                yield f"⚠️ **An error occurred:** {str(e)}", []
