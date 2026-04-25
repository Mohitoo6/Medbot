"""
MedBot RAG Pipeline — v3
========================
Handles PDF ingestion, chunking, embedding, vector storage, and retrieval
for the MedBot pharmaceutical chatbot with multiple medical reference sources.

Improvements in v3:
- Incremental ingestion (add new PDFs without re-processing existing ones)
- Batched page extraction with cooldown for thermal management on laptops
- OCR text cleaning for scanned PDFs
- Generalized for multiple medical reference books
- Enhanced system prompt with structured output instructions
- Query expansion for better retrieval coverage
"""

import os
import re
import hashlib
import logging
import time
from pathlib import Path

import fitz  # PyMuPDF
import chromadb
from chromadb.utils import embedding_functions
import glob
import pymupdf4llm
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────
DATA_DIR = os.path.dirname(__file__)
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "martindale_drugs"
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))
TOP_K = int(os.getenv("TOP_K", 7))   # Increased from 5 to 7 for better coverage
BATCH_PAGES = int(os.getenv("BATCH_PAGES", 50))  # Pages per extraction batch
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", 3))  # Pause between batches
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── OCR Text Cleaning ────────────────────────────────────────────

def clean_ocr_text(text: str) -> str:
    """Clean common OCR artifacts from scanned PDFs."""
    # Fix common OCR spacing issues
    text = re.sub(r'(\w)\s{2,}(\w)', r'\1 \2', text)  # Multiple spaces → single
    # Remove isolated single characters that are likely OCR noise
    text = re.sub(r'\n[a-zA-Z]\n', '\n', text)
    # Fix broken words (letter space letter pattern in middle of words)
    text = re.sub(r'(\w)\s([a-z])\s(\w)', r'\1\2\3', text)
    # Clean up excessive newlines
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text


# ── Markdown-Aware Ingestion & Chunking ─────────────────────────

def _split_md_to_chunks(md_text: str, filename: str) -> list[dict]:
    """Split markdown text into chunks with metadata. Shared by both extraction methods."""
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False
    )

    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    md_docs = md_splitter.split_text(md_text)
    all_chunks = []

    for i, doc in enumerate(md_docs):
        if len(doc.page_content) > CHUNK_SIZE:
            sub_docs = char_splitter.split_text(doc.page_content)
        else:
            sub_docs = [doc.page_content]

        for j, text_chunk in enumerate(sub_docs):
            if len(text_chunk.strip()) < 50:
                continue

            section = "General"
            if doc.metadata:
                headers = [str(v) for k, v in doc.metadata.items() if "Header" in k]
                if headers:
                    section = " > ".join(headers)

            chunk_id = hashlib.md5(f"{filename}_{i}_{j}_{text_chunk[:50]}".encode()).hexdigest()

            all_chunks.append({
                "id": chunk_id,
                "text": text_chunk,
                "metadata": {
                    "book": filename,
                    "section": section[:100],
                    "chunk_index": i,
                    "char_count": len(text_chunk),
                    "page": "N/A"
                }
            })

    return all_chunks


def chunk_documents_from_markdown(pdf_path: str) -> list[dict]:
    """Extract PDF to Markdown and chunk via headings (full extraction, no batching)."""
    filename = os.path.basename(pdf_path)
    logger.info(f"Extracting markdown from {filename} (This may take several minutes)...")

    try:
        md_text = pymupdf4llm.to_markdown(pdf_path)
    except Exception as e:
        logger.error(f"Failed to extract {filename}: {e}")
        return []

    logger.info(f"Extraction complete for {filename}. Splitting text...")
    md_text = clean_ocr_text(md_text)
    all_chunks = _split_md_to_chunks(md_text, filename)

    logger.info(f"Created {len(all_chunks)} chunks from {filename}")
    return all_chunks


