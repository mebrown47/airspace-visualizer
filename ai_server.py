from flask_cors import CORS
import os
import json
import time
import faiss
import numpy as np
import threading
from flask import Flask, request, jsonify
from ollama import embeddings, chat

ADS_B_FILE = "/tmp/aircraft.json"
VDL2_FILE = "/tmp/vdl2.json"
INDEX_FILE = "radar_index.faiss"
META_FILE = "radar_metadata.json"
EMBED_DIM = 768

app = Flask(__name__)
CORS(app)

# Use Inner Product index for cosine similarity
index = faiss.IndexFlatIP(EMBED_DIM)
metadata = []

def get_embedding(text):
    """Get normalized embedding for cosine similarity"""
    emb = embeddings(model="nomic-embed-text", prompt=text)["embedding"]
    # Convert to numpy array and normalize for cosine similarity
    emb = np.array(emb, dtype="float32")
    emb = emb.reshape(1, -1)
    faiss.normalize_L2(emb)
    return emb.flatten()

def extract_semantic_messages():
    summaries = []

    # ADS-B
    try:
        with open(ADS_B_FILE) as f:
            adsb = json.load(f).get("aircraft", [])
            for a in adsb:
                flight = a.get("flight", "unknown").strip()
                hexcode = a.get("hex", "")
                alt = a.get("alt_baro", "unknown")
                speed = a.get("gs", "unknown")
                lat = a.get("lat", "?")
                lon = a.get("lon", "?")
                summaries.append(f"ADS-B: {flight} ({hexcode}) at {alt} ft, speed {speed} knots, position {lat}, {lon}")
    except Exception as e:
        print(f"[ADS-B load error] {e}")

    # VDL2/ACARS
    try:
        with open(VDL2_FILE) as f:
            raw = f.read().strip()

        if not raw:
            raise ValueError("Empty VDL2 file")

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                vdl2_data = [parsed]  # wrap single object as list
            elif isinstance(parsed, list):
                vdl2_data = parsed
            else:
                raise ValueError("Unrecognized VDL2 format")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parse error: {e}")

        for entry in vdl2_data:
            v = entry.get("vdl2", entry)  # support wrapper key or flat
            acars = v.get("acars", {})
            flight = acars.get("flight", "unknown").strip()
            msg_text = acars.get("msg_text", "no message")
            summaries.append(f"ACARS message from flight {flight}: {msg_text}")
    except Exception as e:
        print(f"[VDL2 parse error] {e}")

    return summaries

def rebuild_index():
    global index, metadata
    print("\n🔄 Rebuilding semantic index...")
    summaries = extract_semantic_messages()

    if not summaries:
        print("⚠️ No messages to index")
        return

    # Reset index and metadata
    index = faiss.IndexFlatIP(EMBED_DIM)
    metadata = []
    embeddings_list = []

    # Generate embeddings for all summaries
    for msg in summaries:
        try:
            emb = get_embedding(msg)
            embeddings_list.append(emb)
        except Exception as e:
            print(f"[Embedding error for '{msg[:50]}...']: {e}")
            continue

    if embeddings_list:
        # Create embedding matrix and normalize for cosine similarity
        emb_matrix = np.array(embeddings_list).astype("float32")
        faiss.normalize_L2(emb_matrix)
        
        # Add to index
        index.add(emb_matrix)
        metadata.extend(summaries[:len(embeddings_list)])

        # Save index and metadata
        try:
            faiss.write_index(index, INDEX_FILE)
            with open(META_FILE, "w") as f:
                json.dump(metadata, f)
        except Exception as e:
            print(f"[Index save error]: {e}")

    print(f"✅ Indexed {len(metadata)} messages")

def generate_chat_response(query, context_messages, chat_model="gemma3:4b"):
    """Generate conversational response using retrieved context"""
    
    # Format context for the chat model
    if context_messages:
        context_text = "\n".join([f"- {msg}" for msg in context_messages])
        system_prompt = f"""You are an aviation radar assistant with access to real-time aircraft data. 
Use the following current aviation information to answer questions:

CURRENT AVIATION DATA:
{context_text}

Guidelines:
- Be conversational and helpful
- Focus on aviation safety and operational information
- If asked about specific flights, reference the data provided
- If the data doesn't contain what's asked, say so clearly
- Use aviation terminology appropriately
- Keep responses concise but informative"""
    else:
        system_prompt = """You are an aviation radar assistant. I don't have any current aviation data available right now, but I can help with general aviation questions and guidance."""

    try:
        response = chat(
            model=chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            options={
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 512
            }
        )
        return response['message']['content']
    except Exception as e:
        return f"Chat model error: {str(e)}"

