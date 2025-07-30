#!/usr/bin/env python3
"""
OpenWebUI Adapter - Versiune corectată pentru probleme de răspuns
"""
import asyncio
import json
import os
import sys
import time
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from Clase.OpenWebUI import OpenWebUIAdapter, ChatRequest
import logging

# Import clientul LLM existent
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from universal_llm_client import MCPStdioLLMClient

# Configurare logging mai detaliată
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Instanța globală a adapter-ului
openwebui_adapter = None

# FastAPI App
app = FastAPI(
    title="OpenWebUI MCP Adapter (Corrigat)", 
    version="2.2.0",
    description="Adapter pentru integrarea OpenWebUI cu clientul LLM și serverul MCP Alfresco"
)

# CORS pentru OpenWebUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Inițializează adapter-ul la pornire"""
    global openwebui_adapter
    try:
        openwebui_adapter = OpenWebUIAdapter()
        logger.info("🚀 OpenWebUI Adapter corrigat pornit!")
        
        # Log configurația inițială
        if openwebui_adapter.is_healthy:
            status = await openwebui_adapter.get_mcp_status()
            logger.info(f"📊 Status inițial: {status}")
        
    except Exception as e:
        logger.error(f"❌ Eroare la startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Curăță resursele la oprire"""
    global openwebui_adapter
    if openwebui_adapter:
        openwebui_adapter.cleanup()
        logger.info("🛑 OpenWebUI Adapter oprit")

@app.get("/")
async def root():
    """Endpoint de test îmbunătățit"""
    global openwebui_adapter
    if not openwebui_adapter:
        return {"error": "Adapter nu este inițializat"}
    
    status = await openwebui_adapter.get_mcp_status()
    return {
        "message": "OpenWebUI Adapter corrigat cu client LLM existent",
        "version": "2.2.0",
        "mcp_connected": status.get("connected", False),
        "tools_count": status.get("tools_count", 0),
        "llm_provider": status.get("provider", "unknown"),
        "llm_model": status.get("model", "unknown"),
        "healthy": status.get("healthy", False),
        "endpoints": {
            "models": "/v1/models",
            "chat": "/v1/chat/completions", 
            "status": "/v1/mcp/status",
            "tools": "/v1/mcp/tools",
            "restart": "/v1/mcp/restart"
        }
    }

@app.get("/health")
async def health_check():
    """Health check pentru monitoring"""
    global openwebui_adapter
    
    if not openwebui_adapter:
        raise HTTPException(status_code=503, detail="Adapter nu este inițializat")
    
    status = await openwebui_adapter.get_mcp_status()
    
    if status.get("healthy") and status.get("connected"):
        return {"status": "healthy", "details": status}
    else:
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "details": status})

@app.get("/v1/models")
async def list_models():
    """Lista modelelor pentru OpenWebUI"""
    global openwebui_adapter
    
    logger.info("📋 Solicitare listă modele")
    
    # Model de bază întotdeauna disponibil
    base_model = {
        "id": "alfresco-mcp-assistant",
        "object": "model", 
        "created": int(time.time()),
        "owned_by": "mcp-adapter",
        "permission": [],
        "root": "alfresco-mcp-assistant",
        "parent": None,
    }
    
    models = [base_model]
    
    # Adaugă informații despre modelul LLM real dacă e disponibil
    if openwebui_adapter:
        try:
            status = await openwebui_adapter.get_mcp_status()
            
            if status.get("provider") and status.get("model"):
                enhanced_model = {
                    "id": f"alfresco-{status['provider']}-{status['model']}",
                    "object": "model",
                    "created": int(time.time()), 
                    "owned_by": f"mcp-{status['provider']}",
                    "permission": [],
                    "root": f"alfresco-{status['provider']}-{status['model']}",
                    "parent": None,
                }
                models.append(enhanced_model)
                logger.info(f"➕ Adăugat model enhanced: {enhanced_model['id']}")
                
        except Exception as e:
            logger.error(f"❌ Eroare la obținerea modelelor: {e}")
    
    response = {
        "object": "list",
        "data": models
    }
    
    logger.info(f"✅ Returnez {len(models)} modele")
    return response

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """
    Endpoint principal pentru chat - cu suport pentru streaming
    """
    global openwebui_adapter
    
    logger.info(f"💬 Primită cerere chat: model={request.model}, mesaje={len(request.messages)}, stream={request.stream}")
    
    if not openwebui_adapter:
        logger.error("❌ Adapter nu este inițializat")
        raise HTTPException(status_code=503, detail="Adapter nu este inițializat")
    
    # Validare cerere
    if not request.messages or len(request.messages) == 0:
        logger.error("❌ Nu s-au primit mesaje")
        raise HTTPException(status_code=400, detail="Nu s-au primit mesaje")
    
    # Dacă este cerere pentru streaming, folosim StreamingResponse
    if request.stream:
        logger.info("🌊 Folosesc streaming response")
        return StreamingResponse(
            stream_chat_response(request, openwebui_adapter),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    # Răspuns standard (non-streaming)
    try:
        # Log mesajele pentru debugging
        for i, msg in enumerate(request.messages):
            logger.info(f"  Mesaj {i}: {msg.role} - {msg.content[:50]}...")
        
        # Procesează chat-ul
        start_time = time.time()
        logger.info("🔄 Încep procesarea chat-ului...")
        
        response_content = await openwebui_adapter.process_chat_async(request.messages)
        
        process_time = time.time() - start_time
        logger.info(f"⏱️ Procesarea a durat {process_time:.2f}s")
        
        # Validare răspuns
        if not response_content or not response_content.strip():
            logger.error("❌ Răspuns gol de la procesare")
            response_content = "❌ Nu am putut genera un răspuns. Verifică logs pentru detalii."
        
        logger.info(f"📤 Pregătesc să returnez răspuns de {len(response_content)} caractere")
        logger.debug(f"Răspuns final: {response_content[:200]}...")
        
        # Formatează răspunsul pentru OpenWebUI
        response = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_content
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": sum(len(msg.content.split()) for msg in request.messages),
                "completion_tokens": len(response_content.split()),
                "total_tokens": sum(len(msg.content.split()) for msg in request.messages) + len(response_content.split())
            }
        }
        
        logger.info(f"✅ Răspuns formatat cu succes pentru OpenWebUI")
        return response
        
    except Exception as e:
        logger.error(f"❌ Eroare în chat completions: {e}", exc_info=True)
        
        # Răspuns de fallback în caz de eroare
        error_response = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"❌ Eroare la procesarea cererii: {str(e)}\n\nVerifică logs pentru mai multe detalii."
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
        return error_response

