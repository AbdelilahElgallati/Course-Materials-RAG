print("✅ Course RAG System Starting...")
import os
import sys
import re
import torch
from pathlib import Path
import warnings
import logging

# Suppress warnings early
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
    
    import json
    from datetime import datetime
    from typing import List, Dict, Optional, Tuple
    import yt_dlp
    
except ImportError as e:
    print(f"❌ Missing package: {e}")
    print("💡 Install: pip install langchain python-dotenv langchain-huggingface langchain-community langchain-groq faiss-cpu torch pypdf yt-dlp")
    sys.exit(1)

# -----------------------------
# CONFIGURATION
# -----------------------------
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")

COURSES_DIR = "courses"
METADATA_FILE = "course_metadata.json"
DB_FOLDER = "faiss_course_index"
os.makedirs(COURSES_DIR, exist_ok=True)

# Improved embedding model (better for multilingual, including French)
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# -----------------------------
# YOUTUBE TRANSCRIPT - ENHANCED
# -----------------------------

def get_youtube_transcript_ytdlp(video_id: str) -> Optional[str]:
    """Get transcript using yt-dlp (more reliable)"""
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
            
            # Try to get subtitles
            if 'subtitles' in info:
                for lang in ['en', 'fr']:
                    if lang in info['subtitles']:
                        sub_url = info['subtitles'][lang][0]['url']
                        import urllib.request
                        with urllib.request.urlopen(sub_url) as response:
                            content = response.read().decode('utf-8')
                            # Clean VTT format
                            lines = [line for line in content.split('\n') 
                                   if not line.startswith('WEBVTT') 
                                   and not '-->' in line
                                   and line.strip()]
                            return ' '.join(lines)
            
            # Try automatic captions
            if 'automatic_captions' in info:
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
                            return ' '.join(lines)
                            
    except Exception as e:
        print(f"  ⚠️ yt-dlp failed: {e}")
    
    return None

def get_youtube_metadata(video_id: str) -> Dict:
    """Get video metadata for better context"""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {'quiet': True, 'no_warnings': True}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', ''),
                'description': info.get('description', ''),
                'duration': info.get('duration', 0),
                'channel': info.get('uploader', '')
            }
    except:
        return {}

def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
        r'youtube\.com\/embed\/([^&\n?#]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

# -----------------------------
# DOCUMENT LOADERS
# -----------------------------

def load_pdf(file_path: str, course_id: str, title: str = "") -> List[Document]:
    """Load PDF with metadata"""
    print(f"📄 Loading PDF: {file_path}")
    
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
    
    print(f"  ✅ Loaded {len(docs)} pages")
    return docs

def load_youtube(url: str, course_id: str, title: str = "") -> List[Document]:
    """Load YouTube video with metadata"""
    print(f"🎥 Loading YouTube: {url}")
    
    video_id = extract_youtube_id(url)
    if not video_id:
        print("  ❌ Invalid YouTube URL")
        return []
    
    # Get transcript
    transcript = get_youtube_transcript_ytdlp(video_id)
    
    # Get metadata
    metadata = get_youtube_metadata(video_id)
    
    if not transcript and not metadata.get('description'):
        print(f"  ⚠️ No content available for {video_id}")
        return []
    
    # Combine transcript and description
    content = []
    if metadata.get('title'):
        content.append(f"Title: {metadata['title']}")
    if transcript:
        content.append(f"Transcript: {transcript}")
    elif metadata.get('description'):
        content.append(f"Description: {metadata['description']}")
    
    if not content:
        return []
    
    doc = Document(
        page_content="\n\n".join(content),
        metadata={
            "source": url,
            "course_id": course_id,
            "material_type": "video",
            "title": title or metadata.get('title', f"Video {video_id}"),
            "video_id": video_id,
            "duration": metadata.get('duration', 0),
            "channel": metadata.get('channel', '')
        }
    )
    
    print(f"  ✅ Extracted {len(doc.page_content)} characters")
    return [doc]

def load_text_file(file_path: str, course_id: str, title: str = "") -> List[Document]:
    """Load text file"""
    print(f"📝 Loading text: {file_path}")
    
    loader = TextLoader(file_path, encoding='utf-8')
    docs = loader.load()
    
    for doc in docs:
        doc.metadata.update({
            "source": file_path,
            "course_id": course_id,
            "material_type": "text",
            "title": title or os.path.basename(file_path)
        })
    
    print(f"  ✅ Loaded {len(docs[0].page_content)} characters")
    return docs