def periodic_rebuild():
    """Periodically rebuild the index with fresh data"""
    while True:
        rebuild_index()
        time.sleep(15)
    while True:
        rebuild_index()
        time.sleep(15)

@app.route("/chat")
def chat_endpoint():
    """Conversational interface with RAG context"""
    query = request.args.get("q", "")
    threshold = float(request.args.get("threshold", "0.3"))  # Lower default for chat
    max_context = int(request.args.get("max_context", "3"))  # Limit context for chat
    chat_model = request.args.get("model", "gemma3:4b")
    
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"})

    try:
        # Get relevant context using semantic search
        context_messages = []
        if metadata:  # Only search if we have indexed data
            query_emb = get_embedding(query)
            query_emb = query_emb.reshape(1, -1)
            
            scores, idxs = index.search(query_emb, min(max_context * 2, len(metadata)))
            
            # Get relevant messages above threshold
            for score, idx in zip(scores[0], idxs[0]):
                if idx < len(metadata) and score >= threshold:
                    context_messages.append(metadata[idx])
            
            context_messages = context_messages[:max_context]
        
        # Generate conversational response
        chat_response = generate_chat_response(query, context_messages, chat_model)
        
        return jsonify({
            "query": query,
            "response": chat_response,
            "context_used": len(context_messages),
            "context_messages": context_messages if request.args.get("show_context") == "true" else None,
            "model": chat_model,
            "threshold_used": threshold
        })
        
    except Exception as e:
        return jsonify({
            "error": f"Chat error: {str(e)}",
            "query": query
        })

@app.route("/ask")
def ask_question():
    query = request.args.get("q", "")
    threshold = float(request.args.get("threshold", "0.3"))  # Lower default threshold
    max_results = int(request.args.get("max_results", "5"))
    format_type = request.args.get("format", "simple")  # "simple" or "detailed"
    debug_mode = request.args.get("debug", "false").lower() == "true"
    
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"})

    if not metadata:
        return jsonify({
            "error": "No indexed data available. Please wait for initial indexing to complete."
        })

    try:
        # Get query embedding
        query_emb = get_embedding(query)
        query_emb = query_emb.reshape(1, -1)
        
        # Search for similar messages
        search_k = min(max_results * 3, len(metadata))  # Search more than needed
        scores, idxs = index.search(query_emb, search_k)
        
        debug_info = {}
        if debug_mode:
            debug_info = {
                "query_embedding_shape": query_emb.shape,
                "search_k": search_k,
                "raw_scores": scores[0][:5].tolist(),
                "raw_indices": idxs[0][:5].tolist(),
                "threshold": threshold,
                "metadata_count": len(metadata)
            }
        
        # Filter results by confidence threshold
        filtered_results = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < len(metadata) and score >= threshold:  # Higher cosine similarity = better match
                filtered_results.append({
                    "text": metadata[idx],
                    "confidence": float(score),
                    "score": float(score)
                })
        
        # If no results with threshold, show best matches anyway in debug mode
        if not filtered_results and debug_mode:
            debug_info["best_matches_regardless_of_threshold"] = []
            for score, idx in zip(scores[0][:3], idxs[0][:3]):
                if idx < len(metadata):
                    debug_info["best_matches_regardless_of_threshold"].append({
                        "text": metadata[idx][:100] + "...",  # Truncated for debug
                        "score": float(score)
                    })
        
        # Limit to max_results
        filtered_results = filtered_results[:max_results]
        
        # Format results based on requested format
        if format_type == "detailed":
            # Return detailed format with confidence scores
            response = {
                "query": query,
                "threshold_used": threshold,
                "total_indexed": len(metadata),
                "results_found": len(filtered_results),
                "results": filtered_results if filtered_results else ["No relevant messages found above confidence threshold."],
                "best_match_confidence": filtered_results[0]["confidence"] if filtered_results else 0.0
            }
            if debug_mode:
                response["debug"] = debug_info
        else:
            # Return simple format (backward compatible)
            if filtered_results:
                # Just return the text strings with optional confidence info
                simple_results = []
                for result in filtered_results:
                    confidence_str = f" (confidence: {result['confidence']:.2f})" if request.args.get("show_confidence") == "true" else ""
                    simple_results.append(result["text"] + confidence_str)
                response = {
                    "query": query,
                    "results": simple_results
                }
            else:
                response = {
                    "query": query, 
                    "results": [f"No relevant messages found above confidence threshold {threshold}. Try lowering threshold with &threshold=0.3"]
                }
            
            if debug_mode:
                response["debug"] = debug_info
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            "error": f"Search error: {str(e)}",
            "query": query
        })

