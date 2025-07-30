#!/usr/bin/env python3
"""
Client LLM pentru MCP Alfresco - Comunicație prin STDIO
Se conectează la un server MCP prin stdin/stdout conform standardului MCP
"""
import os
import sys
import json
import signal
from Clase.MCPLLMClient import MCPStdioLLMClient

def signal_handler(signum, frame):
    """Handler pentru semnale de sistem"""
    print(f"\n🛑 Primit semnal {signum} - opresc clientul...")
    sys.exit(0)

def main():
    # Înregistrează handlere pentru semnale
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    config_file = sys.argv[1] if len(sys.argv) > 1 else "llm_config.json"
    
    if not os.path.exists(config_file):
        print(f"❌ Fișierul de configurație nu există: {config_file}")
        print("💡 Exemplu de configurație necesară:")
        example_config = {
            "llm": {
                "provider": "openai",
                "api_key": "your-api-key",
                "model": "gpt-3.5-turbo"
            },
            "mcp": {
                "server_command": ["python3", "mcp_alfresco_server.py"],
                "server_args": ["--config", "alfresco_config.json"],
                "server_env": {
                    "ALFRESCO_URL": "http://localhost:8080/alfresco",
                    "ALFRESCO_USER": "admin",
                    "ALFRESCO_PASS": "admin"
                }
            }
        }
        print(json.dumps(example_config, indent=2))
        sys.exit(1)
    
    client = MCPStdioLLMClient(config_file)
    
    try:
        # Pornește serverul MCP prin STDIO
        print("🚀 Pornesc serverul MCP prin STDIO...")
        mcp_connected = client.start_mcp_server()
        
        if mcp_connected:
            if client.mcp_tools:
                print(f"✅ Mod complet: Server MCP cu {len(client.mcp_tools)} tool-uri disponibile")
            else:
                print("⚠️  Mod parțial: Server MCP conectat dar fără tool-uri detectate")
        else:
            print("❌ Mod offline: Nu pot porni sau conecta serverul MCP")
            print("💡 Verifică configurația serverului MCP")
        
        # Sesiune interactivă prin STDIO
        client.interactive_session_stdio()
        
    except Exception as e:
        print(f"❌ Eroare critică: {e}")
    finally:
        # Cleanup garantat
        client.stop_mcp_server()

if __name__ == "__main__":
    main()
