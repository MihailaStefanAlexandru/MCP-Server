"""
Server MCP pentru Alfresco - versiune HTTP REST API (CORECTATĂ)
"""
import asyncio
import base64
import uvicorn
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import mcp.types as types
import httpx

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
        self.default_username = username
        self.default_password = password
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
            },
            {
                "name": "upload_file",
                "description": "Creează un fișier text într-un folder specificat",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Numele fișierului (ex: Raport_Q1.txt)"},
                        "content": {"type": "string", "description": "Conținutul textual al fișierului"},
                        "parent_id": {"type": "string", "description": "ID-ul folderului în care se creează fișierul"}
                    },
                    "required": ["name", "content", "parent_id"]
                }
            },
            {
                "name": "move_node",
                "description": "Mută un fișier sau folder dintr-un folder în altul",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string", "description": "ID-ul nodului de mutat"},
                        "target_parent_id": {"type": "string", "description": "ID-ul folderului destinație"}
                    },
                    "required": ["node_id", "target_parent_id"]
                }
            },
            {
                "name": "set_permissions",
                "description": "Setează permisiuni pe un folder: dezactivează moștenirea și adaugă permisiuni explicite",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string", "description": "ID-ul folderului"},
                        "inherit": {"type": "boolean", "description": "Dacă folderul moștenește permisiunile părintelui", "default": False},
                        "permissions": {
                            "type": "array",
                            "description": "Lista de permisiuni",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "authorityId": {"type": "string", "description": "Grup (ex: GROUP_Viewer) sau user (ex: app_viewer)"},
                                    "name": {"type": "string", "description": "Rol: Consumer, Contributor, Editor, Coordinator"}
                                },
                                "required": ["authorityId", "name"]
                            }
                        }
                    },
                    "required": ["node_id", "permissions"]
                }
            },
            {
                "name": "list_groups",
                "description": "Listează grupurile din Alfresco. Returnează id-ul real al fiecărui grup — folosește acel id ca authorityId în set_permissions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "search": {
                            "type": "string",
                            "description": "Filtrează după nume (opțional, ex: 'APP')"
                        }
                    }
                }
            }
        ]
    
    def _create_alfresco_server_for_credentials(
        self,
        username: str,
        password: str
    ) -> MinimalAlfrescoServer:
        """
        Creează un server Alfresco temporar cu credențialele specificate.
        Folosit pentru request-uri cu roluri diferite de admin.
        """
        server = MinimalAlfrescoServer(
            base_url=self.base_url,
            username=username,
            password=password
        )
        return server

    def setup_routes(self):
        """Configurează rutele HTTP pentru protocolul MCP"""

        @self.app.post("/mcp", response_model=MCPResponse)
        async def handle_mcp_request(request: MCPRequest, raw_request: Request):
            """
            Handler principal MCP JSON-RPC.
 
            Citește opțional headerele:
            - X-Alfresco-Username: contul tehnic pentru rolul userului
            - X-Alfresco-Password: parola contului tehnic
 
            Dacă sunt prezente, execută operațiunile cu acele credențiale.
            Dacă nu, folosește credențialele default din config.
            """
            try:
                print(f"📥 Cerere MCP: {request.method}")

                # Extrage credențialele din headere (dacă există)
                alfresco_username = raw_request.headers.get("X-Alfresco-Username")
                alfresco_password = raw_request.headers.get("X-Alfresco-Password")

                # Determină serverul Alfresco de folosit
                if alfresco_username and alfresco_password:
                    # Credențiale per-rol din header
                    alfresco_srv = self._create_alfresco_server_for_credentials(
                        alfresco_username, alfresco_password
                    )
                    print(f"🔐 Folosesc credențiale din header: {alfresco_username}")
                else:
                    # Credențiale default din config
                    alfresco_srv = self.alfresco_server
                    print(f"🔐 Folosesc credențiale default: {self.default_username}")

                # Procesează cererea în funcție de metodă
                if request.method == "initialize":
                    result = await self.handle_initialize(request.params or {})
                elif request.method == "tools/list":
                    result = await self.handle_tools_list()
                elif request.method == "tools/call":
                    result = await self.handle_tools_call(request.params or {}, alfresco_srv)
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
        
    def _format_result(self, result) -> Dict[str, Any]:
        """Formatează rezultatul conform protocolului MCP cu JSON corect."""
        import json
        if isinstance(result, str):
            return {"content": [{"type": "text", "text": result}]}
        elif isinstance(result, dict) and "content" in result:
            return result
        elif isinstance(result, dict):
            # IMPORTANT: json.dumps în loc de str() pentru a evita Python repr cu single quotes
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        elif isinstance(result, list):
            if all(isinstance(r, dict) and "type" in r for r in result):
                return {"content": result}
            else:
                return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        else:
            return {"content": [{"type": "text", "text": str(result)}]}
    
    async def handle_tools_call(self, params: Dict[str, Any], alfresco_srv: MinimalAlfrescoServer) -> Dict[str, Any]:
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
            result = await self._execute_tool_directly(tool_name, arguments, alfresco_srv)

            return self._format_result(result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                # Eroare de permisiuni — returnăm mesaj clar în loc să aruncăm excepție
                print(f"⛔ Acces interzis pentru {tool_name}: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": str({
                            "error": True,
                            "code": 403,
                            "message": f"Acces interzis: contul tău nu are permisiuni pentru această operațiune ({tool_name}). Contactează administratorul."
                        })
                    }]
                }
            raise
        except Exception as e:
            print(f"❌ Eroare execuție tool {tool_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Eroare execuție tool: {str(e)}")

    async def _execute_tool_directly(self, tool_name: str, arguments: Dict[str, Any], alfresco_srv: MinimalAlfrescoServer) -> Any:
        """Execută direct metodele din MinimalAlfrescoServer fără să treacă prin serverul MCP"""
        
        # Asigură-te că conexiunea este stabilită
        await alfresco_srv.ensure_connection()
        
        # Mapează tool-urile la metodele corespunzătoare
        if tool_name == "list_root_children":
            max_items = arguments.get("maxItems", 20)
            return await alfresco_srv.list_root_children(max_items)
            
        elif tool_name == "get_node_children":
            node_id = arguments["node_id"]
            max_items = arguments.get("maxItems", 20)
            return await alfresco_srv.get_node_children(node_id, max_items)
            
        elif tool_name == "create_folder":
            name = arguments["name"]
            parent_id = arguments.get("parent_id", "-root-")
            title = arguments.get("title")
            description = arguments.get("description")
            return await alfresco_srv.create_folder(name, parent_id, title, description)
            
        elif tool_name == "get_node_info":
            node_id = arguments["node_id"]
            return await alfresco_srv.get_node_info(node_id)
            
        elif tool_name == "delete_node":
            node_id = arguments["node_id"]
            permanent = arguments.get("permanent", False)
            return await alfresco_srv.delete_node(node_id, permanent)
            
        elif tool_name == "get_node_id_by_name":
            return await alfresco_srv.get_node_id_by_name(
                arguments["name"],
                arguments.get("parent_folder_name")
            )
            
        elif tool_name == "browse_by_path":
            path = arguments.get("path", "/")
            return await alfresco_srv.browse_by_path(path)
        
        elif tool_name == "upload_file":
            return await alfresco_srv.upload_file(
                arguments["name"],
                arguments["content"],
                arguments["parent_id"]
            )
        
        elif tool_name == "move_node":
            return await alfresco_srv.move_node(
                arguments["node_id"],
                arguments["target_parent_id"]
            )
        
        elif tool_name == "set_permissions":
            return await alfresco_srv.set_permissions(
                arguments["node_id"],
                arguments["permissions"],
                arguments.get("inherit", False)
            )
        
        elif tool_name == "list_groups":
            return await alfresco_srv.list_groups(arguments.get("search", ""))
            
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