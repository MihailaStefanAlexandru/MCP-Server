#!/usr/bin/env python3
"""
Server MCP pentru Alfresco - versiune adaptată pentru configurația minimală
"""
import asyncio
import sys
import os
from Clase.MinimalAlfrescoServer import MinimalAlfrescoServer

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions

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

async def main():
    """Main pentru configurația minimală Alfresco"""
    
    # Activează virtual environment-ul dacă există
    setup_virtual_env()
    
    # Configurare de bază
    alfresco_url = os.getenv("ALFRESCO_URL", "http://localhost:8080")
    alfresco_user = os.getenv("ALFRESCO_USER", "admin")
    alfresco_password = os.getenv("ALFRESCO_PASSWORD", "admin")
    
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
        sys.exit(1)
    finally:
        await server.cleanup()

if __name__ == "__main__":
    asyncio.run(main())