def chunk_documents_batched(pdf_path: str) -> list[dict]:
    """
    Extract PDF to Markdown in page batches with cooldown pauses.
    Designed for large PDFs on thermally-constrained laptops (e.g. M2 Air).
    Processes BATCH_PAGES pages at a time, pausing COOLDOWN_SECONDS between batches.
    """
    import fitz as fitz_module
    filename = os.path.basename(pdf_path)

    doc = fitz_module.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    logger.info(f"Batched extraction: {filename} ({total_pages} pages, batch_size={BATCH_PAGES}, cooldown={COOLDOWN_SECONDS}s)")

    all_md_parts = []
    for batch_start in range(0, total_pages, BATCH_PAGES):
        batch_end = min(batch_start + BATCH_PAGES, total_pages)
        page_range = list(range(batch_start, batch_end))
        batch_num = (batch_start // BATCH_PAGES) + 1
        total_batches = (total_pages + BATCH_PAGES - 1) // BATCH_PAGES

        logger.info(f"  Batch {batch_num}/{total_batches}: pages {batch_start+1}-{batch_end} of {total_pages}")

        try:
            md_part = pymupdf4llm.to_markdown(pdf_path, pages=page_range)
            all_md_parts.append(md_part)
        except Exception as e:
            logger.error(f"  Failed batch {batch_num} ({filename} pages {batch_start+1}-{batch_end}): {e}")
            continue

        # Cooldown pause between batches (skip after last batch)
        if batch_end < total_pages:
            time.sleep(COOLDOWN_SECONDS)

    if not all_md_parts:
        logger.error(f"No content extracted from {filename}")
        return []

    full_md = "\n\n".join(all_md_parts)
    full_md = clean_ocr_text(full_md)

    logger.info(f"Extraction complete for {filename}. Total markdown: {len(full_md)} chars. Splitting...")
    all_chunks = _split_md_to_chunks(full_md, filename)

    logger.info(f"Created {len(all_chunks)} chunks from {filename}")
    return all_chunks


# ── Vector Store ─────────────────────────────────────────────────────────

def get_embedding_function():
    """Get sentence-transformers embedding function for ChromaDB."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )


def get_chroma_client():
    """Get persistent ChromaDB client."""
    return chromadb.PersistentClient(path=CHROMA_DIR)


def collection_exists() -> bool:
    """Check if the vector store collection already exists with data."""
    try:
        client = get_chroma_client()
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=get_embedding_function()
        )
        count = collection.count()
        logger.info(f"Existing collection found with {count} documents")
        return count > 0
    except Exception:
        return False


def build_vector_store(force_rebuild: bool = False) -> int:
    """Build the ChromaDB vector store from the PDFs. Returns chunks indexed."""
    if collection_exists() and not force_rebuild:
        client = get_chroma_client()
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=get_embedding_function()
        )
        count = collection.count()
        logger.info(f"Using existing vector store with {count} chunks")
        return count

    logger.info("Building vector store from PDFs...")
    client = get_chroma_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

    ef = get_embedding_function()
    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )

    pdf_files = glob.glob(os.path.join(DATA_DIR, "*.pdf"))
    if not pdf_files:
        logger.error(f"No PDFs found in {DATA_DIR}")
        return 0

    total_chunks_indexed = 0
    BATCH_SIZE = 500
    
    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        
        # Determine page count
        import fitz as fitz_module
        try:
            doc = fitz_module.open(pdf_path)
            page_count = len(doc)
            doc.close()
        except Exception:
            page_count = 0
            
        LARGE_PDF_THRESHOLD = 300
        if page_count > LARGE_PDF_THRESHOLD:
            logger.info(f"Using BATCHED extraction for {filename} ({page_count} pages)")
            chunks = chunk_documents_batched(pdf_path)
        else:
            logger.info(f"Using standard extraction for {filename} ({page_count} pages)")
            chunks = chunk_documents_from_markdown(pdf_path)

        if not chunks:
            continue
            
        total = len(chunks)
        for start in range(0, total, BATCH_SIZE):
            end = min(start + BATCH_SIZE, total)
            batch = chunks[start:end]
            collection.add(
                ids=[c["id"] for c in batch],
                documents=[c["text"] for c in batch],
                metadatas=[c["metadata"] for c in batch],
            )
            logger.info(f"  Indexed {end}/{total} chunks from {filename}...")
        
        total_chunks_indexed += total

    logger.info(f"Vector store built successfully with {total_chunks_indexed} total chunks")
    return total_chunks_indexed


def ingest_new_pdfs() -> int:
    """
    Incrementally ingest only NEW PDFs that aren't already in the vector store.
    Uses batched extraction for large PDFs (>300 pages) to manage thermals.
    Returns total number of new chunks added.
    """
    client = get_chroma_client()
    ef = get_embedding_function()

    # Get or create collection
    try:
        collection = client.get_collection(name=COLLECTION_NAME, embedding_function=ef)
        existing_count = collection.count()
        logger.info(f"Existing collection has {existing_count} chunks")
    except Exception:
        collection = client.create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"}
        )
        existing_count = 0
        logger.info("Created new collection")

    # Find all PDFs in the data directory
    pdf_files = glob.glob(os.path.join(DATA_DIR, "*.pdf"))
    
    indexed_books = set()
    if existing_count > 0:
        for pdf_path in pdf_files:
            filename = os.path.basename(pdf_path)
            
            # Legacy check: Martindale chunks have book="unknown" from v1/v2 pipeline
            if "martindale" in filename.lower() and existing_count > 50000:
                indexed_books.add(filename)
                logger.info(f"Legacy detection: treating '{filename}' as already indexed")
                continue
                
            # Proper check: search for at least 1 chunk with this book name
            try:
                result = collection.get(
                    limit=1,
                    where={"book": filename},
                    include=["metadatas"]
                )
                if result and result["ids"]:
                    indexed_books.add(filename)
            except Exception as e:
                logger.warning(f"Could not check index for {filename}: {e}")

    logger.info(f"Already indexed books: {indexed_books or '{none detected}'}")

    # Find all PDFs and filter to unprocessed ones
    pdf_files = glob.glob(os.path.join(DATA_DIR, "*.pdf"))
    new_pdfs = [p for p in pdf_files if os.path.basename(p) not in indexed_books]

    if not new_pdfs:
        logger.info("No new PDFs to ingest. All files already indexed.")
        return 0

    logger.info(f"Found {len(new_pdfs)} new PDF(s) to ingest: {[os.path.basename(p) for p in new_pdfs]}")

    total_new_chunks = 0
    BATCH_SIZE = 500  # ChromaDB add batch size
    LARGE_PDF_THRESHOLD = 300  # Pages — use batched extraction above this

    for pdf_path in new_pdfs:
        filename = os.path.basename(pdf_path)

        # Determine page count to choose extraction method
        import fitz as fitz_module
        doc = fitz_module.open(pdf_path)
        page_count = len(doc)
        doc.close()

        if page_count > LARGE_PDF_THRESHOLD:
            logger.info(f"Using BATCHED extraction for {filename} ({page_count} pages)")
            chunks = chunk_documents_batched(pdf_path)
        else:
            logger.info(f"Using standard extraction for {filename} ({page_count} pages)")
            chunks = chunk_documents_from_markdown(pdf_path)

        if not chunks:
            logger.warning(f"No chunks produced from {filename}, skipping")
            continue

        # Add to collection in batches
        total = len(chunks)
        for start in range(0, total, BATCH_SIZE):
            end = min(start + BATCH_SIZE, total)
            batch = chunks[start:end]
            collection.add(
                ids=[c["id"] for c in batch],
                documents=[c["text"] for c in batch],
                metadatas=[c["metadata"] for c in batch],
            )
            logger.info(f"  Indexed {end}/{total} chunks from {filename}")

        total_new_chunks += total
        logger.info(f"✓ Finished {filename}: {total} chunks added")

    final_count = collection.count()
    logger.info(f"Ingestion complete! Added {total_new_chunks} new chunks. Total in collection: {final_count}")
    return total_new_chunks


# ── Query Expansion ───────────────────────────────────────────────────────

def expand_query(query: str) -> list[str]:
    """
    Expand a user query into multiple search variants for better retrieval.
    This helps find relevant chunks that use different pharmaceutical terminology.
    """
    queries = [query]

    # Add common pharmaceutical synonyms / expansions
    expansions = {
        "side effects": ["adverse effects", "adverse reactions", "undesirable effects"],
        "side-effects": ["adverse effects", "adverse reactions"],
        "dosage": ["dose", "administration", "uses and administration"],
        "dose": ["dosage", "administration"],
        "interactions": ["drug interactions", "incompatibilities"],
        "overdose": ["overdosage", "toxicity", "poisoning"],
        "pregnancy": ["pregnancy", "breast-feeding", "lactation"],
        "children": ["paediatric", "pediatric", "neonates", "infants"],
        "how does": ["mechanism of action", "pharmacology", "action"],
        "mechanism": ["mechanism of action", "pharmacodynamics", "action"],
        "half life": ["pharmacokinetics", "half-life", "elimination"],
        "absorption": ["pharmacokinetics", "bioavailability"],
        "contraindications": ["contra-indications", "precautions", "warnings"],
    }

    query_lower = query.lower()
    for key, synonyms in expansions.items():
        if key in query_lower:
            for syn in synonyms:
                expanded = re.sub(key, syn, query_lower, flags=re.IGNORECASE)
                if expanded not in [q.lower() for q in queries]:
                    queries.append(expanded)

    return queries[:4]  # Max 4 query variants


# ── Retrieval ────────────────────────────────────────────────────────────

def retrieve_context(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Retrieve the most relevant chunks for a given query using query expansion.
    Returns deduplicated list of dicts with 'text', 'page', 'section', 'distance'.
    """
    client = get_chroma_client()
    ef = get_embedding_function()
    collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=ef
    )

    # Expand query for better coverage
    query_variants = expand_query(query)
    logger.info(f"Query expanded to {len(query_variants)} variants: {query_variants[:2]}...")

    # Retrieve for each query variant
    seen_texts = set()
    all_contexts = []

    for q_var in query_variants:
        results = collection.query(
            query_texts=[q_var],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        if results and results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            ):
                # Use first 80 chars as dedup key
                key = doc[:80]
                if key not in seen_texts:
                    seen_texts.add(key)
                    all_contexts.append({
                        "text": doc,
                        "book": meta.get("book", "Unknown"),
                        "page": meta.get("page", "?"),
                        "section": meta.get("section", "General"),
                        "distance": round(dist, 4),
                    })

    # Sort by relevance (low distance = high relevance) and take top_k
    all_contexts.sort(key=lambda x: x["distance"])
    return all_contexts[:top_k]


