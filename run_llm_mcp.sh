#!/bin/bash
echo "🤖 Pornesc clientul LLM Universal cu MCP pentru Alfresco..."
echo "⚡ Provider: openai"
echo "🧠 Model: gpt-3.5-turbo"
echo "📁 Alfresco: http://localhost:8080"
echo ""

cd "/mnt/d/Programare/MCP-Server"
python3 "/mnt/d/Programare/MCP-Server/universal_llm_client.py" "llm_config.json"
