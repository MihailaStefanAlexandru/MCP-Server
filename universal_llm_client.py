#!/usr/bin/env python3
"""
Client LLM pentru MCP Alfresco - Comunicație prin HTTP
Se conectează la un server MCP prin HTTP conform standardului MCP
"""
import os
import sys
import asyncio
from Clase.MCPHTTPClient import MCPHTTPClient

async def main_async():
    """Funcția principală async pentru clientul HTTP MCP"""
    if len(sys.argv) != 2:
        print("Utilizare: universal_llm_client.py config.json")
        sys.exit(1)

    config_path = sys.argv[1]

    if not os.path.exists(config_path):
        print(f"❌ Fișierul de configurație nu există: {config_path}")
        sys.exit(1)

    # Creează clientul HTTP
    client = MCPHTTPClient(config_path)

    try:
        # Conectează-te la serverul MCP
        print("🔄 Încerc să mă conectez la serverul MCP HTTP...")
        
        # Pornește/conectează la serverul MCP HTTP
        if await client.start_mcp_server_http():
            print("🎉 Conexiune MCP HTTP stabilită cu succes!")
            
            # Testează conexiunea
            if await client.test_mcp_connection_http():
                print("✅ Test conexiune reușit!")
                
                # SOLUȚIA: Apelează direct metoda async în loc de wrapper-ul sincron
                await client.interactive_session_http_async()
            else:
                print("❌ Test conexiune eșuat")
                sys.exit(1)
        else:
            print("❌ Nu m-am putut conecta la serverul MCP HTTP")
            print("💡 Verifică că serverul rulează și URL-ul este corect")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n🛑 Oprire forțată de utilizator")
    except Exception as e:
        print(f"❌ Eroare în clientul HTTP MCP: {e}")
    finally:
        await client.cleanup_http()

def main():
    """Wrapper sincron pentru main async"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()