"""
Enhanced FastAPI Server for Course Materials RAG System
Run with: uvicorn api:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os
import sys
import re
import torch
from contextlib import asynccontextmanager
import shutil
import json
from datetime import datetime
import warnings
import logging
import asyncio

# Suppress warnings
warnings.filterwarnings('ignore')
logging.getLogger("pypdf").setLevel(logging.ERROR)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

try:
    from dotenv import load_dotenv
    load_dotenv()
    
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_groq import ChatGroq
    from langchain_core.prompts import PromptTemplate
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import PyPDFLoader, TextLoader
    import yt_dlp
    
except ImportError as e:
    print(f"❌ Missing package: {e}")
    print("💡 Install: pip install fastapi uvicorn python-dotenv langchain-huggingface langchain-community langchain-groq faiss-cpu torch pypdf yt-dlp")
    sys.exit(1)

# ========================================
# GLOBAL VARIABLES
# ========================================
vectorstore = None
llm = None
embedding_function = None
text_splitter = None

COURSES_DIR = "courses"
METADATA_FILE = "course_metadata.json"
DB_FOLDER = "faiss_course_index"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Use multilingual embeddings
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

os.makedirs(COURSES_DIR, exist_ok=True)

# ========================================
# HELPER FUNCTIONS
# ========================================

def load_metadata() -> Dict:
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"courses": {}}

def save_metadata(metadata: Dict):
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

def extract_youtube_id(url: str) -> Optional[str]:
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
        r'youtube\.com\/embed\/([^&\n?#]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_youtube_content(video_id: str) -> Dict:
    """Get YouTube transcript and metadata using yt-dlp"""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'fr'],
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            transcript = None
            
            # Try manual subtitles first
            if 'subtitles' in info:
                for lang in ['en', 'fr']:
                    if lang in info['subtitles']:
                        sub_url = info['subtitles'][lang][0]['url']
                        import urllib.request
                        with urllib.request.urlopen(sub_url) as response:
                            content = response.read().decode('utf-8')
                            lines = [line for line in content.split('\n') 
                                   if not line.startswith('WEBVTT') 
                                   and not '-->' in line
                                   and line.strip()]
                            transcript = ' '.join(lines)
                            break
            
            # Try auto captions
            if not transcript and 'automatic_captions' in info:
                for lang in ['en', 'fr']:
                    if lang in info['automatic_captions']:
                        sub_url = info['automatic_captions'][lang][0]['url']
                        import urllib.request
                        with urllib.request.urlopen(sub_url) as response:
                            content = response.read().decode('utf-8')
                            lines = [line for line in content.split('\n') 
                                   if not line.startswith('WEBVTT') 
                                   and not '-->' in line
                                   and line.strip()]
                            transcript = ' '.join(lines)
                            break
            
            return {
                'transcript': transcript,
                'title': info.get('title', ''),
                'description': info.get('description', ''),
                'duration': info.get('duration', 0),
                'channel': info.get('uploader', '')
            }
            
    except Exception as e:
        print(f"⚠️ YouTube extraction failed: {e}")
        return {}

# ========================================
# DOCUMENT LOADERS
# ========================================

def load_pdf(file_path: str, course_id: str, title: str = "") -> List[Document]:
    """Load PDF with suppressed warnings"""
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    
    for i, doc in enumerate(docs):
        doc.metadata.update({
            "source": file_path,
            "course_id": course_id,
            "material_type": "pdf",
            "title": title or os.path.basename(file_path),
            "page": i + 1
        })
    
    return docs

def load_youtube(url: str, course_id: str, title: str = "") -> List[Document]:
    """Load YouTube video content"""
    video_id = extract_youtube_id(url)
    if not video_id:
        return []
    
    content_data = get_youtube_content(video_id)
    
    if not content_data:
        return []
    
    # Build content
    content_parts = []
    if content_data.get('title'):
        content_parts.append(f"Title: {content_data['title']}")
    if content_data.get('transcript'):
        content_parts.append(f"Transcript: {content_data['transcript']}")
    elif content_data.get('description'):
        content_parts.append(f"Description: {content_data['description']}")
    
    if not content_parts:
        return []
    
    doc = Document(
        page_content="\n\n".join(content_parts),
        metadata={
            "source": url,
            "course_id": course_id,
            "material_type": "video",
            "title": title or content_data.get('title', f"Video {video_id}"),
            "video_id": video_id,
            "duration": content_data.get('duration', 0),
            "channel": content_data.get('channel', '')
        }
    )
    
    return [doc]

def load_text_file(file_path: str, course_id: str, title: str = "") -> List[Document]:
    """Load text file"""
    loader = TextLoader(file_path, encoding='utf-8')
    docs = loader.load()
    
    for doc in docs:
        doc.metadata.update({
            "source": file_path,
            "course_id": course_id,
            "material_type": "text",
            "title": title or os.path.basename(file_path)
        })
    
    return docs

# ========================================
# HYBRID RETRIEVER
# ========================================

class HybridRetriever:
    """Enhanced retrieval with semantic + MMR"""
    
    def __init__(self, vectorstore, course_id: str = None):
        self.vectorstore = vectorstore
        self.course_id = course_id
    
    def retrieve(self, query: str, k: int = 15) -> List[Document]:
        """Retrieve documents, falling back to global search if course filter is too strict.

        This is important when the existing FAISS index was built with slightly
        different course_id metadata (for example, older courses or accented IDs):
        in that case, a strict filter would return 0 chunks even though the
        database actually contains relevant documents.
        """

        def _search(filter_dict):
            all_docs = []
            seen = set()

            # Strategy 1: Semantic search
            try:
                docs = self.vectorstore.similarity_search(
                    query, k=k * 2, filter=filter_dict
                )
                for doc in docs:
                    h = hash(doc.page_content)
                    if h not in seen:
                        seen.add(h)
                        all_docs.append((doc, 1.0))
            except Exception as e:
                print(f"⚠️ Semantic search failed (filter={filter_dict}): {e}")

            # Strategy 2: MMR for diversity
            try:
                docs = self.vectorstore.max_marginal_relevance_search(
                    query, k=k, fetch_k=k * 5, filter=filter_dict
                )
                for doc in docs:
                    h = hash(doc.page_content)
                    if h not in seen:
                        seen.add(h)
                        all_docs.append((doc, 0.9))
            except Exception as e:
                print(f"⚠️ MMR failed (filter={filter_dict}): {e}")

            all_docs.sort(key=lambda x: x[1], reverse=True)
            return [doc for doc, score in all_docs[:k]]

        # Try with course filter first
        filter_dict = {"course_id": self.course_id} if self.course_id else None
        docs = _search(filter_dict)

        # If nothing found and we used a filter, fall back to global search
        if not docs and filter_dict is not None:
            print(
                f"ℹ️ No documents found with course filter {filter_dict}; "
                "falling back to global search without course filter."
            )
            docs = _search(None)

        return docs

# ========================================
# PYDANTIC MODELS
# ========================================

class CourseCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    category: Optional[str] = "General"

class MaterialAdd(BaseModel):
    url: str
    title: Optional[str] = ""

class QueryRequest(BaseModel):
    query: str
    course_id: Optional[str] = None
    max_chunks: Optional[int] = 15
    stream: Optional[bool] = False

class DocumentInfo(BaseModel):
    content: str
    metadata: Dict[str, Any]
    relevance_score: Optional[float] = None

class QueryResponse(BaseModel):
    answer: str
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    num_chunks: int
    sources: List[str]
    processing_time: float

class HealthResponse(BaseModel):
    status: str
    database_loaded: bool
    llm_connected: bool
    device: str
    embedding_model: str
    total_courses: int
    total_materials: int

class CourseInfo(BaseModel):
    id: str
    name: str
    description: str
    category: str
    materials_count: int
    created_at: str

class MaterialInfo(BaseModel):
    title: str
    type: str
    path: str
    added_at: str

class RebuildResponse(BaseModel):
    message: str
    total_chunks: int
    courses_processed: int
    materials_processed: int

# ========================================
# LIFESPAN
# ========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global vectorstore, llm, embedding_function, text_splitter
    
    print("🚀 Starting Enhanced Course RAG API...")
    print(f"📱 Device: {DEVICE}")
    
    print("📄 Loading embeddings...")
    embedding_function = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={'device': DEVICE}
    )
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""]
    )
    
    print(f"💾 Loading FAISS index...")
    try:
        vectorstore = FAISS.load_local(
            DB_FOLDER,
            embedding_function,
            allow_dangerous_deserialization=True
        )
        print("✅ Database loaded")
    except Exception as e:
        print(f"⚠️ No existing database: {e}")
        vectorstore = None
    
    print("🔌 Connecting to Groq...")
    try:
        llm = ChatGroq(
            temperature=0,
            model_name="llama-3.3-70b-versatile",
            max_tokens=2048
        )
        print("✅ LLM connected")
    except Exception as e:
        print(f"❌ LLM connection failed: {e}")
        llm = None
    
    print("🎉 API Ready!\n")
    
    yield
    
    print("👋 Shutting down...")

# ========================================
# FASTAPI APP
# ========================================

app = FastAPI(
    title="Enhanced Course RAG API",
    description="Production-ready RAG system with multilingual support",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================
# ENDPOINTS
# ========================================

@app.get("/", response_model=HealthResponse)
async def health_check():
    """Health check with system status"""
    metadata = load_metadata()
    total_materials = sum(len(c["materials"]) for c in metadata["courses"].values())
    
    return {
        "status": "online",
        "database_loaded": vectorstore is not None,
        "llm_connected": llm is not None,
        "device": DEVICE,
        "embedding_model": EMBEDDING_MODEL,
        "total_courses": len(metadata["courses"]),
        "total_materials": total_materials
    }

@app.post("/courses", status_code=201)
async def create_course(course: CourseCreate):
    """Create a new course"""
    metadata = load_metadata()
    course_id = course.name.lower().replace(" ", "_").replace("é", "e").replace("è", "e")
    
    if course_id in metadata["courses"]:
        raise HTTPException(status_code=400, detail="Course already exists")
    
    metadata["courses"][course_id] = {
        "name": course.name,
        "description": course.description,
        "category": course.category,
        "materials": [],
        "created_at": datetime.now().isoformat()
    }
    save_metadata(metadata)
    
    return {"course_id": course_id, "message": f"Course '{course.name}' created"}

@app.get("/courses", response_model=List[CourseInfo])
async def list_courses():
    """List all courses with details"""
    metadata = load_metadata()
    
    return [
        CourseInfo(
            id=cid,
            name=info["name"],
            description=info["description"],
            category=info["category"],
            materials_count=len(info["materials"]),
            created_at=info["created_at"]
        )
        for cid, info in metadata["courses"].items()
    ]

@app.get("/courses/{course_id}", response_model=Dict)
async def get_course_details(course_id: str):
    """Get detailed course information"""
    metadata = load_metadata()
    
    if course_id not in metadata["courses"]:
        raise HTTPException(status_code=404, detail="Course not found")
    
    course_info = metadata["courses"][course_id]
    
    return {
        "id": course_id,
        "name": course_info["name"],
        "description": course_info["description"],
        "category": course_info["category"],
        "created_at": course_info["created_at"],
        "materials": [
            MaterialInfo(
                title=m["title"],
                type=m["type"],
                path=m["path"],
                added_at=m["added_at"]
            )
            for m in course_info["materials"]
        ]
    }

@app.post("/courses/{course_id}/materials/upload")
async def upload_material(
    course_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form("")
):
    """Upload PDF or text file"""
    metadata = load_metadata()
    
    if course_id not in metadata["courses"]:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Validate file type
    if not file.filename.endswith(('.pdf', '.txt', '.md')):
        raise HTTPException(
            status_code=400,
            detail="Only PDF, TXT, and MD files are supported"
        )
    
    # Save file
    course_dir = os.path.join(COURSES_DIR, course_id)
    os.makedirs(course_dir, exist_ok=True)
    
    file_path = os.path.join(course_dir, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Determine type
    mat_type = "pdf" if file.filename.endswith('.pdf') else "text"
    
    # Add to metadata
    metadata["courses"][course_id]["materials"].append({
        "path": file_path,
        "type": mat_type,
        "title": title or file.filename,
        "added_at": datetime.now().isoformat()
    })
    save_metadata(metadata)
    
    return {
        "message": f"File '{file.filename}' uploaded successfully",
        "file_path": file_path,
        "type": mat_type
    }

@app.post("/courses/{course_id}/materials/youtube")
async def add_youtube_video(course_id: str, material: MaterialAdd):
    """Add YouTube video to course"""
    metadata = load_metadata()
    
    if course_id not in metadata["courses"]:
        raise HTTPException(status_code=404, detail="Course not found")
    
    video_id = extract_youtube_id(material.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    # Get video info
    content_data = get_youtube_content(video_id)
    
    if not content_data:
        raise HTTPException(
            status_code=400,
            detail="Could not extract video content. Video may be unavailable or private."
        )
    
    title = material.title or content_data.get('title', f"YouTube Video {video_id}")
    
    metadata["courses"][course_id]["materials"].append({
        "path": material.url,
        "type": "video",
        "title": title,
        "added_at": datetime.now().isoformat()
    })
    save_metadata(metadata)
    
    has_transcript = bool(content_data.get('transcript'))
    
    return {
        "message": f"YouTube video '{title}' added",
        "video_id": video_id,
        "has_transcript": has_transcript,
        "channel": content_data.get('channel', 'Unknown')
    }

@app.post("/rebuild", response_model=RebuildResponse)
async def rebuild_database(background_tasks: BackgroundTasks):
    """Rebuild vector database from all materials"""
    global vectorstore
    
    if embedding_function is None or text_splitter is None:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    try:
        import time
        start_time = time.time()
        
        metadata = load_metadata()
        all_docs = []
        courses_processed = 0
        materials_processed = 0
        
        for course_id, info in metadata["courses"].items():
            courses_processed += 1
            
            for material in info["materials"]:
                try:
                    mat_path = material["path"]
                    mat_type = material["type"]
                    title = material["title"]
                    
                    if mat_type == "pdf":
                        docs = load_pdf(mat_path, course_id, title)
                    elif mat_type == "video":
                        docs = load_youtube(mat_path, course_id, title)
                    elif mat_type == "text":
                        docs = load_text_file(mat_path, course_id, title)
                    else:
                        continue
                    
                    if docs:
                        chunks = text_splitter.split_documents(docs)
                        all_docs.extend(chunks)
                        materials_processed += 1
                        
                except Exception as e:
                    print(f"Error processing {mat_path}: {e}")
        
        if not all_docs:
            raise HTTPException(
                status_code=400,
                detail="No documents to index. Add materials first."
            )
        
        vectorstore = FAISS.from_documents(all_docs, embedding_function)
        vectorstore.save_local(DB_FOLDER)
        
        elapsed = time.time() - start_time
        
        return RebuildResponse(
            message=f"Database rebuilt in {elapsed:.2f}s",
            total_chunks=len(all_docs),
            courses_processed=courses_processed,
            materials_processed=materials_processed
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {str(e)}")

@app.post("/query", response_model=QueryResponse)
async def query_materials(request: QueryRequest):
    """Query course materials with enhanced retrieval"""
    if vectorstore is None:
        raise HTTPException(
            status_code=503,
            detail="Database not loaded. Rebuild database first: POST /rebuild"
        )
    
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="LLM not connected. Check GROQ_API_KEY environment variable."
        )
    
    try:
        import time
        start_time = time.time()
        
        # Detect course
        course_id = request.course_id
        course_name = None
        
        if not course_id:
            metadata = load_metadata()
            for cid, info in metadata["courses"].items():
                if info["name"].lower() in request.query.lower():
                    course_id = cid
                    course_name = info["name"]
                    break
        else:
            metadata = load_metadata()
            if course_id in metadata["courses"]:
                course_name = metadata["courses"][course_id]["name"]
        
        # Retrieve documents
        retriever = HybridRetriever(vectorstore, course_id)
        docs = retriever.retrieve(request.query, k=request.max_chunks)
        
        if not docs:
            return QueryResponse(
                answer="I couldn't find relevant information in the course materials for your question.",
                course_id=course_id,
                course_name=course_name,
                num_chunks=0,
                sources=[],
                processing_time=time.time() - start_time
            )
        
        # Build context
        context = "\n\n---\n\n".join([
            f"[{doc.metadata.get('title', 'Unknown')}]\n{doc.page_content}"
            for doc in docs[:10]
        ])
        
        # Enhanced prompt
        template = """You are an expert educational AI assistant with deep knowledge of course materials.

