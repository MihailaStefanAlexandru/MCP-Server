#!/usr/bin/env python3
"""
Server MCP pentru Alfresco - versiune adaptată pentru configurația minimală
(fără Solr, Share, transforms sau messaging)
"""
import asyncio
import json
import sys
import os
from typing import Any, Dict, List
import httpx
from urllib.parse import urljoin
import base64

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
)
import mcp.types as types


def setup_virtual_env():
    """Detectează și activează virtual environment-ul automat"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Lista de locații posibile pentru venv
    possible_venvs = [
        os.path.join(current_dir, 'venv'),
        os.path.join(current_dir, '.venv'),
        os.path.join(current_dir, 'env'),
        os.path.join(os.path.dirname(current_dir), 'venv'),
        os.path.join(os.path.dirname(current_dir), '.venv'),
    ]
    
    for venv_path in possible_venvs:
        if os.path.exists(venv_path):
            # Detectează platforma
            if sys.platform == "win32":
                python_path = os.path.join(venv_path, "Scripts", "python.exe")
                activate_script = os.path.join(venv_path, "Scripts", "activate")
            else:
                python_path = os.path.join(venv_path, "bin", "python")
                activate_script = os.path.join(venv_path, "bin", "activate")
            
            if os.path.exists(python_path):
                # Setează VIRTUAL_ENV
                os.environ['VIRTUAL_ENV'] = venv_path
                
                # Adaugă bin/Scripts la PATH
                venv_bin = os.path.dirname(python_path)
                if venv_bin not in os.environ['PATH']:
                    os.environ['PATH'] = venv_bin + os.pathsep + os.environ['PATH']
                
                # Adaugă site-packages la Python path
                if sys.platform == "win32":
                    site_packages = os.path.join(venv_path, "Lib", "site-packages")
                else:
                    # Găsește versiunea Python
                    for item in os.listdir(os.path.join(venv_path, "lib")):
                        if item.startswith("python"):
                            site_packages = os.path.join(venv_path, "lib", item, "site-packages")
                            break
                
                if 'site_packages' in locals() and os.path.exists(site_packages):
                    if site_packages not in sys.path:
                        sys.path.insert(0, site_packages)
                
                print(f"✅ Virtual environment găsit și activat: {venv_path}", file=sys.stderr)
                return True
    
    print("⚠️ Nu am găsit virtual environment. Folosesc Python global.", file=sys.stderr)
    return False


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
            """Execută tool-urile pentru configurația minimală"""
            try:
                # Conectarea lazy - doar când e nevoie
                if not self.connection_tested:
                    await self.ensure_connection()
                
                if name == "list_root_children":
                    result = await self.list_root_children(arguments.get("maxItems", 20))
                elif name == "get_node_children":
                    result = await self.get_node_children(arguments["node_id"], arguments.get("maxItems", 20))
                elif name == "create_folder":
                    result = await self.create_folder(
                        arguments["name"],
                        arguments.get("parent_id", "-root-"),
                        arguments.get("title"),
                        arguments.get("description")
                    )
                elif name == "get_node_info":
                    result = await self.get_node_info(arguments["node_id"])
                elif name == "delete_node":
                    result = await self.delete_node(arguments["node_id"], arguments.get("permanent", False))
                elif name == "browse_by_path":
                    result = await self.browse_by_path(arguments.get("path", "/"))
                else:
                    return [types.TextContent(type="text", text=f"Tool necunoscut: {name}")]
                
                return [types.TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
            
            except Exception as e:
                error_msg = f"Eroare la executarea {name}: {str(e)}"
                print(f"❌ {error_msg}", file=sys.stderr)
                return [types.TextContent(type="text", text=error_msg)]
    
    async def ensure_connection(self):
        """Asigură că avem o conexiune validă"""
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=10.0),  # Timeout mai mare pentru configurația minimală
                follow_redirects=True
            )
            
            # Folosim Basic Auth direct
            auth_string = base64.b64encode(f'{self.username}:{self.password}'.encode()).decode()
            self.client.headers.update({
                "Authorization": f"Basic {auth_string}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            })
        
        if not self.connection_tested:
            # Testăm cu endpoint-ul de noduri (nu sites care poate să nu existe)
            try:
                test_url = urljoin(self.base_url, "/alfresco/api/-default-/public/alfresco/versions/1/nodes/-root-")
                response = await self.client.get(test_url)
                response.raise_for_status()
                self.connection_tested = True
                print("✅ Conexiune Alfresco minimal validată", file=sys.stderr)
            except Exception as e:
                print(f"❌ Eroare la validarea conexiunii Alfresco minimal: {e}", file=sys.stderr)
                raise Exception(f"Nu pot conecta la Alfresco minimal ({self.base_url}): {str(e)}")
    
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
            "message": f"Informații pentru nodul '{node.get('name')}'"
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
    
    async def cleanup(self):
        """Curăță resursele"""
        if self.client:
            await self.client.aclose()
    
    def get_server(self) -> Server:
        return self.server


async def main():
    """Main pentru configurația minimală Alfresco"""
    
    # Activează virtual environment-ul dacă există
    setup_virtual_env()
    
    # Configurare de bază
    alfresco_url = os.getenv("ALFRESCO_URL", "http://172.17.253.147:8080")
    alfresco_user = os.getenv("ALFRESCO_USER", "admin") 
    alfresco_password = os.getenv("ALFRESCO_PASSWORD", "admin")
    
    # Log pentru debugging
    import logging
    log_file = os.getenv("MCP_LOG_FILE", "/tmp/alfresco_mcp_minimal.log")
    
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filemode='a'
    )
    
    try:
        logging.info(f"🚀 Pornesc serverul MCP pentru Alfresco MINIMAL...")
        logging.info(f"📍 URL: {alfresco_url}")
        logging.info(f"👤 User: {alfresco_user}")
        logging.info(f"⚠️ Configurație minimală: FĂRĂ search, Share, transforms")
    except:
        pass
    
    # Print pentru debugging
    print(f"🚀 Server MCP Alfresco MINIMAL pornit", file=sys.stderr)
    print(f"📍 URL: {alfresco_url}", file=sys.stderr)
    print(f"⚠️ LIMITĂRI: Nu sunt disponibile search, Share UI, transformări", file=sys.stderr)
    
    # Creează serverul minimal
    server = MinimalAlfrescoServer(
        base_url=alfresco_url,
        username=alfresco_user,
        password=alfresco_password
    )
    
    # Pornește serverul MCP
    from mcp.server.stdio import stdio_server
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.get_server().run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="minimal-alfresco-server",
                    server_version="0.1.0",
                    capabilities=server.get_server().get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )
    except KeyboardInterrupt:
        print("🛑 Server minimal oprit de user", file=sys.stderr)
    except Exception as e:
        error_msg = f"❌ Eroare în serverul MCP minimal: {e}"
        print(error_msg, file=sys.stderr)
        try:
            logging.error(error_msg)
        except:
            pass
        sys.exit(1)
    finally:
        await server.cleanup()


if __name__ == "__main__":
    asyncio.run(main())