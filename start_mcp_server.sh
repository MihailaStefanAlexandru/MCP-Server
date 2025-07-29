#!/bin/bash
export ALFRESCO_URL="http://localhost:8080"
export ALFRESCO_USER="admin"  
export ALFRESCO_PASSWORD="admin"

cd "/mnt/d/Programare/MCP-Server"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "🚀 Pornesc serverul MCP Alfresco..."
python3 "./alfresco_mcp_server.py"