async def stream_chat_response(request: ChatRequest, adapter: OpenWebUIAdapter):
    """
    Generator pentru streaming response - compatibil cu OpenWebUI
    """
    try:
        logger.info("🌊 Încep streaming response...")
        
        # Log mesajele pentru debugging
        for i, msg in enumerate(request.messages):
            logger.info(f"  Mesaj {i}: {msg.role} - {msg.content[:50]}...")
        
        # Procesează chat-ul
        start_time = time.time()
        response_content = await adapter.process_chat_async(request.messages)
        process_time = time.time() - start_time
        
        logger.info(f"⏱️ Procesarea streaming a durat {process_time:.2f}s")
        
        # Validare răspuns
        if not response_content or not response_content.strip():
            logger.error("❌ Răspuns gol pentru streaming")
            response_content = "❌ Nu am putut genera un răspuns. Verifică logs pentru detalii."
        
        logger.info(f"🌊 Streaming răspuns de {len(response_content)} caractere")
        
        # ID-ul răspunsului
        chat_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        
        # Trimite răspunsul ca stream de bucăți
        words = response_content.split()
        
        for i, word in enumerate(words):
            chunk_content = word + (" " if i < len(words) - 1 else "")
            
            chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": chunk_content
                        },
                        "finish_reason": None
                    }
                ]
            }
            
            # Formatează ca Server-Sent Events
            yield f"data: {json.dumps(chunk)}\n\n"
            
            # Mică pauză pentru efect de streaming natural
            await asyncio.sleep(0.01)
        
        # Trimite chunk-ul final
        final_chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
        
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"
        
        logger.info("✅ Streaming complet")
        
    except Exception as e:
        logger.error(f"❌ Eroare în streaming: {e}", exc_info=True)
        
        # Chunk de eroare
        error_chunk = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": f"❌ Eroare streaming: {str(e)}"
                    },
                    "finish_reason": "stop"
                }
            ]
        }
        
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"

# Endpoint-urile de management rămân la fel
@app.get("/v1/mcp/status")
async def mcp_status():
    """Status al conexiunii MCP"""
    global openwebui_adapter
    
    if not openwebui_adapter:
        raise HTTPException(status_code=503, detail="Adapter nu este inițializat")
    
    return await openwebui_adapter.get_mcp_status()

@app.get("/v1/mcp/tools")
async def list_mcp_tools():
    """Lista tool-urilor MCP disponibile"""
    global openwebui_adapter
    
    if not openwebui_adapter:
        raise HTTPException(status_code=503, detail="Adapter nu este inițializat")
    
    tools = await openwebui_adapter.get_available_tools()
    return {"tools": tools, "count": len(tools)}

@app.post("/v1/mcp/restart")
async def restart_mcp_client():
    """Restart clientul LLM cu MCP"""
    global openwebui_adapter
    
    if not openwebui_adapter:
        raise HTTPException(status_code=503, detail="Adapter nu este inițializat")
    
    try:
        logger.info("🔄 Restart client LLM...")
        
        # Forțează recrearea clientului
        with openwebui_adapter.client_lock:
            if openwebui_adapter.llm_client:
                openwebui_adapter.llm_client.stop_mcp_server()
            openwebui_adapter.llm_client = None
            openwebui_adapter.last_activity = 0  # Forțează recrearea
            openwebui_adapter.is_healthy = False
        
        # Testează noul client
        openwebui_adapter._test_configuration()
        status = await openwebui_adapter.get_mcp_status()
        
        if status.get("connected"):
            return {"success": True, "message": "Client LLM restartat cu succes", "status": status}
        else:
            return {"success": False, "message": "Restart parțial - verifică conexiunea MCP", "status": status}
            
    except Exception as e:
        logger.error(f"❌ Eroare restart: {e}")
        raise HTTPException(status_code=500, detail=f"Eroare restart: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    import signal
    
    def signal_handler(signum, frame):
        """Handler pentru semnale de sistem"""
        logger.info(f"🛑 Primit semnal {signum} - opresc adapter-ul...")
        if openwebui_adapter:
            openwebui_adapter.cleanup()
        sys.exit(0)
    
    # Înregistrează handlere pentru semnale
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🚀 Pornesc OpenWebUI Adapter corrigat...")
    
    # Pornește serverul
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8001,
        log_level="info"
    )