def format_context_for_llm(contexts: list[dict]) -> str:
    """Format retrieved contexts into a structured string for the LLM prompt."""
    if not contexts:
        return "No relevant information found in the reference database."

    # Group by section for better readability
    by_section = {}
    for ctx in contexts:
        section = ctx["section"]
        if section not in by_section:
            by_section[section] = []
        by_section[section].append(ctx)

    parts = []
    src_num = 1
    for section, ctxs in by_section.items():
        for ctx in ctxs:
            book = ctx.get('book', 'Unknown')
            parts.append(
                f"[Reference {src_num} | Book: {book} | {ctx['section']}]\n"
                f"{ctx['text']}"
            )
            src_num += 1

    return "\n\n━━━\n\n".join(parts)


# ── Enhanced System Prompt ────────────────────────────────────────────────

SYSTEM_PROMPT = """You are **MedBot**, an expert pharmaceutical intelligence assistant powered by authoritative medical references including *Martindale: The Complete Drug Reference (36th Edition)*, *RxPrep Course Book*, and *RxPrep NAPLEX Notes* — trusted resources used by pharmacists, physicians, and healthcare professionals globally.

## Your Expertise
You have deep knowledge of:
- Drug pharmacology, mechanisms of action, and pharmacokinetics
- Clinical uses, dosing regimens, and routes of administration
- Adverse effects, toxicity profiles, and overdose management
- Drug-drug, drug-food, and drug-disease interactions
- Contraindications, precautions, and special population considerations
- NAPLEX exam preparation topics and clinical pearls

## Response Format — ALWAYS use this structure:

### ⚡ Quick Summary
*(A 2-3 sentence TL;DR for busy professionals outlining what the drug is and the main point answering their question. Put this in a markdown blockquote over multiple lines if necessary)*

### 🔬 [Drug Name] — [Topic]
**Brief overview** (1-2 sentences from the reference)

**📋 Key Points:**
- Bullet point findings with specific details
- Include numerical values when available (doses, half-life, protein binding %)
- Cite sources: *(Martindale p.XXX)* or *(RxPrep, [Chapter])* as appropriate

**⚠️ Safety Considerations:**
- Adverse effects, interactions, or contraindications relevant to the question
- **Use severity indicators** where appropriate: 🔴 Severe/Major, 🟡 Moderate/Caution, 🟢 Mild/Minor
- Include Black Box Warnings (BBW) when referenced

**📊 Comparisons & Details:**
- **Use a markdown table** whenever comparing multiple drugs, routes of administration, or detailed dosing schedules (e.g. Adult vs Child vs Elderly). Tables make data scanable!

**💊 Clinical Context:**
- Practical information for students/professionals
- NAPLEX-relevant study tips when available from RxPrep sources

> ⚕️ *Always consult a qualified healthcare professional for clinical decisions. This information is from medical reference textbooks for educational reference.*

## Core Rules:
1. **Only answer from the provided reference context.** Never fabricate drug information.
2. **Always cite the source** from the retrieved context (e.g., *(Martindale p.125)* or *(RxPrep)*). Mention which book the information comes from.
3. **Be specific and precise** — include actual numbers, percentages, timeframes from the text
4. If context is insufficient, say: "The retrieved context doesn't contain enough detail about [topic]. I found related information on [nearby topics]."
5. Produce concise, readable bullet points instead of long paragraphs whenever possible.
6. Use emojis (🔬, ⚠️, 📊, 💊) strictly as section headers to organize output.
7. When context comes from multiple books, synthesize the information and note which source each detail comes from.

## Tone: Expert but accessible. Thorough but visually organized. Safety-first."""