# -----------------------------
# METADATA MANAGEMENT
# -----------------------------

def load_metadata() -> Dict:
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"courses": {}}

def save_metadata(metadata: Dict):
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

def add_course(name: str, description: str = "", category: str = "General") -> str:
    metadata = load_metadata()
    course_id = name.lower().replace(" ", "_")
    
    if course_id not in metadata["courses"]:
        metadata["courses"][course_id] = {
            "name": name,
            "description": description,
            "category": category,
            "materials": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(metadata)
        print(f"✅ Added course: {name}")
    return course_id

def add_material(course_id: str, path: str, mat_type: str, title: str = ""):
    metadata = load_metadata()
    
    if course_id not in metadata["courses"]:
        print(f"❌ Course {course_id} not found")
        return
    
    metadata["courses"][course_id]["materials"].append({
        "path": path,
        "type": mat_type,
        "title": title or os.path.basename(path),
        "added_at": datetime.now().isoformat()
    })
    
    save_metadata(metadata)
    print(f"✅ Added {mat_type}: {title or path}")

# -----------------------------
# ADVANCED RETRIEVER
# -----------------------------

class HybridRetriever:
    """Hybrid retrieval with semantic + keyword matching"""
    
    def __init__(self, vectorstore, course_id: str = None):
        self.vectorstore = vectorstore
        self.course_id = course_id
    
    def retrieve(self, query: str, k: int = 10) -> List[Document]:
        """Retrieve with multiple strategies"""
        all_docs = []
        seen = set()
        
        # Strategy 1: Semantic search
        try:
            filter_dict = {"course_id": self.course_id} if self.course_id else None
            docs = self.vectorstore.similarity_search(
                query,
                k=k*2,
                filter=filter_dict
            )
            
            for doc in docs:
                h = hash(doc.page_content)
                if h not in seen:
                    seen.add(h)
                    all_docs.append((doc, 1.0))
        except Exception as e:
            print(f"⚠️ Semantic search failed: {e}")
        
        # Strategy 2: MMR for diversity
        try:
            filter_dict = {"course_id": self.course_id} if self.course_id else None
            docs = self.vectorstore.max_marginal_relevance_search(
                query,
                k=k,
                fetch_k=k*5,
                filter=filter_dict
            )
            
            for doc in docs:
                h = hash(doc.page_content)
                if h not in seen:
                    seen.add(h)
                    all_docs.append((doc, 0.8))
        except Exception as e:
            print(f"⚠️ MMR search failed: {e}")
        
        # Sort by score
        all_docs.sort(key=lambda x: x[1], reverse=True)
        
        print(f"📊 Retrieved {len(all_docs)} unique chunks")
        return [doc for doc, score in all_docs[:k]]

# -----------------------------
# MAIN APPLICATION
# -----------------------------

def main():
    print("\n🎓 Enhanced Course RAG System\n")
    
    # Initialize embeddings
    print("📄 Initializing embeddings...")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={'device': DEVICE}
    )
    
    # Text splitter with better chunking
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        length_function=len,
        separators=["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""]
    )
    
    def build_database():
        print("\n⚙️ Building database...")
        metadata = load_metadata()
        all_docs = []
        
        for course_id, info in metadata["courses"].items():
            print(f"\n📚 Processing: {info['name']}")
            
            for material in info["materials"]:
                try:
                    mat_type = material["type"]
                    mat_path = material["path"]
                    title = material["title"]
                    
                    if mat_type == "pdf":
                        docs = load_pdf(mat_path, course_id, title)
                    elif mat_type in ["url", "video"]:
                        docs = load_youtube(mat_path, course_id, title)
                    elif mat_type == "text":
                        docs = load_text_file(mat_path, course_id, title)
                    else:
                        continue
                    
                    if docs:
                        chunks = text_splitter.split_documents(docs)
                        all_docs.extend(chunks)
                        print(f"  ✅ Added {len(chunks)} chunks")
                        
                except Exception as e:
                    print(f"  ❌ Error: {e}")
        
        if not all_docs:
            print("\n⚠️ No documents to index")
            return None
        
        print(f"\n📊 Total chunks: {len(all_docs)}")
        print("🔨 Building FAISS index...")
        
        vectorstore = FAISS.from_documents(all_docs, embeddings)
        vectorstore.save_local(DB_FOLDER)
        print("✅ Database ready!\n")
        
        return vectorstore
    
    # Load or build database
    if os.path.exists(DB_FOLDER):
        print(f"✅ Loading index from {DB_FOLDER}...")
        try:
            vectorstore = FAISS.load_local(
                DB_FOLDER,
                embeddings,
                allow_dangerous_deserialization=True
            )
        except:
            vectorstore = build_database()
    else:
        vectorstore = build_database()
    
    if vectorstore is None:
        print("\n💡 Quick Start:")
        print("1. add course Data Science | AI Course | Tech")
        print("2. add pdf data_science path/to/file.pdf")
        print("3. rebuild")
        return
    
    # LLM Setup
    print("🔌 Connecting to Groq...")
    llm = ChatGroq(
        temperature=0,
        model=GROQ_MODEL,
        max_tokens=2048
    )
    
    # Enhanced prompt
    template = """You are an expert educational AI assistant with deep knowledge of the course materials.

**Context from course materials:**
{context}

**Student Question:** {question}

**Instructions:**
1. Provide a clear, detailed answer using ONLY the context above
2. Include specific examples, formulas, or code if present in the context
3. If the context has relevant definitions, explain them
4. Reference specific materials when helpful (e.g., "According to Partie 3...")
5. If information is not in the context, clearly state: "I don't have information about this in the provided materials"
6. Be educational and encouraging

**Answer:**"""
    
    prompt = PromptTemplate(
        template=template,
        input_variables=["context", "question"]
    )
    
    # Interactive loop
    print("\n💬 System Ready!\n")
    print("📚 Commands:")
    print("  add course <name> | <description> | <category>")
    print("  add pdf <course_id> <file_path> [title]")
    print("  add url <course_id> <youtube_url> [title]")
    print("  add text <course_id> <file_path> [title]")
    print("  list courses")
    print("  rebuild")
    print("  exit/quit\n")
    print("🔍 Or just ask a question!\n")
    
    while True:
        try:
            user_input = input("💡 > ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["exit", "quit"]:
                print("\n👋 Goodbye!")
                break
            
            # Commands
            if user_input.lower().startswith("add course"):
                parts = user_input[10:].split("|")
                name = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else ""
                cat = parts[2].strip() if len(parts) > 2 else "General"
                add_course(name, desc, cat)
                continue
            
            if user_input.lower().startswith("add pdf"):
                parts = user_input[8:].split()
                if len(parts) >= 2:
                    add_material(parts[0], parts[1], "pdf", " ".join(parts[2:]))
                continue
            
            if user_input.lower().startswith("add url"):
                parts = user_input[8:].split()
                if len(parts) >= 2:
                    add_material(parts[0], parts[1], "video", " ".join(parts[2:]))
                continue
            
            if user_input.lower().startswith("add text"):
                parts = user_input[9:].split()
                if len(parts) >= 2:
                    add_material(parts[0], parts[1], "text", " ".join(parts[2:]))
                continue
            
            if user_input.lower() == "list courses":
                metadata = load_metadata()
                if metadata["courses"]:
                    print("\n📚 Available Courses:")
                    for cid, info in metadata["courses"].items():
                        print(f"\n  🎓 {info['name']} (ID: {cid})")
                        print(f"     📁 {len(info['materials'])} materials")
                else:
                    print("No courses found")
                continue
            
            if user_input.lower() == "rebuild":
                vectorstore = build_database()
                continue
            
            # Query processing
            if vectorstore is None:
                print("⚠️ Build database first: type 'rebuild'")
                continue
            
            query = user_input
            
            # Detect course
            metadata = load_metadata()
            course_id = None
            for cid, info in metadata["courses"].items():
                if info["name"].lower() in query.lower() or cid in query.lower():
                    course_id = cid
                    print(f"🎯 Searching in: {info['name']}")
                    break
            
            # Retrieve
            retriever = HybridRetriever(vectorstore, course_id)
            docs = retriever.retrieve(query, k=15)
            
            if not docs:
                print("💡 No relevant materials found")
                continue
            
            # Build context
            context = "\n\n---\n\n".join([
                f"[{doc.metadata.get('title', 'Unknown')}]\n{doc.page_content}"
                for doc in docs[:10]
            ])
            
            # Get answer
            print("⏳ Generating answer...", end="\r")
            response = llm.invoke(prompt.format(context=context, question=query))
            
            print(f"\n📖 Answer:\n{response.content}\n")
            print(f"📄 Sources: {len(docs)} chunks from {len(set(d.metadata.get('title') for d in docs))} materials")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()