@app.route("/debug")
def debug_info():
    """Debug endpoint to check index status and test embeddings"""
    debug_data = {
        "index_status": {
            "total_vectors": index.ntotal if index else 0,
            "metadata_count": len(metadata),
            "index_dimension": EMBED_DIM,
            "index_type": str(type(index)) if index else "None"
        },
        "sample_metadata": metadata[:3] if metadata else [],
        "files_exist": {
            "adsb_file": os.path.exists(ADS_B_FILE),
            "vdl2_file": os.path.exists(VDL2_FILE),
            "index_file": os.path.exists(INDEX_FILE),
            "meta_file": os.path.exists(META_FILE)
        }
    }
    
    # Test embedding generation
    try:
        test_emb = get_embedding("test aircraft message")
        debug_data["embedding_test"] = {
            "success": True,
            "embedding_shape": len(test_emb),
            "sample_values": test_emb[:5].tolist() if len(test_emb) >= 5 else test_emb.tolist()
        }
    except Exception as e:
        debug_data["embedding_test"] = {
            "success": False,
            "error": str(e)
        }
    
    # Test a simple search
    try:
        if metadata and index.ntotal > 0:
            query_emb = get_embedding("aircraft")
            query_emb = query_emb.reshape(1, -1)
            scores, idxs = index.search(query_emb, min(3, len(metadata)))
            debug_data["search_test"] = {
                "success": True,
                "scores": scores[0].tolist(),
                "indices": idxs[0].tolist(),
                "best_score": float(scores[0][0]) if len(scores[0]) > 0 else "no results"
            }
        else:
            debug_data["search_test"] = {"success": False, "reason": "no_data_indexed"}
    except Exception as e:
        debug_data["search_test"] = {
            "success": False,
            "error": str(e)
        }
    
    return jsonify(debug_data)
    """Health check and index status endpoint"""
    return jsonify({
        "status": "running",
        "indexed_messages": len(metadata),
        "index_dimension": EMBED_DIM,
        "model": "nomic-embed-text",
        "similarity_method": "cosine",
        "files_monitored": [ADS_B_FILE, VDL2_FILE]
    })

@app.route("/")
def home():
    return """
    <h1>Radar AI Assistant (Semantic RAG + Chat)</h1>
    <p>Endpoints:</p>
    <ul>
        <li><code>/ask?q=your_query&threshold=0.7&max_results=5</code> - Search messages</li>
        <li><code>/chat?q=your_question&threshold=0.6&model=gemma3:4b</code> - Conversational interface</li>
        <li><code>/status</code> - Check system status</li>
        <li><code>/debug</code> - Debug index and embedding status</li>
    </ul>
    <p><strong>Troubleshooting:</strong></p>
    <ul>
        <li>No results? Try: <code>/ask?q=aircraft&threshold=0.1&debug=true</code></li>
        <li>Check system: <code>/debug</code></li>
        <li>Lower threshold: <code>&threshold=0.3</code> or <code>&threshold=0.1</code></li>
    </ul>
    <p>Using cosine similarity with confidence thresholding + Gemma3 4B chat.</p>
    """

if __name__ == "__main__":
    print("\n🚀 Launching Radar AI Assistant (Semantic RAG + Chat)")
    print("📊 Using cosine similarity with confidence thresholding")
    print("🤖 Chat powered by Gemma3 4B")
    print(f"📁 Monitoring: {ADS_B_FILE}, {VDL2_FILE}")
    print(f"🧠 Embedding Model: nomic-embed-text ({EMBED_DIM}D)")
    
    # Load existing index if available
    try:
        if os.path.exists(INDEX_FILE) and os.path.exists(META_FILE):
            print("📂 Loading existing index...")
            index = faiss.read_index(INDEX_FILE)
            with open(META_FILE, "r") as f:
                metadata = json.load(f)
            print(f"✅ Loaded {len(metadata)} existing messages")
    except Exception as e:
        print(f"⚠️ Could not load existing index: {e}")
        print("🔄 Will rebuild on startup...")
    
    # Start periodic rebuild thread
    threading.Thread(target=periodic_rebuild, daemon=True).start()
    
    # Run Flask app
    app.run(host="0.0.0.0", port=11435, debug=False)
