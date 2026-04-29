#!/usr/bin/env python3
"""
OpenWebUI Adapter pentru MCP HTTP - Versiune adaptată pentru comunicație HTTP
"""
import asyncio
import json
import sys
import time
import uuid
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from Clase.OpenWebUI import OpenWebUIHTTPAdapter
from Clase.OpenWebUI import ChatRequest
from pydantic import BaseModel, Field

from Clase.Authen import (
    UserManager, UserRole, User, TokenData,
    init_auth, create_access_token, verify_access_token,
    get_alfresco_credentials_for_role, get_allowed_tools_for_role,
    extract_token_from_header,
)

# Configurare logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CONFIG_PATH = "llm_config.json"

# Modele Pydantic

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str
    role: str

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.VIEWER

class UpdatePasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6)

class UpdateRoleRequest(BaseModel):
    role: UserRole

# Instanța globală a adapter-ului HTTP
openwebui_adapter = None

# FastAPI App pentru HTTP
app = FastAPI(
    title="OpenWebUI MCP HTTP Adapter", 
    version="3.0.0",
    description="Adapter pentru integrarea OpenWebUI cu clientul LLM și serverul MCP Alfresco prin HTTP"
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
    """Inițializează adapter-ul HTTP la pornire"""
    global openwebui_adapter
    try:
        init_auth(CONFIG_PATH)
        openwebui_adapter = OpenWebUIHTTPAdapter()
        logger.info("🚀 OpenWebUI HTTP Adapter pornit!")
        
        # Așteaptă puțin pentru inițializare
        await asyncio.sleep(2)
        
        # Log configurația inițială
        if openwebui_adapter.is_healthy:
            status = await openwebui_adapter.get_mcp_status()
            logger.info(f"📊 Status HTTP inițial: {status}")
        
    except Exception as e:
        logger.error(f"❌ Eroare la startup HTTP: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Curăță resursele HTTP la oprire"""
    global openwebui_adapter
    if openwebui_adapter:
        await openwebui_adapter.cleanup()
        logger.info("🛑 OpenWebUI HTTP Adapter oprit")

# Dependențe JWT

async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
) -> TokenData:
    # Încearcă mai întâi Authorization: Bearer
    token = extract_token_from_header(authorization) if authorization else None
    
    # Fallback pe X-Api-Key (cum trimite OpenWebUI)
    if not token and x_api_key:
        token = x_api_key
    
    if not token:
        raise HTTPException(status_code=401, detail="Lipsește autentificarea")
    
    token_data = verify_access_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Token invalid sau expirat")
    
    return token_data

async def require_admin(
    current_user: TokenData = Depends(get_current_user)
) -> TokenData:
    """Permite accesul doar utilizatorilor cu rol admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Necesită rol admin")
    return current_user

# Authen Endpoints

@app.post("/auth/login", response_model=LoginResponse, tags=["Auth"])
async def login(request: LoginRequest):
    """
    Autentifică un utilizator și returnează un JWT.
 
    Trimite username și parolă, primești un token pe care îl folosești
    în toate cererile ulterioare în header-ul Authorization: Bearer <token>
    """
    user = UserManager.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credențiale invalide")
 
    token = create_access_token(user)
    logger.info(f"🔐 Login: {user.username} (rol: {user.role.value})")
 
    from Clase.Authen import JWT_EXPIRE_HOURS
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRE_HOURS * 3600,
        username=user.username,
        role=user.role.value,
    )

@app.get("/auth/me", tags=["Auth"])
async def get_me(current_user: TokenData = Depends(get_current_user)):
    """Informații despre utilizatorul autentificat curent."""
    user = UserManager.get(current_user.username)
    if not user:
        raise HTTPException(status_code=404, detail="Utilizatorul nu mai există")
    return {
        "username":        user.username,
        "role":            user.role.value,
        "allowed_tools":   get_allowed_tools_for_role(user.role),
        "alfresco_account": get_alfresco_credentials_for_role(user.role)["username"],
    }

@app.post("/auth/change-password", tags=["Auth"])
async def change_password(
    request: UpdatePasswordRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Schimbă propria parolă."""
    ok = UserManager.update_password(current_user.username, request.new_password)
    if not ok:
        raise HTTPException(status_code=500, detail="Eroare actualizare parolă")
    return {
        "message": "Parola actualizată cu succes"
    }

# Admin Endpoints

@app.get("/admin/users", tags=["Admin"])
async def list_users(_: TokenData = Depends(require_admin)):
    """Listează toți utilizatorii. Necesită rol admin."""
    users = UserManager.list_all()
    return {
        "users": [
            {
                **u,
                "alfresco_account": get_alfresco_credentials_for_role(
                    UserRole(u["role"])
                )["username"],
                "allowed_tools": get_allowed_tools_for_role(UserRole(u["role"])),
            }
            for u in users
        ],
        "total": len(users),
    }

@app.post("/admin/users", tags=["Admin"])
async def create_user(
    request: CreateUserRequest,
    _: TokenData = Depends(require_admin)
):
    """Creează un utilizator nou. Necesită rol admin."""
    try:
        user = UserManager.create(request.username, request.password, request.role)
        logger.info(f"👤 Utilizator creat: {user.username} (rol: {user.role.value})")
        return {
            "username": user.username,
            "role":     user.role.value,
            "message":  f"Utilizatorul '{user.username}' creat cu succes"
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.patch("/admin/users/{username}/role", tags=["Admin"])
async def update_role(
    username: str,
    request: UpdateRoleRequest,
    _: TokenData = Depends(require_admin)
):
    """Schimbă rolul unui utilizator. Necesită rol admin."""
    if not UserManager.get(username):
        raise HTTPException(status_code=404, detail="Utilizatorul nu există")
    UserManager.update_role(username, request.role)
    return {
        "message": f"Rol actualizat: {username} → {request.role.value}"
    }

@app.patch("/admin/users/{username}/password", tags=["Admin"])
async def admin_reset_password(
    username: str,
    request: UpdatePasswordRequest,
    _: TokenData = Depends(require_admin)
):
    """Resetează parola unui utilizator. Necesită rol admin."""
    if not UserManager.get(username):
        raise HTTPException(status_code=404, detail="Utilizatorul nu există")
    UserManager.update_password(username, request.new_password)
    return {
        "message": f"Parola resetată pentru '{username}'"
    }

@app.delete("/admin/users/{username}", tags=["Admin"])
async def delete_user(
    username: str,
    admin_user: TokenData = Depends(require_admin)
):
    """Șterge un utilizator. Necesită rol admin. Nu poți șterge propriul cont."""
    if username == admin_user.username:
        raise HTTPException(status_code=400, detail="Nu poți șterge propriul cont")
    if not UserManager.delete(username):
        raise HTTPException(status_code=404, detail="Utilizatorul nu există")
    return {
        "message": f"Utilizatorul '{username}' șters"
    }

# Endpoints deja existente acum cu JWT

@app.get("/")
async def root():
    """Endpoint de test îmbunătățit pentru HTTP"""
    global openwebui_adapter
    if not openwebui_adapter:
        return {"error": "HTTP Adapter nu este inițializat"}
    
    status = await openwebui_adapter.get_mcp_status()
    return {
        "message": "OpenWebUI HTTP Adapter cu client LLM prin HTTP",
        "version": "4.0.0",
        "connection_type": "HTTP",
        "mcp_connected": status.get("connected", False),
        "mcp_server_url": status.get("server_url", "unknown"),
        "tools_count": status.get("tools_count", 0),
        "llm_provider": status.get("provider", "unknown"),
        "llm_model": status.get("model", "unknown"),
        "healthy": status.get("healthy", False),
        "endpoints": {
            "login": "POST /auth/login",
            "me": "GET  /auth/me",
            "change_password": "POST /auth/change-password",
            "admin_users": "GET  /admin/users",
            "models": "/v1/models",
            "chat": "/v1/chat/completions", 
            "status": "/v1/mcp/status",
            "tools": "/v1/mcp/tools",
            "restart": "/v1/mcp/restart"
        }
    }

@app.get("/health")
async def health_check():
    """Health check pentru monitoring HTTP"""
    global openwebui_adapter
    
    if not openwebui_adapter:
        raise HTTPException(status_code=503, detail="HTTP Adapter nu este inițializat")
    
    status = await openwebui_adapter.get_mcp_status()
    
    if status.get("healthy") and status.get("connected"):
        return {"status": "healthy", "auth": "JWT enabled", "connection_type": "HTTP", "details": status}
    else:
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "connection_type": "HTTP", "details": status})

