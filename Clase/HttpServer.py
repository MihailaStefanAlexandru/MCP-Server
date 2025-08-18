"""
Server MCP pentru Alfresco - versiune HTTP REST API (CORECTATĂ)
"""
import asyncio
import uvicorn
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import mcp.types as types

from Clase.MinimalAlfrescoServer import MinimalAlfrescoServer

class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str
    params: Optional[Dict[str, Any]] = None

class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

class MCPNotification(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None

class HTTPAlfrescoMCPServer:
    def __init__(self, base_url: str, username: str, password: str, port: int = 8002):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.port = port

        self.alfresco_server = MinimalAlfrescoServer(
            base_url=base_url,
            username=username,
            password=password
        )

        self.initialized = False
        self.capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {}
        }

        # SOLUȚIA: Definim tool-urile manual în loc să încercăm să le extragem din serverul MCP
        self.tools_registry = self._define_tools()

        self.app = FastAPI(
            title="Alfresco MCP HTTP Server",
            description="Server MCP pentru Alfresco cu comunicare HTTP",
            version="1.0.0"
        )

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self.setup_routes()

    def _define_tools(self) -> List[Dict[str, Any]]:
        """Definește manual tool-urile disponibile - SOLUȚIA PRINCIPALĂ"""
        return [
            {
                "name": "list_root_children",
                "description": "Listează fișierele și folderele din root-ul Alfresco",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "maxItems": {
                            "type": "integer",
                            "description": "Numărul maxim de elemente de returnat (default: 20)",
                            "default": 20
                        }
                    }
                }
            },
            {
                "name": "get_node_children",
                "description": "Listează conținutul unui folder specific",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "ID-ul nodului/folderului"
                        },
                        "maxItems": {
                            "type": "integer",
                            "description": "Numărul maxim de elemente",
                            "default": 20
                        }
                    },
                    "required": ["node_id"]
                }
            },
            {
                "name": "create_folder",
                "description": "Creează un folder nou",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Numele folderului"
                        },
                        "parent_id": {
                            "type": "string",
                            "description": "ID-ul folderului părinte (default: -root-)",
                            "default": "-root-"
                        },
                        "title": {
                            "type": "string",
                            "description": "Titlul folderului (opțional)"
                        },
                        "description": {
                            "type": "string",
                            "description": "Descrierea folderului (opțional)"
                        }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "get_node_info",
                "description": "Obține informații despre un nod/fișier/folder specific",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "ID-ul nodului"
                        }
                    },
                    "required": ["node_id"]
                }
            },
            {
                "name": "delete_node",
                "description": "Șterge un nod/fișier/folder",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "ID-ul nodului de șters"
                        },
                        "permanent": {
                            "type": "boolean",
                            "description": "Ștergere permanentă (default: false - merge în trash)",
                            "default": False
                        }
                    },
                    "required": ["node_id"]
                }
            },
            {
                "name": "get_node_id_by_name",
                "description": "Returnează ID-ul unui fișier sau folder Alfresco după nume (căutare în root)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Numele nodului (fișier sau folder)"
                        }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "browse_by_path",
                "description": "Navighează la un folder folosind calea (path) în loc de ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Calea folderului (ex: /Company Home/Sites/test-site)",
                            "default": "/"
                        }
                    }
                }
            }
        ]

    def setup_routes(self):
        """Configurează rutele HTTP pentru protocolul MCP"""

        @self.app.post("/mcp", response_model=MCPResponse)
        async def handle_mcp_request(request: MCPRequest):
            """Handler principal pentru cereri MCP JSON-RPC"""
            try:
                print(f"📥 Cerere MCP: {request.method}")

                # Procesează cererea în funcție de metodă
                if request.method == "initialize":
                    result = await self.handle_initialize(request.params or {})
                elif request.method == "tools/list":
                    result = await self.handle_tools_list()
                elif request.method == "tools/call":
                    result = await self.handle_tools_call(request.params or {})
                elif request.method == "resources/list":
                    result = await self.handle_resources_list()
                elif request.method == "resources/read":
                    result = await self.handle_resources_read(request.params or {})
                elif request.method == "prompts/list":
                    result = await self.handle_prompts_list()
                elif request.method == "prompts/get":
                    result = await self.handle_prompts_get(request.params or {})
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Metodă necunoscută: {request.method}"
                    )
                
                return MCPResponse(
                    id=request.id,
                    result=result
                )
            
            except Exception as e:
                print(f"❌ Eroare procesare cerere {request.method}: {e}")
                return MCPResponse(
                    id=request.id,
                    error={
                        "code": -32603,
                        "message": "Internal error",
                        "data": str(e)
                    }
                )
            
        @self.app.post("/mcp/notify")
        async def handle_mcp_notification(notification: MCPNotification):
            """Handler pentru notificări MCP"""

            try:
                print(f"📢 Notificare MCP: {notification.method}")

                if notification.method == "notifications/initialized":
                    print("✅ Client confirmat că inițializarea e completă")
                
                return {"status": "ok"}
            
            except Exception as e:
                print(f"❌ Eroare procesare notificare: {e}")
                raise HTTPException(status_code=500, detail=str(e))
            
        @self.app.get("/health")
        async def health_check():
            """Verificare stare server"""
            return {
                "status": "healthy",
                "initialized": self.initialized,
                "alfresco_url": self.base_url,
                "timestamp": datetime.now().isoformat()
            }
        
        @self.app.get("/capabilities")
        async def get_capabilities():
            """Returnează capabilitățile serverului"""
            return self.capabilities
        
        @self.app.get("/debug/tools")
        async def debug_tools():
            """Debug endpoint pentru a vedea tool-urile - ÎMBUNĂTĂȚIT"""
            debug_info = {
                "tools_registry_count": len(self.tools_registry),
                "tools_registry": [tool["name"] for tool in self.tools_registry],
                "initialized": self.initialized,
                "alfresco_server_type": type(self.alfresco_server).__name__
            }
            
            # Informații despre serverul MCP intern
            mcp_server = self.alfresco_server.get_server()
            debug_info.update({
                "mcp_server_type": type(mcp_server).__name__,
                "mcp_server_attributes": [attr for attr in dir(mcp_server) if not attr.startswith('__')],
            })
            
            # Încearcă să acceseze handler-urile MCP (dacă există)
            try:
                if hasattr(mcp_server, '_tool_handlers'):
                    debug_info["mcp_tool_handlers"] = list(mcp_server._tool_handlers.keys())
                if hasattr(mcp_server, '_tools'):
                    debug_info["mcp_tools"] = list(mcp_server._tools.keys())
            except Exception as e:
                debug_info["mcp_handlers_error"] = str(e)
            
            return debug_info
        
    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handler pentru inițializarea protocolului MCP"""
        protocol_version = params.get("protocolVersion", "2024-11-05")
        client_capabilities = params.get("capabilities", {})
        client_info = params.get("clientInfo", {})

        print(f"🤝 Inițializare MCP de la client: {client_info.get('name', 'Unknown')}")
        print(f"📋 Protocol version: {protocol_version}")

        # Configurează capabilitățile serverului
        server_capabilities = {
            "tools": {
                "listChanged": False
            },
            "resources": {
                "subscribe": False,
                "listChanged": False
            },
            "prompts": {
                "listChanged": False
            }
        }

        self.capabilities = server_capabilities
        self.initialized = True

        # Inițializează conexiunea cu Alfresco (dacă nu e deja inițializată)
        try:
            if not hasattr(self.alfresco_server, '_session'):
                await self.alfresco_server.ensure_connection()
            print("✅ Conexiune Alfresco verificată")
        except Exception as e:
            print(f"⚠️ Conexiune Alfresco limitată: {e}")
        
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": server_capabilities,
            "serverInfo": {
                "name": "alfresco-mcp-http-server",
                "version": "1.0.0"
            }
        }

    async def handle_tools_list(self) -> Dict[str, Any]:
        """Returnează lista tool-urilor disponibile - SOLUȚIA CORECTATĂ"""
        if not self.initialized:
            raise HTTPException(status_code=400, detail="Server nu este inițializat")
        
        try:
            print(f"🔧 Returnez {len(self.tools_registry)} tool-uri din registry")
            return {"tools": self.tools_registry}
        
        except Exception as e:
            print(f"❌ Eroare la listarea tool-urilor: {e}")
            return {"tools": []}
    
    async def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execută un tool MCP - SOLUȚIA CORECTATĂ"""

        if not self.initialized:
            raise HTTPException(status_code=400, detail="Server nu este inițializat")
        
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise HTTPException(status_code=400, detail="Lipsește numele tool-ului")
        
        print(f"🔧 Execut tool: {tool_name} cu argumente: {arguments}")

        # Verifică dacă tool-ul există în registry
        tool_exists = any(tool["name"] == tool_name for tool in self.tools_registry)
        if not tool_exists:
            raise HTTPException(status_code=404, detail=f"Tool-ul '{tool_name}' nu există")
        
        try:
            # SOLUȚIA: Apelează direct metodele din MinimalAlfrescoServer în loc să accesezi handler-urile MCP
            result = await self._execute_tool_directly(tool_name, arguments)

            # Formatează rezultatul conform protocolului MCP
            if isinstance(result, str):
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": result
                        }
                    ]
                }
            elif isinstance(result, dict) and "content" in result:
                # Dacă rezultatul are deja formatul MCP
                return result
            elif isinstance(result, dict):
                # Convertim dict-ul într-un format MCP
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": str(result)
                        }
                    ]
                }
            elif isinstance(result, list):
                # Dacă elementele sunt dict, le returnezi direct
                if all(isinstance(r, dict) and "type" in r for r in result):
                    return {
                        "content": result
                    }
                # Dacă sunt obiecte arbitrare, le convertim în stringuri
                else:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": str(r)
                            } for r in result
                        ]
                    }
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": str(result)
                        }
                    ]
                }
            
        except Exception as e:
            print(f"❌ Eroare execuție tool {tool_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Eroare execuție tool: {str(e)}")

    async def _execute_tool_directly(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execută direct metodele din MinimalAlfrescoServer fără să treacă prin serverul MCP"""
        
        # Asigură-te că conexiunea este stabilită
        await self.alfresco_server.ensure_connection()
        
        # Mapează tool-urile la metodele corespunzătoare
        if tool_name == "list_root_children":
            max_items = arguments.get("maxItems", 20)
            return await self.alfresco_server.list_root_children(max_items)
            
        elif tool_name == "get_node_children":
            node_id = arguments["node_id"]
            max_items = arguments.get("maxItems", 20)
            return await self.alfresco_server.get_node_children(node_id, max_items)
            
        elif tool_name == "create_folder":
            name = arguments["name"]
            parent_id = arguments.get("parent_id", "-root-")
            title = arguments.get("title")
            description = arguments.get("description")
            return await self.alfresco_server.create_folder(name, parent_id, title, description)
            
        elif tool_name == "get_node_info":
            node_id = arguments["node_id"]
            return await self.alfresco_server.get_node_info(node_id)
            
        elif tool_name == "delete_node":
            node_id = arguments["node_id"]
            permanent = arguments.get("permanent", False)
            return await self.alfresco_server.delete_node(node_id, permanent)
            
        elif tool_name == "get_node_id_by_name":
            name = arguments["name"]
            return await self.alfresco_server.get_node_id_by_name(name)
            
        elif tool_name == "browse_by_path":
            path = arguments.get("path", "/")
            return await self.alfresco_server.browse_by_path(path)
            
        else:
            raise ValueError(f"Tool necunoscut: {tool_name}")
        
    async def handle_resources_list(self) -> Dict[str, Any]:
        """Returnează lista resurselor disponibile"""
        if not self.initialized:
            raise HTTPException(status_code=400, detail="Server nu este inițializat")
        
        # Pentru moment, nu avem resurse definite în serverul minimal
        resources = []
        
        print(f"📁 Returnez {len(resources)} resurse")
        return {"resources": resources}
    
    async def handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Citește o resursă specifică"""
        if not self.initialized:
            raise HTTPException(status_code=400, detail="Server nu este inițializat")
        
        uri = params.get("uri")
        if not uri:
            raise HTTPException(status_code=400, detail="Lipsește URI-ul resursei")
        
        # Implementare placeholder pentru citirea resurselor
        raise HTTPException(status_code=404, detail="Resursa nu a fost găsită")
    
    async def handle_prompts_list(self) -> Dict[str, Any]:
        """Returnează lista prompt-urilor disponibile"""
        if not self.initialized:
            raise HTTPException(status_code=400, detail="Server nu este inițializat")
        
        # Pentru moment, nu avem prompt-uri definite în serverul minimal
        prompts = []
        
        print(f"💭 Returnez {len(prompts)} prompt-uri")
        return {"prompts": prompts}
    
    async def handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Obține un prompt specific"""
        if not self.initialized:
            raise HTTPException(status_code=400, detail="Server nu este inițializat")
        
        name = params.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="Lipsește numele prompt-ului")
        
        # Implementare placeholder pentru prompt-uri
        raise HTTPException(status_code=404, detail="Prompt-ul nu a fost găsit")
    
    async def cleanup(self):
        """Curăță resursele serverului"""
        try:
            await self.alfresco_server.cleanup()
            print("✅ Server HTTP curățat")
        except Exception as e:
            print(f"⚠️ Eroare la cleanup: {e}")

    def run(self, host: str = "0.0.0.0"):
        """Pornește serverul HTTP"""
        print(f"🚀 Server MCP Alfresco HTTP pornit pe {host}:{self.port}")
        print(f"📍 Alfresco URL: {self.base_url}")
        print(f"🏥 Health check: http://{host}:{self.port}/health")
        print(f"🔧 Endpoint MCP: http://{host}:{self.port}/mcp")
        print(f"🐛 Debug tools: http://{host}:{self.port}/debug/tools")
        
        try:
            uvicorn.run(
                self.app,
                host=host,
                port=self.port,
                log_level="info",
                access_log=True
            )
        except KeyboardInterrupt:
            print("🛑 Server oprit de utilizator")
        finally:
            asyncio.run(self.cleanup())