def build_llm_messages(
    query: str,
    context_str: str,
    conversation_history: list[dict]
) -> list[dict]:
    """Build the messages array for the OpenRouter API call."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history (last 8 exchanges)
    history_window = conversation_history[-16:]
    messages.extend(history_window)

    # Structured user message with context
    user_message = (
        f"## Question\n{query}\n\n"
        f"## Retrieved Reference Context (from Pharmaceutical Textbooks)\n\n"
        f"{context_str}\n\n"
        f"---\n"
        f"Please provide a comprehensive, well-structured answer using the reference context above. "
        f"Include specific page citations, numerical values, and organize by the response format in your instructions. "
        f"If the context covers the topic well, be thorough. If it's partial, say what you found and what's missing."
    )
    messages.append({"role": "user", "content": user_message})

    return messages


# ── LLM Call with Retry ──────────────────────────────────────────────────

def query_llm(messages: list[dict], requested_model: str = None) -> str:
    """Send messages to OpenRouter API and return the response. Includes retry logic."""
    import requests

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = requested_model or os.getenv("OPENROUTER_MODEL", "openrouter/free")

    if not api_key:
        return "Error: OpenRouter API key not configured."

    api_key = api_key.strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "MedBot - Pharmaceutical RAG Chatbot",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,      # Lower = more factual and deterministic
        "max_tokens": 3500,      # Increased for thorough answers with tables/summaries
        "top_p": 0.85,
        "frequency_penalty": 0.1,  # Reduce repetition
    }

    max_retries = 4
    base_delay = 3

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            if attempt < max_retries:
                logger.warning(f"Timeout, retrying ({attempt+1}/{max_retries})...")
                time.sleep(base_delay * (2 ** attempt))
                continue
            return "⏱️ The request timed out. Please try again."

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            if status == 429 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Rate limited, retrying in {delay}s ({attempt+1}/{max_retries})...")
                time.sleep(delay)
                continue
            elif status == 402:
                return (
                    "⚠️ **API Credit Error**: The free-tier model is temporarily unavailable.\n\n"
                    "**To fix this**, add credits at https://openrouter.ai/settings/credits "
                    "and update `OPENROUTER_MODEL` in `.env` to `google/gemini-2.0-flash-001`."
                )
            logger.error(f"HTTP {status}: {e.response.text[:300]}")
            return f"API Error {status}. Please try again shortly."

        except Exception as e:
            logger.error(f"LLM error: {e}")
            if attempt < max_retries:
                time.sleep(base_delay)
                continue
            return f"An error occurred: {str(e)}"

    return "Failed after retries. Please try again in a moment."


def query_llm_stream(messages: list[dict], requested_model: str = None):
    """Stream messages from OpenRouter API and yield text chunks."""
    import requests
    import json

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = requested_model or os.getenv("OPENROUTER_MODEL", "openrouter/free")

    if not api_key:
        yield "Error: OpenRouter API key not configured."
        return

    api_key = api_key.strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "MedBot - Pharmaceutical RAG Chatbot",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 3500,
        "top_p": 0.85,
        "frequency_penalty": 0.1,
        "stream": True,
    }

    max_retries = 4
    base_delay = 3

    for attempt in range(max_retries + 1):
        try:
            with requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=120,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                return
                            try:
                                data = json.loads(data_str)
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                continue
                return
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            if status == 429 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Rate limited, retrying in {delay}s ({attempt+1}/{max_retries})...")
                import time
                yield f"\n\n*[Rate limit hit. Waiting {delay}s...]*\n\n"
                time.sleep(delay)
                continue
            elif status == 402:
                yield "\n\n⚠️ **API Credit Error**: The requested API pool is unavailable."
                return
            yield f"\n\n[API Error {status}: {e.response.text[:100]}]"
            return
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                import time
                yield f"\n\n*[Connection lost. Retrying in {delay}s...]*\n\n"
                time.sleep(delay)
                continue
            yield f"\n\n[Connection Error: {str(e)}]"
            return


# ── Full Pipeline ────────────────────────────────────────────────────────

def answer_query(query: str, conversation_history: list[dict], requested_model: str = None) -> dict:
    """Full RAG pipeline: retrieve → format → generate."""
    contexts = retrieve_context(query)
    context_str = format_context_for_llm(contexts)
    messages = build_llm_messages(query, context_str, conversation_history)
    answer = query_llm(messages, requested_model=requested_model)

    sources = [
        {"book": ctx.get("book", "?"), "section": ctx["section"], "relevance": round(1 - ctx["distance"], 4)}
        for ctx in contexts
    ]
    return {"answer": answer, "sources": sources, "query": query}

def answer_query_stream(query: str, conversation_history: list[dict], requested_model: str = None):
    """Stream RAG pipeline: yields JSON chunks of sources and text."""
    import json
    contexts = retrieve_context(query)
    context_str = format_context_for_llm(contexts)
    messages = build_llm_messages(query, context_str, conversation_history)
    
    sources = [
        {"book": ctx.get("book", "?"), "section": ctx["section"], "relevance": round(1 - ctx["distance"], 4)}
        for ctx in contexts
    ]
    
    yield json.dumps({"type": "metadata", "sources": sources}) + "\n"
    
    for chunk in query_llm_stream(messages, requested_model=requested_model):
        yield json.dumps({"type": "chunk", "content": chunk}) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--build":
        print("Building vector store from ALL PDFs (full rebuild)...")
        count = build_vector_store(force_rebuild=True)
        print(f"Done! Indexed {count} chunks.")
    elif len(sys.argv) > 1 and sys.argv[1] == "--ingest":
        print("Incrementally ingesting new PDFs only...")
        new_count = ingest_new_pdfs()
        print(f"Done! Added {new_count} new chunks.")
    elif len(sys.argv) > 1 and sys.argv[1] == "--query":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "What is paracetamol?"
        result = answer_query(query, [])
        print(f"\nAnswer:\n{result['answer']}")
        print(f"\nSources: {result['sources']}")
    else:
        print("Usage:")
        print("  python rag_pipeline.py --build          # Full rebuild (all PDFs)")
        print("  python rag_pipeline.py --ingest         # Add only NEW PDFs")
        print("  python rag_pipeline.py --query <text>   # Query the database")