**Context from course materials:**
{context}

**Student Question:** {question}

**Instructions:**
1. Provide a clear, comprehensive answer using ONLY the context above
2. Include specific examples, definitions, formulas, or code when present
3. Structure your answer with clear explanations
4. Reference materials when helpful (e.g., "According to the lecture notes...")
5. If information is missing, state: "I don't have this information in the provided materials"
6. Be educational, detailed, and encouraging

**Answer:**"""
        
        prompt = PromptTemplate(
            template=template,
            input_variables=["context", "question"]
        )
        
        # Get answer
        response = llm.invoke(prompt.format(context=context, question=request.query))
        
        # Get unique sources
        sources = list(set(doc.metadata.get('title', 'Unknown') for doc in docs))
        
        return QueryResponse(
            answer=response.content,
            course_id=course_id,
            course_name=course_name,
            num_chunks=len(docs),
            sources=sources,
            processing_time=time.time() - start_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.delete("/courses/{course_id}")
async def delete_course(course_id: str):
    """Delete course and all its materials"""
    metadata = load_metadata()
    
    if course_id not in metadata["courses"]:
        raise HTTPException(status_code=404, detail="Course not found")
    
    course_name = metadata["courses"][course_id]["name"]
    
    # Delete files
    course_dir = os.path.join(COURSES_DIR, course_id)
    if os.path.exists(course_dir):
        shutil.rmtree(course_dir)
    
    # Remove from metadata
    del metadata["courses"][course_id]
    save_metadata(metadata)
    
    return {
        "message": f"Course '{course_name}' deleted successfully",
        "course_id": course_id
    }

@app.get("/stats")
async def get_statistics():
    """Get system statistics"""
    metadata = load_metadata()
    
    stats = {
        "total_courses": len(metadata["courses"]),
        "courses_by_category": {},
        "total_materials": 0,
        "materials_by_type": {"pdf": 0, "video": 0, "text": 0},
        "database_size_mb": 0
    }
    
    for course_info in metadata["courses"].values():
        category = course_info["category"]
        stats["courses_by_category"][category] = \
            stats["courses_by_category"].get(category, 0) + 1
        
        for material in course_info["materials"]:
            stats["total_materials"] += 1
            mat_type = material["type"]
            if mat_type in stats["materials_by_type"]:
                stats["materials_by_type"][mat_type] += 1
    
    # Get database size
    if os.path.exists(DB_FOLDER):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(DB_FOLDER):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        stats["database_size_mb"] = round(total_size / (1024 * 1024), 2)
    
    return stats

# ========================================
# RUN
# ========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )