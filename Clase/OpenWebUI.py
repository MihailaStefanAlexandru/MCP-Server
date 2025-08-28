#!/usr/bin/env python3
"""
OpenWebUI Adapter pentru MCP HTTP - Versiune Corectată
"""
import asyncio
import os
import time
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from Clase.MCPHTTPClient import MCPHTTPClient

# Configurare logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Modele pentru OpenWebUI
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = 0.7

class OpenWebUIHTTPAdapter:
    """
    Adapter pentru OpenWebUI cu comunicație HTTP către serverul MCP - VERSIUNE CORECTATĂ
    """
    
    def __init__(self, config_path: str = "llm_config.json"):
        self.config_path = config_path
        self.llm_client = None
        self.client_lock = asyncio.Lock()
        self.last_activity = time.time()
        self.session_timeout = 1800  # 30 minute
        self.is_healthy = False
        
        logger.info("🔧 OpenWebUI HTTP Adapter inițializat")
        
        # Testează configurația la inițializare
        asyncio.create_task(self._test_configuration_async())

    async def _test_configuration_async(self):
        """Testează configurația async"""
        try:
            if not os.path.exists(self.config_path):
                logger.error(f"❌ Fișierul de configurare {self.config_path} nu există!")
                return
            
            test_client = await self.get_or_create_llm_client()
            if test_client and test_client.mcp_connected:
                logger.info("✅ Configurația HTTP este validă")
                self.is_healthy = True
            else:
                logger.error("❌ Nu s-a putut crea clientul LLM HTTP")
                
        except Exception as e:
            logger.error(f"❌ Eroare la testarea configurației HTTP: {e}")

    async def get_or_create_llm_client(self) -> MCPHTTPClient:
        """
        Obține clientul LLM HTTP cu logging îmbunătățit
        """
        async with self.client_lock:
            current_time = time.time()
            
            # Verifică dacă clientul există și este încă valid
            if self.llm_client is None or (current_time - self.last_activity > self.session_timeout):
                if self.llm_client is not None:
                    logger.info("🔄 Recreez clientul LLM HTTP (session timeout)")
                    try:
                        await self.llm_client.cleanup_http()
                    except Exception as e:
                        logger.warning(f"⚠️ Eroare la oprirea clientului HTTP vechi: {e}")
                
                logger.info(f"🚀 Creez nou client LLM HTTP cu config: {self.config_path}")
                
                try:
                    self.llm_client = MCPHTTPClient(self.config_path)
                    
                    # Pornește serverul MCP HTTP
                    connected = await self.llm_client.start_mcp_server_http()
                    if connected:
                        logger.info("✅ Client LLM HTTP cu MCP creat cu succes")
                        self.is_healthy = True
                    else:
                        logger.warning("⚠️ Client LLM HTTP creat dar fără conexiune MCP")
                        self.is_healthy = False
                        
                except Exception as e:
                    logger.error(f"❌ Eroare crearea clientului LLM HTTP: {e}")
                    self.is_healthy = False
                    raise
            
            self.last_activity = current_time
            return self.llm_client

    async def process_chat_async(self, messages: List[ChatMessage]) -> str:
        """
        Procesează chat-ul cu server MCP HTTP - TRATEAZĂ tool_results ca STRING
        """
        try:
            logger.info("🔄 Încep procesarea cererii HTTP...")
            
            # Obține clientul LLM HTTP
            client = await self.get_or_create_llm_client()
            
            if not client:
                error_msg = "❌ Nu s-a putut inițializa clientul LLM HTTP"
                logger.error(error_msg)
                return error_msg
            
            # Extrage ultima cerere a utilizatorului
            user_message = messages[-1].content if messages else ""
            
            if not user_message.strip():
                return "ℹ️ Te rog să îmi spui ce vrei să fac."
            
            logger.info(f"📝 Procesez mesaj HTTP: {user_message[:100]}...")
            
            # Verifică conexiunea MCP HTTP
            if client.mcp_connected and client.mcp_tools:
                logger.info(f"🔗 MCP HTTP conectat cu {len(client.mcp_tools)} tools")
                
                # Analizează și apelează tool-uri MCP prin HTTP
                logger.info("🛠️ Apelez tools MCP prin HTTP...")
                tool_results = await client.analyze_intent_and_call_tools_async(user_message)
                logger.info(f"✅ Tool HTTP results: {type(tool_results)} - {len(tool_results) if isinstance(tool_results, str) else 'Not string'} caractere")
                
                # Creează context pentru răspunsul final
                context_messages = []
                if len(messages) > 1:
                    recent_messages = messages[-3:-1] if len(messages) > 3 else messages[:-1]
                    for msg in recent_messages:
                        context_messages.append(f"{msg.role.title()}: {msg.content}")
                
                context_str = ""
                if context_messages:
                    context_str = "\nContext conversație:\n" + "\n".join(context_messages) + "\n"
                
                # Creează prompt îmbunătățit
                logger.info("📋 Creez prompt îmbunătățit pentru HTTP...")
                enhanced_prompt = client.create_enhanced_prompt(user_message, tool_results)
                
                if context_str:
                    enhanced_prompt = enhanced_prompt.replace(
                        f"Întrebarea curentă: {user_message}", 
                        f"{context_str}Întrebarea curentă: {user_message}"
                    )
                
                logger.info("🤖 Trimit prompt către LLM...")
                
                # Obține răspunsul de la LLM
                response = client.query_llm_with_retry(enhanced_prompt, max_tokens=500)
                
                if response:
                    logger.info(f"✅ Răspuns HTTP primit de la LLM: {len(response)} caractere")
                    return response
                else:
                    error_msg = "❌ Nu am primit răspuns de la LLM prin HTTP."
                    logger.error(error_msg)
                    return error_msg
                    
            else:
                logger.warning("⚠️ MCP HTTP nu este conectat - folosesc fallback")
                
                # Fallback dacă MCP HTTP nu este conectat
                fallback_prompt = f"""Ești un asistent AI pentru Alfresco Document Management System.

    Utilizatorul întreabă: {user_message}

    Din păcate, nu am acces la tool-urile MCP Alfresco prin HTTP în acest moment. 
    Te rog să explici ce ai fi vrut să faci și încearcă din nou mai târziu.

    Pentru operațiuni Alfresco disponibile de obicei:
    - Listarea fișierelor și folderelor  
    - Crearea de foldere noi
    - Căutarea în documente  
    - Obținerea de informații despre noduri

    Răspuns:"""
                
                logger.info("🤖 Folosesc fallback prompt pentru HTTP...")
                response = client.query_llm_with_retry(fallback_prompt, max_tokens=300)
                
                if response:
                    logger.info(f"✅ Răspuns HTTP fallback primit: {len(response)} caractere")
                    return response
                else:
                    error_msg = "❌ Nu am primit răspuns nici cu fallback HTTP."
                    logger.error(error_msg)
                    return error_msg
                    
        except Exception as e:
            error_msg = f"❌ Eroare în procesarea chat-ului HTTP: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Obține lista tool-urilor HTTP cu error handling îmbunătățit"""
        try:
            client = await self.get_or_create_llm_client()
            if not client:
                logger.warning("⚠️ Nu s-a putut obține clientul LLM HTTP pentru tools")
                return []
                
            if client.mcp_connected and client.mcp_tools:
                tools_info = []
                for tool_name, tool_data in client.mcp_tools.items():
                    tools_info.append({
                        "name": tool_name,
                        "description": tool_data.get("description", "Fără descriere"),
                        "parameters": list(tool_data.get("inputSchema", {}).get("properties", {}).keys())
                    })
                logger.info(f"🛠️ Returnez {len(tools_info)} tools HTTP")
                return tools_info
            else:
                logger.warning("⚠️ MCP HTTP nu este conectat sau nu sunt tools disponibile")
                return []
        except Exception as e:
            logger.error(f"❌ Eroare obținere tool-uri HTTP: {e}")
            return []

    async def get_mcp_status(self) -> Dict[str, Any]:
        """Status îmbunătățit pentru HTTP"""
        try:
            client = await self.get_or_create_llm_client()
            if not client:
                return {
                    "connected": False,
                    "error": "Nu s-a putut crea clientul LLM HTTP",
                    "tools_count": 0,
                    "resources_count": 0,
                    "healthy": False,
                    "connection_type": "HTTP"
                }
                
            status = {
                "connected": client.mcp_connected,
                "tools_count": len(client.mcp_tools),
                "resources_count": len(client.mcp_resources),
                "tools": list(client.mcp_tools.keys()),
                "server_url": client.mcp_server_url,
                "provider": getattr(client, 'provider', 'unknown'),
                "model": getattr(client, 'model', 'unknown'),
                "last_activity": self.last_activity,
                "config_path": self.config_path,
                "healthy": self.is_healthy,
                "session_timeout": self.session_timeout,
                "connection_type": "HTTP"
            }
            
            # Test conexiunea HTTP
            if client.mcp_connected:
                connection_ok = await client.test_mcp_connection_http()
                status["connection_test"] = connection_ok
            
            return status
        except Exception as e:
            logger.error(f"❌ Eroare obținere status HTTP: {e}")
            return {
                "connected": False,
                "error": str(e),
                "tools_count": 0,
                "resources_count": 0,
                "healthy": False,
                "connection_type": "HTTP"
            }

    async def cleanup(self):
        """Curăță resursele HTTP"""
        async with self.client_lock:
            if self.llm_client:
                try:
                    await self.llm_client.cleanup_http()
                    logger.info("🧹 Resurse LLM HTTP client curățate")
                except Exception as e:
                    logger.error(f"⚠️ Eroare cleanup HTTP: {e}")
                finally:
                    self.llm_client = None
                    self.is_healthy = False