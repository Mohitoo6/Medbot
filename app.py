"""
MedBot Flask Application
=========================
REST API server for the pharmaceutical RAG chatbot.
"""

import os
import uuid
import logging
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from rag_pipeline import build_vector_store, answer_query, collection_exists, ingest_new_pdfs

load_dotenv()

# ── App Setup ────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── In-memory session storage ────────────────────────────────────────────
# Maps session_id -> { "history": [...], "created_at": datetime }
sessions: dict[str, dict] = {}
MAX_HISTORY = 20  # Max messages per session (10 exchanges)


def get_or_create_session(session_id: str | None) -> tuple[str, list]:
    """Get existing session or create a new one."""
    if session_id and session_id in sessions:
        return session_id, sessions[session_id]["history"]

    new_id = session_id or str(uuid.uuid4())
    sessions[new_id] = {
        "history": [],
        "created_at": datetime.now().isoformat(),
    }
    return new_id, sessions[new_id]["history"]


# ── Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def serve_frontend():
    """Serve the main application page."""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    db_ready = collection_exists()
    return jsonify({
        "status": "healthy",
        "database_ready": db_ready,
        "active_sessions": len(sessions),
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Main chat endpoint.
    Expects JSON: { "message": str, "session_id": str (optional) }
    Returns JSON: { "answer": str, "sources": [...], "session_id": str }
    """
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' field"}), 400

    user_message = data["message"].strip()
    if not user_message:
        return jsonify({"error": "Message cannot be empty"}), 400

    if len(user_message) > 2000:
        return jsonify({"error": "Message too long (max 2000 characters)"}), 400

    # Get or create session
    session_id, history = get_or_create_session(data.get("session_id"))

    try:
        if not collection_exists():
            return jsonify({
                "answer": "⚠️ **Database Initialization in Progress:** The medical database is currently being built from the reference PDFs. This process can take several minutes. Please try your search again shortly.",
                "sources": [],
                "session_id": session_id,
            })
            
        # Run RAG pipeline
        result = answer_query(user_message, history)

        # Update conversation history
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": result["answer"]})

        # Trim history if too long
        if len(history) > MAX_HISTORY:
            sessions[session_id]["history"] = history[-MAX_HISTORY:]

        return jsonify({
            "answer": result["answer"],
            "sources": result["sources"],
            "session_id": session_id,
        })

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({
            "error": "An internal error occurred. Please try again.",
            "session_id": session_id,
        }), 500


@app.route("/api/chat_stream", methods=["POST"])
def chat_stream():
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    Expects JSON: { "message": str, "session_id": str (optional) }
    Yields NDJSON chunks.
    """
    from flask import Response, stream_with_context
    import json
    from rag_pipeline import answer_query_stream
    
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' field"}), 400

    user_message = data["message"].strip()
    if not user_message:
        return jsonify({"error": "Message cannot be empty"}), 400

    if len(user_message) > 2000:
        return jsonify({"error": "Message too long (max 2000 characters)"}), 400

    session_id, history = get_or_create_session(data.get("session_id"))
    requested_model = data.get("model")

    def generate():
        full_answer = []
        client_disconnected = False
        try:
            if not collection_exists():
                yield json.dumps({"type": "chunk", "content": "⚠️ **Database Initialization in Progress:** The medical database is currently being built from the reference PDFs. This process can take several minutes. Please try your search again shortly."}) + "\n"
                return
                
            for out in answer_query_stream(user_message, history, requested_model):
                obj = json.loads(out)
                if obj.get("type") == "chunk":
                    full_answer.append(obj.get("content", ""))
                yield out
                
            # After stream finishes, save to history
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": "".join(full_answer)})
            if len(history) > MAX_HISTORY:
                sessions[session_id]["history"] = history[-MAX_HISTORY:]
                
            # Yield final session ID update
            yield json.dumps({"type": "session", "session_id": session_id}) + "\n"

        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Client disconnected mid-stream (e.g. page refresh, navigation)
            # This is normal and expected — log as info, not error
            client_disconnected = True
            logger.info(f"Client disconnected during stream (session {session_id[:8]}…). Saving partial response.")

        except OSError as e:
            # Catches [Errno 5] Input/output error and similar OS-level I/O failures
            if e.errno == 5 or "input/output" in str(e).lower():
                client_disconnected = True
                logger.info(f"Client I/O disconnect during stream (session {session_id[:8]}…). Saving partial response.")
            else:
                logger.error(f"Stream OS error: {e}", exc_info=True)
                try:
                    yield json.dumps({"type": "error", "content": f"Stream error: {str(e)}"}) + "\n"
                except Exception:
                    pass  # Client already gone

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            try:
                yield json.dumps({"type": "error", "content": f"Stream error: {str(e)}"}) + "\n"
            except (BrokenPipeError, OSError):
                pass  # Client already gone

        finally:
            # Always save whatever we got to history, even on disconnect
            if client_disconnected and full_answer:
                partial = "".join(full_answer)
                history.append({"role": "user", "content": user_message})
                history.append({"role": "assistant", "content": partial})
                if len(history) > MAX_HISTORY:
                    sessions[session_id]["history"] = history[-MAX_HISTORY:]
                logger.info(f"Saved partial response ({len(partial)} chars) to session history.")

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')


@app.route("/api/clear", methods=["POST"])
def clear_session():
    """Clear conversation history for a session."""
    data = request.get_json() or {}
    session_id = data.get("session_id")

    if session_id and session_id in sessions:
        sessions[session_id]["history"] = []
        return jsonify({"status": "cleared", "session_id": session_id})

    return jsonify({"status": "no_session_found"}), 404


@app.route("/api/stats", methods=["GET"])
def stats():
    """Get database statistics."""
    try:
        from rag_pipeline import get_chroma_client, get_embedding_function, COLLECTION_NAME
        client = get_chroma_client()
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=get_embedding_function()
        )
        count = collection.count()
        return jsonify({
            "total_chunks": count,
            "active_sessions": len(sessions),
            "embedding_model": "all-MiniLM-L6-v2",
            "llm_model": os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Startup ──────────────────────────────────────────────────────────────

def initialize():
    """Initialize the application — build vector store if needed, ingest new PDFs."""
    logger.info("=" * 60)
    logger.info("  MedBot — Pharmaceutical RAG Chatbot")
    logger.info("=" * 60)

    if not collection_exists():
        logger.info("Vector store not found. Building from all PDFs...")
        logger.info("This may take 5-15 minutes for the first run...")
        count = build_vector_store()
        logger.info(f"Vector store ready with {count} chunks!")
    else:
        logger.info("Vector store exists. Checking for new PDFs to ingest...")
        new_count = ingest_new_pdfs()
        if new_count > 0:
            logger.info(f"Added {new_count} new chunks from new PDFs!")
        else:
            logger.info("All PDFs already indexed. Ready to serve!")

    logger.info("Server starting on http://0.0.0.0:7860")
    logger.info("=" * 60)


if __name__ == "__main__":
    import threading
    init_thread = threading.Thread(target=initialize)
    init_thread.daemon = True
    init_thread.start()
    
    app.run(host="0.0.0.0", port=7860, debug=False)