@app.get("/v1/models")
async def list_models():
    """Lista modelelor pentru OpenWebUI cu HTTP"""
    global openwebui_adapter
    
    logger.info("📋 Solicitare listă modele HTTP")
    
    # Model de bază HTTP
    base_model = {
        "id": "alfresco-mcp-http-assistant",
        "object": "model", 
        "created": int(time.time()),
        "owned_by": "mcp-http-adapter",
        "permission": [],
        "root": "alfresco-mcp-http-assistant",
        "parent": None,
    }
    
    models = [base_model]
    
    # Adaugă informații despre modelul LLM real dacă e disponibil
    if openwebui_adapter:
        try:
            status = await openwebui_adapter.get_mcp_status()
            
            if status.get("provider") and status.get("model"):
                enhanced_model = {
                    "id": f"alfresco-http-{status['provider']}-{status['model']}",
                    "object": "model",
                    "created": int(time.time()), 
                    "owned_by": f"mcp-http-{status['provider']}",
                    "permission": [],
                    "root": f"alfresco-http-{status['provider']}-{status['model']}",
                    "parent": None,
                }
                models.append(enhanced_model)
                logger.info(f"➕ Adăugat model HTTP enhanced: {enhanced_model['id']}")
                
        except Exception as e:
            logger.error(f"❌ Eroare la obținerea modelelor HTTP: {e}")
    
    response = {
        "object": "list",
        "data": models
    }
    
    logger.info(f"✅ Returnez {len(models)} modele HTTP")
    return response

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Endpoint principal pentru chat HTTP - cu suport pentru streaming
    """
    global openwebui_adapter
    
    logger.info(f"💬 Primită cerere chat HTTP: model={request.model}, mesaje={len(request.messages)}, stream={request.stream}")
    
    if not openwebui_adapter:
        logger.error("❌ HTTP Adapter nu este inițializat")
        raise HTTPException(status_code=503, detail="HTTP Adapter nu este inițializat")
    
    # Validare cerere
    if not request.messages or len(request.messages) == 0:
        logger.error("❌ Nu s-au primit mesaje pentru HTTP")
        raise HTTPException(status_code=400, detail="Nu s-au primit mesaje")
    
    alfresco_creds = get_alfresco_credentials_for_role(current_user.role)
    allowed_tools  = get_allowed_tools_for_role(current_user.role)

    logger.info(
        f"🔐 Alfresco: {alfresco_creds['username']} | "
        f"Tools permise: {allowed_tools}"
    )
    
    # Dacă este cerere pentru streaming, folosim StreamingResponse
    if request.stream:
        logger.info("🌊 Folosesc streaming HTTP response")
        return StreamingResponse(
            stream_chat_response_http(request, openwebui_adapter, current_user, alfresco_creds, allowed_tools),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    # Răspuns standard HTTP (non-streaming)
    try:
        # Log mesajele pentru debugging
        for i, msg in enumerate(request.messages):
            logger.info(f"  Mesaj HTTP {i}: {msg.role} - {msg.content[:50]}...")
        
        # Procesează chat-ul prin HTTP
        start_time = time.time()
        logger.info("🔄 Încep procesarea chat-ului HTTP...")
        
        response_content = await openwebui_adapter.process_chat_async(
            request.messages,
            alfresco_username=alfresco_creds["username"],
            alfresco_password=alfresco_creds["password"],
            allowed_tools=allowed_tools,
            user_role=current_user.role.value,
        )
        
        process_time = time.time() - start_time
        logger.info(f"⏱️ Procesarea HTTP a durat {process_time:.2f}s")
        
        # Validare răspuns
        if not response_content or not response_content.strip():
            logger.error("❌ Răspuns gol de la procesare HTTP")
            response_content = "❌ Nu am putut genera un răspuns prin HTTP. Verifică logs pentru detalii."
        
        logger.info(f"📤 Pregătesc să returnez răspuns HTTP de {len(response_content)} caractere")
        
        # Formatează răspunsul pentru OpenWebUI
        response = {
            "id": f"chatcmpl-http-{uuid.uuid4()}",
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
        
        logger.info(f"✅ Răspuns HTTP formatat cu succes pentru OpenWebUI")
        return response
        
    except Exception as e:
        logger.error(f"❌ Eroare în chat completions HTTP: {e}", exc_info=True)
        
        # Răspuns de fallback în caz de eroare HTTP
        error_response = {
            "id": f"chatcmpl-http-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"❌ Eroare la procesarea cererii HTTP: {str(e)}\n\nVerifică logs pentru mai multe detalii."
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

async def stream_chat_response_http(request: ChatRequest, adapter: OpenWebUIHTTPAdapter, current_user, alfresco_creds, allowed_tools):
    """
    Generator pentru streaming response HTTP - compatibil cu OpenWebUI
    """
    try:
        logger.info("🌊 Încep streaming HTTP response...")
        
        # Procesează chat-ul prin HTTP
        start_time = time.time()
        response_content = await adapter.process_chat_async(
            request.messages,
            alfresco_username=alfresco_creds["username"],
            alfresco_password=alfresco_creds["password"],
            allowed_tools=allowed_tools,
            user_role=current_user.role.value,
        )
        process_time = time.time() - start_time
        
        logger.info(f"⏱️ Procesarea streaming HTTP a durat {process_time:.2f}s")
        
        # Validare răspuns
        if not response_content or not response_content.strip():
            logger.error("❌ Răspuns gol pentru streaming HTTP")
            response_content = "❌ Nu am putut genera un răspuns HTTP. Verifică logs pentru detalii."
        
        logger.info(f"🌊 Streaming HTTP răspuns de {len(response_content)} caractere")
        
        # ID-ul răspunsului HTTP
        chat_id = f"chatcmpl-http-{uuid.uuid4()}"
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
        
        # Trimite chunk-ul final HTTP
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
        
        logger.info("✅ Streaming HTTP complet")
        
    except Exception as e:
        logger.error(f"❌ Eroare în streaming HTTP: {e}", exc_info=True)
        
        # Chunk de eroare HTTP
        error_chunk = {
            "id": f"chatcmpl-http-{uuid.uuid4()}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": f"❌ Eroare streaming HTTP: {str(e)}"
                    },
                    "finish_reason": "stop"
                }
            ]
        }
        
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"

# Endpoint-urile de management pentru HTTP
@app.get("/v1/mcp/status")
async def mcp_status(current_user: TokenData = Depends(get_current_user)):
    """Status al conexiunii MCP HTTP"""
    global openwebui_adapter
    
    if not openwebui_adapter:
        raise HTTPException(status_code=503, detail="HTTP Adapter nu este inițializat")
    
    status = await openwebui_adapter.get_mcp_status()
    creds  = get_alfresco_credentials_for_role(current_user.role)
    status["your_role"]       = current_user.role.value
    status["alfresco_account"] = creds["username"]
    status["allowed_tools"]   = get_allowed_tools_for_role(current_user.role)

    return status

@app.get("/v1/mcp/tools")
async def list_mcp_tools(current_user: TokenData = Depends(get_current_user)):
    """Lista tool-urilor MCP HTTP disponibile"""
    global openwebui_adapter
    
    if not openwebui_adapter:
        raise HTTPException(status_code=503, detail="HTTP Adapter nu este inițializat")
    
    all_tools = await openwebui_adapter.get_available_tools()
    allowed   = get_allowed_tools_for_role(current_user.role)
    filtered  = [t for t in all_tools if t["name"] in allowed]

    return {
        "tools":   filtered,
        "count":   len(filtered),
        "role":    current_user.role.value,
        "note":    f"{len(filtered)}/{len(all_tools)} tool-uri pentru rolul '{current_user.role.value}'"
    }

@app.post("/v1/mcp/restart")
async def restart_mcp_client(_: TokenData = Depends(require_admin)):
    """Restart clientul LLM HTTP cu MCP"""
    global openwebui_adapter
    
    if not openwebui_adapter:
        raise HTTPException(status_code=503, detail="HTTP Adapter nu este inițializat")
    
    try:
        logger.info("🔄 Restart client LLM HTTP...")
        
        # Forțează recrearea clientului HTTP
        async with openwebui_adapter.client_lock:
            if openwebui_adapter.llm_client:
                await openwebui_adapter.llm_client.cleanup_http()
            openwebui_adapter.llm_client = None
            openwebui_adapter.last_activity = 0  # Forțează recrearea
            openwebui_adapter.is_healthy = False
        
        # Testează noul client HTTP
        await openwebui_adapter._test_configuration_async()
        status = await openwebui_adapter.get_mcp_status()
        
        if status.get("connected"):
            return {"success": True, "message": "Client LLM HTTP restartat cu succes", "status": status}
        else:
            return {"success": False, "message": "Restart HTTP parțial - verifică conexiunea MCP", "status": status}
            
    except Exception as e:
        logger.error(f"❌ Eroare restart HTTP: {e}")
        raise HTTPException(status_code=500, detail=f"Eroare restart HTTP: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    import signal
    
    def signal_handler(signum, frame):
        """Handler pentru semnale de sistem HTTP"""
        logger.info(f"🛑 Primit semnal {signum} - opresc HTTP adapter-ul...")
        if openwebui_adapter:
            asyncio.run(openwebui_adapter.cleanup())
        sys.exit(0)
    
    # Înregistrează handlere pentru semnale
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🚀 Pornesc OpenWebUI HTTP Adapter...")
    
    # Pornește serverul HTTP
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8001,
        log_level="info"
    )