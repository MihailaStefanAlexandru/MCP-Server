"""
Server MCP pentru Alfresco - versiune HTTP REST API
"""
import asyncio
import sys
import os
import json
import uvicorn
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

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

        self.initialized=False
        self.capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {}
        }

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
                elif request.method == "tools/calls":
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
                        status_code = 400,
                        detail = f"Metodă necunoscută: {request.method}"
                    )
                
                return MCPResponse(
                    id = request.id,
                    result = result
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
                "status": "healty",
                "initialized": self.initialized,
                "alfresco_url": self.base_url,
                "timestamp": datetime.now().isoformat()
            }
        
        @self.app.get("/capabilities")
        async def get_capabilities():
            """Returnează capabilitățile serverului"""
            return self.capabilities
        
    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handler pentru inițializarea protocolului MCP"""
        protocol_version = params.get("protocolVersion", "2024-11-05")
        client_capabilities = params.get("capabilities", {})
        client_info = params.get("cleintInfo", {})

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
                await self.alfresco_server.initialize()
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
        """Returnează lista tool-urilor disponibile"""
        if not self.initialized:
            raise HTTPException(status_code=400, detail="Server nu este inițializat")
        
        mcp_server = self.alfresco_server.get_server()
        tools = []

        # Iterează prin tool-urile înregistrate
        for name, handler in mcp_server._tools.items():
            tool_info = {
                "name": name, 
                "description": getattr(handler, '__doc__', f"Tool Alfresco: {name}"),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }

            # Încearcă să extragi schema din handler
            if hasattr(handler, '_input_schema'):
                tool_info["inputSchema"] = handler._input_schema

            tools.append(tool_info)

        print(f"🔧 Returnez {len(tools)} tool-uri")
        return {"tools": tools}
    
    async def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execută un tool MCP"""

        if not self.initialized:
            raise HTTPException(status_code=400, detail="Server nu este inițializat")
        
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise HTTPException(status_code=400, detail="Lipsește numele tool-ului")
        
        print(f"🔧 Execut tool: {tool_name}")

        # Obține serverul MCP și execută tool-ul
        mcp_server = self.alfresco_server.get_server()

        if tool_name not in mcp_server._tools:
            raise HTTPException(status_code=404, detail=f"Tool-ul '{tool_name}' nu există")
        
        try:
            # Execută tool-ul
            handler = mcp_server._tools[tool_name]
            result = await handler(**arguments)

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
            elif isinstance(result, dict):
                return result
            elif isinstance(result, list):
                # Dacă elementele sunt dict, le returnezi direct
                if all(isinstance(r, dict) for r in result):
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