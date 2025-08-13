#!/usr/bin/env python3
"""
Server MCP pentru Alfresco - versiune adaptată pentru configurația minimală
"""
import asyncio
import sys
import os
from Clase.HttpServer import HTTPAlfrescoMCPServer

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

def main():
    """Main pentru serverul HTTP Alfresco MCP"""
    
    # Activează virtual environment-ul dacă există
    setup_virtual_env()
    
    # Configurare din environment variables
    alfresco_url = os.getenv("ALFRESCO_URL", "http://localhost:8080")
    alfresco_user = os.getenv("ALFRESCO_USER", "admin")
    alfresco_password = os.getenv("ALFRESCO_PASSWORD", "admin")
    server_port = int(os.getenv("MCP_SERVER_PORT", "8002"))
    server_host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    
    # Creează și pornește serverul HTTP
    server = HTTPAlfrescoMCPServer(
        base_url=alfresco_url,
        username=alfresco_user,
        password=alfresco_password,
        port=server_port
    )
    
    server.run(host=server_host)

if __name__ == "__main__":
    main()