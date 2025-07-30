import json
import sys
import os
from typing import Any, Dict, List
import httpx
from urllib.parse import urljoin
import base64

from mcp.server import Server
from mcp.types import (
    Tool,
)
import mcp.types as types

class MinimalAlfrescoServer:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.client = None
        self.server = Server("minimal-alfresco-server")
        self.connection_tested = False
        self.setup_handlers()
    
    def setup_handlers(self):
        """Configurează handler-urile pentru configurația minimală"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """Tool-uri adaptate pentru configurația minimală (fără search)"""
            return [
                Tool(
                    name="list_root_children",
                    description="Listează fișierele și folderele din root-ul Alfresco",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "maxItems": {
                                "type": "integer",
                                "description": "Numărul maxim de elemente de returnat (default: 10)",
                                "default": 20
                            }
                        }
                    }
                ),
                Tool(
                    name="get_node_children",
                    description="Listează conținutul unui folder specific",
                    inputSchema={
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
                ),
                Tool(
                    name="create_folder",
                    description="Creează un folder nou",
                    inputSchema={
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
                ),
                Tool(
                    name="get_node_info",
                    description="Obține informații despre un nod/fișier/folder specific",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "node_id": {
                                "type": "string",
                                "description": "ID-ul nodului"
                            }
                        },
                        "required": ["node_id"]
                    }
                ),
                Tool(
                    name="delete_node",
                    description="Șterge un nod/fișier/folder",
                    inputSchema={
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
                ),
                Tool(
                    name="browse_by_path",
                    description="Navighează la un folder folosind calea (path) în loc de ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Calea folderului (ex: /Company Home/Sites/test-site)",
                                "default": "/"
                            }
                        }
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            """Execută tool-urile cu răspunsuri optimizate pentru TinyLlama"""
            try:
                if not self.connection_tested:
                    await self.ensure_connection()
                
                result = None
                context = ""
                
                if name == "list_root_children":
                    result = await self.list_root_children(min(arguments.get("maxItems", 10), 10))
                    context = "root folder"
                elif name == "get_node_children":
                    node_id = arguments["node_id"]
                    result = await self.get_node_children(node_id, min(arguments.get("maxItems", 10), 10))
                    context = f"folder {node_id}"
                elif name == "create_folder":
                    result = await self.create_folder(
                        arguments["name"],
                        arguments.get("parent_id", "-root-"),
                        arguments.get("title"),
                        arguments.get("description")
                    )
                    context = "folder creation"
                elif name == "get_node_info":
                    result = await self.get_node_info(arguments["node_id"])
                    context = "node information"
                elif name == "delete_node":
                    result = await self.delete_node(arguments["node_id"], arguments.get("permanent", False))
                    context = "node deletion"
                elif name == "browse_by_path":
                    result = await self.browse_by_path(arguments.get("path", "/"))
                    context = f"path {arguments.get('path', '/')}"
                else:
                    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
                
                # Formatează pentru TinyLlama
                formatted_result = self.format_simple_response(result, context)
                
                # Răspuns mai concis
                response_text = json.dumps(formatted_result, indent=1, ensure_ascii=False)
                
                return [types.TextContent(type="text", text=response_text)]
            
            except Exception as e:
                error_msg = f"Error in {name}: {str(e)}"
                return [types.TextContent(type="text", text=json.dumps({
                    "error": True,
                    "message": error_msg,
                    "tool": name
                }, indent=1))]

    async def ensure_connection(self):
        """Conexiune optimizată pentru modele rapide"""
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=5.0),  # Timeout-uri mai mici
                follow_redirects=True
            )
            
            auth_string = base64.b64encode(f'{self.username}:{self.password}'.encode()).decode()
            self.client.headers.update({
                "Authorization": f"Basic {auth_string}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            })
        
        if not self.connection_tested:
            try:
                test_url = urljoin(self.base_url, "/alfresco/api/-default-/public/alfresco/versions/1/nodes/-root-")
                response = await self.client.get(test_url)
                response.raise_for_status()
                self.connection_tested = True
                # Log mai concis pentru TinyLlama
                print("✅ Alfresco connected", file=sys.stderr)
            except Exception as e:
                raise Exception(f"Cannot connect to Alfresco: {str(e)}")
    
    async def list_root_children(self, max_items: int = 20) -> Dict[str, Any]:
        """Listează conținutul root-ului"""
        return await self.get_node_children("-root-", max_items)
    
    async def get_node_children(self, node_id: str, max_items: int = 20) -> Dict[str, Any]:
        """Obține copiii unui nod"""
        url = urljoin(self.base_url, f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}/children")
        
        params = {
            "maxItems": max_items,
            "skipCount": 0,
            "include": "properties,aspectNames,path"
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        # Formatăm rezultatele să fie mai ușor de citit
        items = []
        for entry in data.get("list", {}).get("entries", []):
            node = entry["entry"]
            item_info = {
                "id": node.get("id"),
                "name": node.get("name"),
                "type": "folder" if node.get("isFolder") else "file",
                "nodeType": node.get("nodeType"),
                "created": node.get("createdAt"),
                "modified": node.get("modifiedAt"),
                "createdBy": node.get("createdByUser", {}).get("displayName"),
                "modifiedBy": node.get("modifiedByUser", {}).get("displayName"),
            }
            
            # Adaugă informații specifice fișierelor
            if not node.get("isFolder") and "content" in node:
                item_info.update({
                    "size": node["content"].get("sizeInBytes"),
                    "mimeType": node["content"].get("mimeType"),
                    "encoding": node["content"].get("encoding")
                })
            
            # Adaugă path dacă este disponibil
            if "path" in node:
                item_info["path"] = node["path"].get("name")
            
            items.append(item_info)
        
        return {
            "parent_id": node_id,
            "items": items,
            "total": len(items),
            "message": f"Am găsit {len(items)} elemente în nodul {node_id}"
        }
    
    async def create_folder(self, name: str, parent_id: str = "-root-", title: str = None, description: str = None) -> Dict[str, Any]:
        """Creează un folder nou"""
        url = urljoin(self.base_url, f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children")
        
        folder_data = {
            "name": name,
            "nodeType": "cm:folder"
        }
        
        # Adaugă proprietăți opționale
        if title or description:
            folder_data["properties"] = {}
            if title:
                folder_data["properties"]["cm:title"] = title
            if description:
                folder_data["properties"]["cm:description"] = description
        
        response = await self.client.post(url, json=folder_data)
        response.raise_for_status()
        
        result = response.json()
        
        return {
            "created": True,
            "folder_id": result["entry"]["id"],
            "folder_name": result["entry"]["name"],
            "parent_id": parent_id,
            "message": f"Folderul '{name}' a fost creat cu succes"
        }
    
    async def get_node_info(self, node_id: str) -> Dict[str, Any]:
        """Obține informații detaliate despre un nod"""
        url = urljoin(self.base_url, f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}")
        
        params = {
            "include": "properties,aspectNames,path,permissions,allowableOperations"
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        
        node = response.json()["entry"]
        
        # Formatează informațiile
        info = {
            "id": node.get("id"),
            "name": node.get("name"),
            "type": "folder" if node.get("isFolder") else "file",
            "nodeType": node.get("nodeType"),
            "created": node.get("createdAt"),
            "modified": node.get("modifiedAt"),
            "createdBy": node.get("createdByUser", {}).get("displayName"),
            "modifiedBy": node.get("modifiedByUser", {}).get("displayName"),
            "parentId": node.get("parentId")
        }
        
        # Path info
        if "path" in node:
            info["path"] = node["path"].get("name")
            info["isRoot"] = node["path"].get("isRoot", False)
        
        # Content info pentru fișiere
        if not node.get("isFolder") and "content" in node:
            info["content"] = {
                "size": node["content"].get("sizeInBytes"),
                "mimeType": node["content"].get("mimeType"),
                "encoding": node["content"].get("encoding")
            }
        
        # Properties
        if "properties" in node:
            info["properties"] = {}
            props = node["properties"]
            if "cm:title" in props:
                info["properties"]["title"] = props["cm:title"]
            if "cm:description" in props:
                info["properties"]["description"] = props["cm:description"]
        
        return {
            "node": info,
            "message": f"Informații pentru nodul '{node.get('name')}'",
            "items": [
                {"label": "ID", "value": node.get("id")},
                {"label": "Tip", "value": "folder" if node.get("isFolder") else "file"},
                {"label": "Tip nod", "value": node.get("nodeType")},
                {"label": "Creat la", "value": node.get("createdAt")},
                {"label": "Modificat la", "value": node.get("modifiedAt")},
                {"label": "Creat de", "value": node.get("createdByUser", {}).get("displayName")},
                {"label": "Modificat de", "value": node.get("modifiedByUser", {}).get("displayName")},
                {"label": "ID Părinte", "value": node.get("parentId")}
            ]
        }
    
    async def delete_node(self, node_id: str, permanent: bool = False) -> Dict[str, Any]:
        """Șterge un nod"""
        url = urljoin(self.base_url, f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}")
        
        params = {}
        if permanent:
            params["permanent"] = "true"
        
        response = await self.client.delete(url, params=params)
        response.raise_for_status()
        
        return {
            "deleted": True,
            "node_id": node_id,
            "permanent": permanent,
            "message": f"Nodul {node_id} a fost șters {'permanent' if permanent else '(în trash)'}"
        }
    
    async def browse_by_path(self, path: str = "/") -> Dict[str, Any]:
        """Navighează folosind path-ul"""
        # Pentru configurația minimală, încercăm să găsim nodul după path
        # Aceasta este o funcție simplificată
        
        if path == "/" or path == "":
            # Root
            return await self.list_root_children()
        
        # Încercăm să găsim path-ul prin Company Home
        # Aceasta este o implementare simplificată
        try:
            # Căutăm în root pentru "Company Home"
            root_children = await self.get_node_children("-root-", 100)
            
            company_home_id = None
            for item in root_children["items"]:
                if item["name"] == "Company Home" and item["type"] == "folder":
                    company_home_id = item["id"]
                    break
            
            if not company_home_id:
                return {
                    "error": True,
                    "message": "Nu am găsit 'Company Home' în root. Pentru configurația minimală folosește ID-uri de noduri."
                }
            
            # Pentru simplitate, returnăm conținutul Company Home
            result = await self.get_node_children(company_home_id)
            result["message"] = f"Navighează la path: {path} (Company Home)"
            return result
            
        except Exception as e:
            return {
                "error": True,
                "message": f"Nu pot naviga la path-ul '{path}': {str(e)}. În configurația minimală, folosește tool-ul 'get_node_children' cu ID-uri specifice."
            }
        
    def format_simple_response(self, result: Any, context: str = "") -> Dict[str, Any]:
        """Formatează un răspuns simplificat, text-based, pentru modele LLM mici"""
        if isinstance(result, dict):
            message = result.get("message", "")
            items = result.get("items", []) if isinstance(result.get("items", []), list) else []

            simplified_items = []
            for item in items:
                if "name" in item and "type" in item:
                    name = item.get("name", "")
                    node_type = item.get("type", "")
                    node_id = item.get("id", "")
                    simplified_items.append(f"- {name} [{node_type}] (ID: {node_id})")
                elif "label" in item and "value" in item:
                    # E o informație cheie-valoare
                    simplified_items.append(f"{item['label']}: {item['value']}")

            return {
                "context": context,
                "summary": message,
                "items": simplified_items
            }

        elif isinstance(result, str):
            return {
                "context": context,
                "text": result
            }

        else:
            return {
                "context": context,
                "data": result
            }
    
    async def cleanup(self):
        """Curăță resursele"""
        if self.client:
            await self.client.aclose()
    
    def get_server(self) -> Server:
        return self.server