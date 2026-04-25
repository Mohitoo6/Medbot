import re
with open("rag_pipeline.py", "r") as f:
    content = f.read()

# Replace Imports
content = content.replace(
    "from langchain_text_splitters import RecursiveCharacterTextSplitter",
    "import glob\nimport pymupdf4llm\nfrom langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter"
)

# Replace Config
content = content.replace(
"""PDF_PATH = os.path.join(
    os.path.dirname(__file__),
    "Martindale-The-Complete-Drug-Reference_-36th-Edition (1).pdf"
)""",
"""DATA_DIR = os.path.dirname(__file__)"""
)

# Extract to Return pattern replacement
pattern = r"# ── PDF Text Extraction.*?logger\.info\(f\"Created \{len\(all_chunks\)\} chunks from \{len\(pages\)\} pages\"\)\n    return all_chunks"

new_extraction_code = """# ── Markdown-Aware Ingestion & Chunking ─────────────────────────

def chunk_documents_from_markdown(pdf_path: str) -> list[dict]:
    \"\"\"Extract PDF to Markdown and chunk via headings.\"\"\"
    filename = os.path.basename(pdf_path)
    logger.info(f"Extracting markdown from {filename} (This may take several minutes)...")
    
    try:
        md_text = pymupdf4llm.to_markdown(pdf_path)
    except Exception as e:
        logger.error(f"Failed to extract {filename}: {e}")
        return []
        
    logger.info(f"Extraction complete for {filename}. Splitting text...")
    
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
            
    logger.info(f"Created {len(all_chunks)} chunks from {filename}")
    return all_chunks"""

content = re.sub(pattern, new_extraction_code, content, flags=re.DOTALL)

# Replace Build Vector Store
pattern_build = r"def build_vector_store\(force_rebuild: bool = False\) -> int:.*?return total"
new_build_code = """def build_vector_store(force_rebuild: bool = False) -> int:
    \"\"\"Build the ChromaDB vector store from the PDFs. Returns chunks indexed.\"\"\"
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
            logger.info(f"  Indexed {end}/{total} chunks from {os.path.basename(pdf_path)}...")
        
        total_chunks_indexed += total

    logger.info(f"Vector store built successfully with {total_chunks_indexed} total chunks")
    return total_chunks_indexed"""

content = re.sub(pattern_build, new_build_code, content, flags=re.DOTALL)

# Replace context stuff
content = content.replace(
    '                        "page": meta.get("page", "?"),',
    '                        "book": meta.get("book", "Unknown"),\n                        "page": meta.get("page", "?"),'
)

# Format for LLM
content = content.replace(
"""            parts.append(
                f"[Reference {src_num} | Page {ctx['page']} | {ctx['section']}]\\n"
                f"{ctx['text']}"
            )""",
"""            book = ctx.get('book', 'Unknown')
            parts.append(
                f"[Reference {src_num} | Book: {book} | {ctx['section']}]\\n"
                f"{ctx['text']}"
            )"""
)

# sources dict
content = content.replace(
"""    sources = [
        {"page": ctx["page"], "section": ctx["section"], "relevance": round(1 - ctx["distance"], 4)}""",
"""    sources = [
        {"book": ctx.get("book", "?"), "section": ctx["section"], "relevance": round(1 - ctx["distance"], 4)}"""
)

# System prompt update
content = content.replace(
    "*Martindale: The Complete Drug Reference (36th Edition)*",
    "*Martindale: The Complete Drug Reference (36th Edition) and RxPrep*"
)

content = content.replace(
    "f\"## Retrieved Reference Context (from Martindale 36th Ed.)\\n\\n\"",
    "f\"## Retrieved Reference Context (from Pharmaceutical Textbooks)\\n\\n\""
)

with open("rag_pipeline.py", "w") as f:
    f.write(content)
