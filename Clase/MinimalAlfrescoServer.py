import json
import sys
import os
from typing import Any, Dict, List
import httpx
from urllib.parse import urljoin
import base64
import re

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
                                "description": "Numărul maxim de elemente de returnat (default: 20)",
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
                    name="get_node_id_by_name",
                    description="Returnează ID-ul unui fișier sau folder Alfresco după nume (căutare în root)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Numele nodului"},
                            "parent_folder_name": {"type": "string", "description": "Numele folderului părinte (opțional, pentru a evita ambiguitatea)"}
                        },
                        "required": ["name"]
                    }
                ),
                Tool(
                    name="upload_file",
                    description="Creează un fișier text într-un folder specificat",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Numele fișierului (ex: Raport_Q1.txt)"
                            },
                            "content": {
                                "type": "string",
                                "description": "Conținutul textual al fișierului"
                            },
                            "parent_id": {
                                "type": "string",
                                "description": "ID-ul folderului în care se creează fișierul"
                            }
                        },
                        "required": ["name", "content", "parent_id"]
                    }
                ),
                Tool(
                    name="move_node",
                    description="Mută un fișier sau folder dintr-un folder în altul",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "node_id": {
                                "type": "string",
                                "description": "ID-ul nodului de mutat"
                            },
                            "target_parent_id": {
                                "type": "string",
                                "description": "ID-ul folderului destinație"
                            }
                        },
                        "required": ["node_id", "target_parent_id"]
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
                ),
                Tool(
                    name="set_permissions",
                    description="Setează permisiuni pe un folder. Roluri valide: Consumer, Contributor, Editor, Coordinator",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "node_id": {
                                "type": "string",
                                "description": "ID-ul folderului"
                            },
                            "inherit": {
                                "type": "boolean",
                                "description": "Dacă folderul moștenește permisiunile părintelui",
                                "default": False
                            },
                            "permissions": {
                                "type": "array",
                                "description": "Lista de permisiuni",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "authorityId": {
                                            "type": "string",
                                            "description": (
                                                "ID-ul grupului sau utilizatorului. "
                                                "Grupurile TREBUIE să aibă prefixul GROUP_ (ex: GROUP_APP_EDITORS, GROUP_APP_VIEWER). "
                                                "Utilizatorii se specifică direct (ex: admin, john). "
                                                "Folosește list_groups pentru a vedea grupurile disponibile."
                                            )
                                        },
                                        "name": {
                                            "type": "string",
                                            "description": "Rol: Consumer, Contributor, Editor, Coordinator"
                                        }
                                    },
                                    "required": ["authorityId", "name"]
                                }
                            }
                        },
                        "required": ["node_id", "permissions"]
                    }
                ),
                Tool(
                    name="list_groups",
                    description="Listează grupurile din Alfresco. Returnează id-ul real al fiecărui grup — folosește acel id ca authorityId în set_permissions.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "search": {
                                "type": "string",
                                "description": "Filtrează după nume (opțional, ex: 'APP')"
                            }
                        }
                    }
                ),
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
                    result = await self.list_root_children(min(arguments.get("maxItems", 20), 10))
                    context = "root folder"
                elif name == "get_node_children":
                    node_id = arguments["node_id"]
                    result = await self.get_node_children(node_id, min(arguments.get("maxItems", 20), 10))
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
                    node_id = arguments.get("node_id", "")
                    # Validare rapidă înainte de HTTP call
                    import re
                    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
                    if not re.search(uuid_pattern, node_id, re.IGNORECASE):
                        return [types.TextContent(type="text", text=json.dumps({
                            "error": True,
                            "message": f"node_id '{node_id}' nu este un UUID valid. Obține mai întâi ID-ul cu list_root_children sau get_node_id_by_name.",
                            "tool": name
                        }))]
                    result = await self.get_node_info(node_id)
                    context = "node information"
                elif name == "delete_node":
                    result = await self.delete_node(arguments["node_id"], arguments.get("permanent", False))
                    context = "node deletion"
                elif name == "get_node_id_by_name":
                    result = await self.get_node_id_by_name(arguments["name"])
                    context = f"node ID for name '{arguments['name']}'"
                elif name == "browse_by_path":
                    result = await self.browse_by_path(arguments.get("path", "/"))
                    context = f"path {arguments.get('path', '/')}"
                else:
                    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
                
                response = {
                    "tool": name,
                    "context": context,
                    "result": result
                }

                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False)
                    )
                ]
            
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
        """Creează un folder nou dacă nu există deja"""

        parent_id = parent_id.strip()

        # Normalizează parent_id
        if not parent_id or parent_id in ["-", "/", "root", "root-", "-root", "ROOT"]:
            parent_id = "-root-"

        children = await self.get_node_children(parent_id, 100)

        for item in children.get("items", []):
            if item["name"] == name and item["type"] == "folder":
                return {
                    "created": False,
                    "folder_id": item["id"],
                    "message": f"Folderul '{name}' există deja"
                }

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
        import re

        # Sanitizare mai inteligentă: extrage primul UUID valid din string
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        match = re.search(uuid_pattern, node_id.strip(), re.IGNORECASE)
        
        if not match:
            return {
                "error": True,
                "message": f"node_id invalid: '{node_id}' nu conține un UUID valid"
            }
        
        node_id = match.group()  # UUID curat, garantat valid
        
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
        import re

        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        match = re.search(uuid_pattern, node_id, re.IGNORECASE)

        if not match:
            return {
                "error": True,
                "message": "node_id invalid"
            }

        node_id = match.group()

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
    
    async def get_node_id_by_name(self, name: str, parent_folder_name: str = None) -> Dict[str, Any]:
        """Caută un nod după nume în repository (căutare BFS limitată)"""

        start_node = "-root-"
        max_depth = 4

        queue = [(start_node, 0, "root")]
        visited = set()
        all_matches = []

        while queue:
            node_id, depth, current_parent_name= queue.pop(0)

            if node_id in visited:
                continue
            visited.add(node_id)

            if depth > max_depth:
                continue

            children = await self.get_node_children(node_id, 100)

            for item in children.get("items", []):
                if item["name"] == name:
                    all_matches.append({
                        "error": False,
                        "node_id": item["id"],
                        "name": item["name"],
                        "type": item["type"],
                        "parent_id": node_id,
                        "parent_name": current_parent_name
                    })

                if item["type"] == "folder":
                    queue.append((item["id"], depth + 1, item["name"]))

        if not all_matches:
            return {"error": True, "message": f"Nodul '{name}' nu a fost găsit"}

        # Dacă e specificat parent_folder_name, filtrează
        if parent_folder_name:
            filtered = [m for m in all_matches if m.get("parent_name") == parent_folder_name]
            if filtered:
                return filtered[0]
            # Dacă nu găsim în parent-ul specificat, returnăm toate match-urile cu avertisment
            return {
                "error": False,
                "node_id": all_matches[0]["node_id"],
                "name": all_matches[0]["name"],
                "type": all_matches[0]["type"],
                "parent_id": all_matches[0]["parent_id"],
                "warning": f"Nu am găsit '{name}' în '{parent_folder_name}'. Am returnat primul rezultat. Toate match-urile: {[m['parent_name'] for m in all_matches]}"
            }

        # Dacă sunt multiple match-uri fără filtru, avertizează
        if len(all_matches) > 1:
            return {
                "error": False,
                "node_id": all_matches[0]["node_id"],
                "name": all_matches[0]["name"],
                "type": all_matches[0]["type"],
                "parent_id": all_matches[0]["parent_id"],
                "warning": f"Există {len(all_matches)} noduri cu numele '{name}'. Am returnat primul. Specifică parent_folder_name pentru precizie. Găsite în: {[m['parent_name'] for m in all_matches]}"
            }

        return all_matches[0]
    
    async def browse_by_path(self, path: str = "/") -> Dict[str, Any]:
        """Navighează folosind path-ul"""
        # Pentru configurația minimală, încercăm să găsim nodul după path
        # Aceasta este o funcție simplificată
        
        if path == "/" or path == "":
            # Root
            return await self.list_root_children()
        
        parts = [p for p in path.split("/") if p]

        current_node = "-root-"
        
        for part in parts:
            children = await self.get_node_children(current_node, 100)

            match = None
            for item in children.get("items", []):
                if item["name"] == part and item["type"] == "folder":
                    match = item
                    break

            if not match:
                return {
                    "error": True,
                    "message": f"Folderul '{part}' nu există în path '{path}'"
                }

            current_node = match["id"]

        return await self.get_node_children(current_node)
    
    async def upload_file(
        self,
        name: str,
        content: str,
        parent_id: str
    ) -> Dict[str, Any]:
        """
        Creează un fișier text într-un folder specificat.
        Folosește multipart/form-data conform API-ului Alfresco.
        """
        url = urljoin(
            self.base_url,
            f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children"
        )
 
        # Alfresco acceptă upload prin multipart form
        # Trebuie un client fără Content-Type: application/json pentru acest request
        auth_string = base64.b64encode(
            f'{self.username}:{self.password}'.encode()
        ).decode()
 
        file_content = content.encode('utf-8')
 
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True
        ) as upload_client:
            response = await upload_client.post(
                url,
                headers={"Authorization": f"Basic {auth_string}"},
                files={
                    "filedata": (name, file_content, "text/plain"),
                    "name": (None, name),
                    "nodeType": (None, "cm:content"),
                },
            )
            response.raise_for_status()
            result = response.json()
 
        entry = result.get("entry", {})
        return {
            "created": True,
            "file_id": entry.get("id"),
            "file_name": entry.get("name"),
            "parent_id": parent_id,
            "size": entry.get("content", {}).get("sizeInBytes"),
            "message": f"Fișierul '{name}' a fost creat cu succes"
        }
    
    async def move_node(
        self,
        node_id: str,
        target_parent_id: str
    ) -> Dict[str, Any]:
        """
        Mută un nod (fișier sau folder) într-un alt folder.
        Folosește PUT /nodes/{nodeId} cu targetParentId.
        """
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
 
        if not re.search(uuid_pattern, node_id, re.IGNORECASE):
            return {"error": True, "message": f"node_id invalid: '{node_id}'"}
        if not re.search(uuid_pattern, target_parent_id, re.IGNORECASE):
            return {"error": True, "message": f"target_parent_id invalid: '{target_parent_id}'"}
 
        url = urljoin(
            self.base_url,
            f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}/move"
        )
 
        move_data = {"targetParentId": target_parent_id}
        response = await self.client.post(url, json=move_data)
        response.raise_for_status()
        result = response.json()
 
        entry = result.get("entry", {})
        return {
            "moved": True,
            "node_id": entry.get("id"),
            "node_name": entry.get("name"),
            "new_parent_id": target_parent_id,
            "message": f"Nodul '{entry.get('name')}' a fost mutat cu succes"
        }
    
    async def set_permissions(
        self,
        node_id: str,
        permissions: List[Dict[str, str]],
        inherit: bool = False
    ) -> Dict[str, Any]:
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        if not re.search(uuid_pattern, node_id, re.IGNORECASE):
            return {"error": True, "message": f"node_id invalid: '{node_id}'"}

        url = urljoin(
            self.base_url,
            f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}"
        )

        local_permissions = []
        for perm in permissions:
            # Acceptă "authorityId", "authority", sau orice alt câmp cu "authority"
            authority_id = (
                perm.get("authorityId") or
                perm.get("authority") or
                perm.get("authorityid") or
                ""
            )
            
            if not authority_id:
                return {
                    "error": True,
                    "message": f"Permisiunea nu are câmpul 'authorityId': {perm}"
                }

            # Acceptă "name", "role", sau "permission" pentru rolul efectiv
            role_value = (
                perm.get("name") or
                perm.get("role") or
                perm.get("permission") or
                "Consumer"
            )

            local_permissions.append({
                "authorityId": authority_id,
                "name": role_value,
                "accessStatus": "ALLOWED"
            })

        permissions_data = {
            "permissions": {
                "isInheritanceEnabled": inherit,
                "locallySet": local_permissions
            }
        }

        response = await self.client.put(url, json=permissions_data)
        response.raise_for_status()
        result = response.json()

        entry = result.get("entry", {})
        set_perms = entry.get("permissions", {}).get("locallySet", [])

        return {
            "success": True,
            "node_id": node_id,
            "node_name": entry.get("name"),
            "inheritance_enabled": inherit,
            "permissions_set": [
                {"authority": p.get("authorityId"), "role": p.get("name")}
                for p in set_perms
            ],
            "message": (
                f"Permisiuni setate pe '{entry.get('name')}': "
                f"moștenire={'activă' if inherit else 'dezactivată'}, "
                f"{len(local_permissions)} permisiuni explicite"
            )
        }
    
    async def list_groups(self, search: str = "") -> Dict[str, Any]:
        """Listează grupurile din Alfresco"""
        url = urljoin(
            self.base_url,
            "/alfresco/api/-default-/public/alfresco/versions/1/groups"
        )
        params = {"maxItems": 100, "skipCount": 0}
        if search:
            params["where"] = f'(displayName matches "{search}*")'
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        groups = []
        for entry in data.get("list", {}).get("entries", []):
            g = entry["entry"]
            groups.append({
                "id": g.get("id"),           # Acesta e authorityId real
                "displayName": g.get("displayName")
            })
        
        return {
            "groups": groups,
            "total": len(groups),
            "message": f"Am găsit {len(groups)} grupuri",
            "hint": "Folosește câmpul 'id' ca authorityId în set_permissions"
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
                    simplified_items.append({
                        "name": name,
                        "type": node_type,
                        "id": node_id
                    })
                elif "label" in item and "value" in item:
                    # E o informație cheie-valoare
                    simplified_items.append({
                        "label": item['label'], 
                        "value": item['value']
                    })

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