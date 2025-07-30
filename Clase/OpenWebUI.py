import asyncio
import os
import sys
import time
import threading
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
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

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = 0.7

class OpenWebUIAdapter:
    """
    Adapter corrigat pentru OpenWebUI
    """
    
    def __init__(self, config_path: str = "llm_config.json"):
        self.config_path = config_path
        self.llm_client = None
        self.client_lock = threading.Lock()
        self.last_activity = time.time()
        self.session_timeout = 1800  # 30 minute
        self.is_healthy = False
        
        logger.info("🔧 OpenWebUI Adapter inițializat")
        
        # Testează configurația la inițializare
        self._test_configuration()

    def _test_configuration(self):
        """Testează configurația și conexiunea la pornire"""
        try:
            # Verifică dacă fișierul de configurare există
            if not os.path.exists(self.config_path):
                logger.error(f"❌ Fișierul de configurare {self.config_path} nu există!")
                return
            
            # Încearcă să creeze un client de test
            test_client = self.get_or_create_llm_client()
            if test_client:
                logger.info("✅ Configurația este validă")
                self.is_healthy = True
            else:
                logger.error("❌ Nu s-a putut crea clientul LLM")
                
        except Exception as e:
            logger.error(f"❌ Eroare la testarea configurației: {e}")

    def get_or_create_llm_client(self) -> MCPStdioLLMClient:
        """
        Obține clientul LLM cu logging îmbunătățit
        """
        with self.client_lock:
            current_time = time.time()
            
            # Verifică dacă clientul există și este încă valid
            if self.llm_client is None or (current_time - self.last_activity > self.session_timeout):
                if self.llm_client is not None:
                    logger.info("🔄 Recreez clientul LLM (session timeout)")
                    try:
                        self.llm_client.stop_mcp_server()
                    except Exception as e:
                        logger.warning(f"⚠️ Eroare la oprirea clientului vechi: {e}")
                
                logger.info(f"🚀 Creez nou client LLM cu config: {self.config_path}")
                
                try:
                    self.llm_client = MCPStdioLLMClient(self.config_path)
                    
                    # Pornește serverul MCP
                    if self.llm_client.start_mcp_server():
                        logger.info("✅ Client LLM cu MCP creat cu succes")
                        self.is_healthy = True
                    else:
                        logger.warning("⚠️ Client LLM creat dar fără conexiune MCP")
                        self.is_healthy = False
                        
                except Exception as e:
                    logger.error(f"❌ Eroare crearea clientului LLM: {e}")
                    self.is_healthy = False
                    raise
            
            self.last_activity = current_time
            return self.llm_client

    async def process_chat_async(self, messages: List[ChatMessage]) -> str:
        """
        Procesează chat-ul cu debugging îmbunătățit și error handling
        """
        def run_sync_chat():
            try:
                logger.info("🔄 Încep procesarea cererii...")
                
                # Obține clientul LLM
                client = self.get_or_create_llm_client()
                
                if not client:
                    error_msg = "❌ Nu s-a putut inițializa clientul LLM. Verifică configurația."
                    logger.error(error_msg)
                    return error_msg
                
                # Extrage ultima cerere a utilizatorului
                user_message = messages[-1].content if messages else ""
                
                if not user_message.strip():
                    return "ℹ️ Te rog să îmi spui ce vrei să fac."
                
                logger.info(f"📝 Procesez mesaj de la user: {user_message[:100]}...")
                
                # Verifică conexiunea MCP
                if client.mcp_connected and client.mcp_tools:
                    logger.info(f"🔗 MCP conectat cu {len(client.mcp_tools)} tools disponibile")
                    
                    # Analizează și apelează tool-uri MCP
                    logger.info("🛠️ Apelez tools MCP...")
                    tool_results = client.analyze_intent_and_call_tools(user_message)
                    logger.info(f"✅ Tool results: {len(tool_results) if tool_results else 0} rezultate")
                    
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
                    logger.info("📋 Creez prompt îmbunătățit...")
                    enhanced_prompt = client.create_enhanced_prompt(user_message, tool_results)
                    
                    if context_str:
                        enhanced_prompt = enhanced_prompt.replace(
                            f"Întrebarea curentă: {user_message}", 
                            f"{context_str}Întrebarea curentă: {user_message}"
                        )
                    
                    logger.info("🤖 Trimit prompt către LLM...")
                    logger.debug(f"Prompt complet: {enhanced_prompt[:200]}...")
                    
                    # Obține răspunsul de la LLM
                    response = client.query_llm_with_retry(enhanced_prompt, max_tokens=500)
                    
                    if response:
                        logger.info(f"✅ Răspuns primit de la LLM: {len(response)} caractere")
                        logger.debug(f"Răspuns: {response[:200]}...")
                        return response
                    else:
                        error_msg = "❌ Nu am primit răspuns de la LLM."
                        logger.error(error_msg)
                        return error_msg
                        
                else:
                    logger.warning("⚠️ MCP nu este conectat - folosesc fallback")
                    
                    # Fallback dacă MCP nu este conectat
                    fallback_prompt = f"""Ești un asistent AI pentru Alfresco Document Management System.

Utilizatorul întreabă: {user_message}

Din păcate, nu am acces la tool-urile MCP Alfresco în acest moment. 
Te rog să explici ce ai fi vrut să faci și încearcă din nou mai târziu.

Pentru operațiuni Alfresco disponibile de obicei:
- Listarea fișierelor și folderelor  
- Crearea de foldere noi
- Căutarea în documente  
- Obținerea de informații despre noduri

Răspuns:"""
                    
                    logger.info("🤖 Folosesc fallback prompt...")
                    response = client.query_llm_with_retry(fallback_prompt, max_tokens=300)
                    
                    if response:
                        logger.info(f"✅ Răspuns fallback primit: {len(response)} caractere")
                        return response
                    else:
                        error_msg = "❌ Nu am primit răspuns nici cu fallback."
                        logger.error(error_msg)
                        return error_msg
                    
            except Exception as e:
                error_msg = f"❌ Eroare în procesarea chat-ului: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return error_msg
        
        # Rulează în thread separar pentru a nu bloca FastAPI
        logger.info("🔄 Lansez procesarea în executor...")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_sync_chat)
        logger.info(f"📤 Rezultat final: {len(result) if result else 0} caractere")
        return result

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Obține lista tool-urilor cu error handling îmbunătățit"""
        def get_tools_sync():
            try:
                client = self.get_or_create_llm_client()
                if not client:
                    logger.warning("⚠️ Nu s-a putut obține clientul LLM pentru tools")
                    return []
                    
                if client.mcp_connected and client.mcp_tools:
                    tools_info = []
                    for tool_name, tool_data in client.mcp_tools.items():
                        tools_info.append({
                            "name": tool_name,
                            "description": tool_data.get("description", "Fără descriere"),
                            "parameters": list(tool_data.get("inputSchema", {}).get("properties", {}).keys())
                        })
                    logger.info(f"🛠️ Returnez {len(tools_info)} tools")
                    return tools_info
                else:
                    logger.warning("⚠️ MCP nu este conectat sau nu sunt tools disponibile")
                    return []
            except Exception as e:
                logger.error(f"❌ Eroare obținere tool-uri: {e}")
                return []
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_tools_sync)
        return result

    async def get_mcp_status(self) -> Dict[str, Any]:
        """Status îmbunătățit cu mai multe informații"""
        def get_status_sync():
            try:
                client = self.get_or_create_llm_client()
                if not client:
                    return {
                        "connected": False,
                        "error": "Nu s-a putut crea clientul LLM",
                        "tools_count": 0,
                        "resources_count": 0,
                        "healthy": False
                    }
                    
                status = {
                    "connected": client.mcp_connected,
                    "tools_count": len(client.mcp_tools),
                    "resources_count": len(client.mcp_resources),
                    "tools": list(client.mcp_tools.keys()),
                    "process_running": client.mcp_process is not None and client.mcp_process.poll() is None,
                    "provider": getattr(client, 'provider', 'unknown'),
                    "model": getattr(client, 'model', 'unknown'),
                    "last_activity": self.last_activity,
                    "config_path": self.config_path,
                    "healthy": self.is_healthy,
                    "session_timeout": self.session_timeout
                }
                
                return status
            except Exception as e:
                logger.error(f"❌ Eroare obținere status: {e}")
                return {
                    "connected": False,
                    "error": str(e),
                    "tools_count": 0,
                    "resources_count": 0,
                    "healthy": False
                }
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_status_sync)
        return result

    def cleanup(self):
        """Curăță resursele"""
        with self.client_lock:
            if self.llm_client:
                try:
                    self.llm_client.stop_mcp_server()
                    logger.info("🧹 Resurse LLM client curățate")
                except Exception as e:
                    logger.error(f"⚠️ Eroare cleanup: {e}")
                finally:
                    self.llm_client = None
                    self.is_healthy = False
