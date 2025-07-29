#!/bin/bash

# Script pentru configurarea serverului MCP Alfresco cu multiple opțiuni LLM
# Suportă: OpenAI GPT-3.5, Groq (gratuit), Google Gemini (gratuit), Ollama local

set -e

echo "🤖 Configurez serverul MCP Alfresco cu LLM flexibil..."

# Detectează mediul
IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null || grep -qi wsl /proc/version 2>/dev/null; then
    IS_WSL=true
    echo "🐧 Detectat WSL"
    CONFIG_DIR="$HOME/.config/alfresco-mcp"
else
    OS=$(uname -s)
    case $OS in
        "Darwin"|"Linux")
            CONFIG_DIR="$HOME/.config/alfresco-mcp"
            ;;
        *)
            echo "❌ Sistem nesuportat: $OS"
            exit 1
            ;;
    esac
fi

mkdir -p "$CONFIG_DIR"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SERVER_PATH="$SCRIPT_DIR/alfresco_mcp_server.py"

# Verifică serverul MCP
if [ ! -f "$SERVER_PATH" ]; then
    echo "❌ Serverul MCP nu a fost găsit la: $SERVER_PATH"
    exit 1
fi

echo "✅ Serverul MCP găsit la: $SERVER_PATH"

# Instalează dependențele
echo "🔍 Verificez dependențele Python..."
pip3 install -q mcp httpx openai google-generativeai requests groq

echo "✅ Dependențele Python sunt OK"

# Configurează Alfresco
echo ""
echo "📝 Configurare Alfresco:"
read -p "URL Alfresco (default: http://localhost:8080): " ALFRESCO_URL
ALFRESCO_URL=${ALFRESCO_URL:-http://localhost:8080}

read -p "Username Alfresco (default: admin): " ALFRESCO_USER
ALFRESCO_USER=${ALFRESCO_USER:-admin}

read -s -p "Password Alfresco (default: admin): " ALFRESCO_PASSWORD
ALFRESCO_PASSWORD=${ALFRESCO_PASSWORD:-admin}
echo ""

# Selecția providerului LLM
echo ""
echo "🤖 Selectează providerul LLM:"
echo "1. 🟢 Groq (GRATUIT, foarte rapid, Llama-3.1-70B)"
echo "2. 🟡 Google Gemini (GRATUIT cu limite, foarte bun)"
echo "3. 🔵 OpenAI GPT-3.5 (5$ gratuit, apoi paid, excelent)"
echo "4. 🟠 Ollama local (complet gratuit, consum RAM)"
echo "5. 🔴 HuggingFace (gratuit cu limite, variabil)"
echo ""

read -p "🎯 Alege opțiunea (1-5): " LLM_CHOICE

# Configurarea pe baza selecției
case $LLM_CHOICE in
    1)
        LLM_PROVIDER="groq"
        echo "🟢 Ai ales Groq - cel mai rapid LLM gratuit!"
        echo "📝 Obține API key de la: https://console.groq.com/keys"
        read -p "🔑 Introdu Groq API key: " API_KEY
        LLM_MODEL="llama3-70b-8192"
        ;;
    2)
        LLM_PROVIDER="openai"
        echo "🔵 Ai ales OpenAI GPT-3.5 - foarte stabil și performant!"
        echo "📝 Obține API key de la: https://platform.openai.com/api-keys"
        read -p "🔑 Introdu OpenAI API key: " API_KEY
        LLM_MODEL="gpt-3.5-turbo"
        ;;
    *)
        echo "⚠️  Selecție invalidă, folosesc Groq implicit"
        LLM_PROVIDER="openai"
        read -p "🔑 Introdu OpenAI API key: " API_KEY
        LLM_MODEL="gpt-3.5-turbo"
        ;;
esac

if [ -z "$API_KEY" ] && [ "$LLM_PROVIDER" != "ollama" ]; then
    echo "❌ API key este obligatoriu pentru $LLM_PROVIDER"
    exit 1
fi

# Creează scriptul MCP (același ca înainte)
MCP_SCRIPT="$SCRIPT_DIR/start_mcp_server.sh"
cat > "$MCP_SCRIPT" << EOF
#!/bin/bash
export ALFRESCO_URL="$ALFRESCO_URL"
export ALFRESCO_USER="$ALFRESCO_USER"  
export ALFRESCO_PASSWORD="$ALFRESCO_PASSWORD"

cd "$SCRIPT_DIR"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "🚀 Pornesc serverul MCP Alfresco..."
python3 "./alfresco_mcp_server.py"
EOF

chmod +x "$MCP_SCRIPT"

# Script principal de rulare
MAIN_SCRIPT="$SCRIPT_DIR/run_llm_mcp.sh"
cat > "$MAIN_SCRIPT" << EOF
#!/bin/bash
echo "🤖 Pornesc clientul LLM Universal cu MCP pentru Alfresco..."
echo "⚡ Provider: $LLM_PROVIDER"
echo "🧠 Model: $LLM_MODEL"
echo "📁 Alfresco: $ALFRESCO_URL"
echo ""

cd "$SCRIPT_DIR"
python3 "/mnt/d/Programare/MCP-server/universal_llm_client.py" "/home/.config/alfresco-mcp/llm_config.json"
EOF

chmod +x "$MAIN_SCRIPT"

echo ""
echo "✅ Configurația LLM Universal + MCP completată!"
echo ""
echo "📋 Configurația creată pentru $LLM_PROVIDER:"
echo "   🤖 Model: $LLM_MODEL"
echo "   🔑 API Key configurat: ${API_KEY:0:10}..."
echo "   📄 Client universal: $LLM_CLIENT_PATH"
echo "   ⚙️  Config: $APP_CONFIG"
echo "   🚀 Script principal: $MAIN_SCRIPT"
echo "   🔗 Alfresco: $ALFRESCO_URL"
echo ""

# Informații specifice provider-ului
case $LLM_PROVIDER in
    "groq")
        echo "🟢 Groq - Avantaje:"
        echo "   ✅ Complet GRATUIT"
        echo "   ✅ Foarte rapid (200+ tokens/sec)"
        echo "   ✅ Llama 3.1 70B foarte capabil"
        echo "   ✅ Rate limits generoase"
        ;;
    "openai")
        echo "🔵 OpenAI GPT-3.5 - Avantaje:"
        echo "   💰 5$ credit gratuit apoi ~0.002$/1K tokens"
        echo "   ✅ Foarte stabil și consistent"
        echo "   ✅ Rapid și de încredere"
        echo "   ✅ Excelent pentru taskuri complexe"
        ;;
esac

echo ""
echo "🚀 Pentru a rula aplicația:"
echo "   $MAIN_SCRIPT"
echo ""
echo "🧪 Comenzi test pentru Alfresco:"
echo "   📁 'Listează documentele din root'"
echo "   ➕ 'Creează un folder numit Proiect'"
echo "   ℹ️  'Informații despre folderul root'"
echo "   🧭 'Navighează la calea /Company Home'"
echo ""

read -p "🚀 Vrei să pornesc aplicația acum? (y/N): " START_APP
if [[ "$START_APP" =~ ^[Yy]$ ]]; then
    echo "🔥 Pornesc clientul $LLM_PROVIDER + MCP..."
    exec "$MAIN_SCRIPT"
fi

echo "🎉 Setup complet! Rulează $MAIN_SCRIPT când ești gata."
