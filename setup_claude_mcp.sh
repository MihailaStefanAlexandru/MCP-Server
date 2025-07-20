#!/bin/bash

# Script pentru configurarea serverului MCP Alfresco în Claude Desktop (Windows + WSL)
# Versiune adaptată pentru configurația minimală Alfresco

set -e

echo "🔧 Configurez serverul MCP Alfresco pentru Claude Desktop (configurație minimală)..."

# Detectează dacă rulăm în WSL
IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null || grep -qi wsl /proc/version 2>/dev/null; then
    IS_WSL=true
    echo "🐧 Detectat WSL - configurez pentru Windows + WSL"
    # Pentru WSL, configurația Claude Desktop e pe Windows
    WINDOWS_USER=$(powershell.exe -c "echo \$env:USERNAME" 2>/dev/null | tr -d '\r\n' || cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')
    CONFIG_DIR="/mnt/c/Users/$WINDOWS_USER/AppData/Roaming/Claude"
    echo "📁 Director configurare Windows: $CONFIG_DIR"
    echo "👤 User Windows: $WINDOWS_USER"
else
    # Detectează sistemul de operare normal
    OS=$(uname -s)
    case $OS in
        "Darwin")
            CONFIG_DIR="$HOME/Library/Application Support/Claude"
            ;;
        "Linux")
            CONFIG_DIR="$HOME/.config/Claude"
            ;;
        *)
            echo "❌ Sistem de operare nesuportat: $OS"
            exit 1
            ;;
    esac
fi

# Verifică dacă directorul de configurare există și poate fi accesat
if [ ! -d "$(dirname "$CONFIG_DIR")" ]; then
    echo "❌ Nu pot accesa directorul părinte: $(dirname "$CONFIG_DIR")"
    echo "💡 Verifică că Windows drive-ul C: este montat în WSL"
    exit 1
fi

# Creează directorul de configurare dacă nu există
mkdir -p "$CONFIG_DIR"

# Obține calea absolută a scriptului
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SERVER_PATH="$SCRIPT_DIR/alfresco_mcp_server.py"

# Verifică dacă serverul există
if [ ! -f "$SERVER_PATH" ]; then
    echo "❌ Serverul MCP nu a fost găsit la: $SERVER_PATH"
    echo "💡 Verifică că fișierul alfresco_mcp_server.py este în același director cu acest script"
    exit 1
fi

echo "✅ Serverul găsit la: $SERVER_PATH"

# Verifică dacă docker-compose.yaml există
DOCKER_COMPOSE_FILE="$SCRIPT_DIR/acs-community-deployment/docker-compose.yaml"
if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
    echo "⚠️  docker-compose.yaml nu a fost găsit"
    echo "💡 Asigură-te că ai fișierul docker-compose.yaml în același director"
fi

# Verifică dependențele Python
echo "🔍 Verificez dependențele Python..."
if ! python3 -c "import mcp, httpx" 2>/dev/null; then
    echo "⚠️  Dependențele Python nu sunt instalate. Instalez acum..."
    pip3 install mcp httpx
    if [ $? -ne 0 ]; then
        echo "❌ Nu pot instala dependențele. Rulează manual: pip3 install mcp httpx"
        exit 1
    fi
fi
echo "✅ Dependențele Python sunt OK"

# Verifică dacă Alfresco minimal rulează
echo "🔍 Verificez starea Alfresco minimal..."
if command -v docker >/dev/null 2>&1 && command -v docker-compose >/dev/null 2>&1; then
    if docker ps | grep -q "alfresco.*Up"; then
        echo "✅ Alfresco minimal rulează deja"
    else
        echo "⚠️  Alfresco nu pare să ruleze"
        read -p "🚀 Vrei să pornesc Alfresco minimal acum? (y/N): " START_ALFRESCO
        if [[ "$START_ALFRESCO" =~ ^[Yy]$ ]]; then
            if [ -f "$DOCKER_COMPOSE_FILE" ]; then
                echo "🐳 Pornesc Alfresco minimal..."
                cd "$SCRIPT_DIR"
                docker-compose -f docker-compose.yaml up -d
                echo "⏳ Aștept ca serviciile să pornească (60 secunde)..."
                sleep 60
            else
                echo "❌ docker-compose.yaml nu a fost găsit în $SCRIPT_DIR"
            fi
        fi
    fi
else
    echo "⚠️  Docker sau docker-compose nu sunt disponibile"
fi

# Obține configurarea Alfresco (adaptat pentru configurația minimală)
echo ""
echo "📝 Configurare Alfresco (configurație minimală):"
read -p "URL Alfresco (default: http://172.17.253.147:8080): " ALFRESCO_URL
ALFRESCO_URL=${ALFRESCO_URL:-http://172.17.253.147:8080}

read -p "Username Alfresco (default: admin): " ALFRESCO_USER
ALFRESCO_USER=${ALFRESCO_USER:-admin}

read -s -p "Password Alfresco (default: admin): " ALFRESCO_PASSWORD
ALFRESCO_PASSWORD=${ALFRESCO_PASSWORD:-admin}
echo ""

# Testează conexiunea la Alfresco (endpoint-uri adaptate pentru configurația minimală)
echo "🔗 Testez conexiunea la Alfresco minimal..."
if command -v curl >/dev/null 2>&1; then
    # Testează endpoint-ul principal
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "$ALFRESCO_URL/alfresco/api/-default-/public/alfresco/versions/1/nodes/-root-/children" -u "$ALFRESCO_USER:$ALFRESCO_PASSWORD" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "401" ]; then
        if [ "$HTTP_CODE" = "401" ]; then
            echo "⚠️  Conexiunea OK dar credențialele par incorecte (HTTP 401)"
        else
            echo "✅ Conexiunea la Alfresco minimal este OK"
        fi
    else
        echo "⚠️  Nu pot conecta la Alfresco (HTTP $HTTP_CODE). Continuă oricum..."
        echo "💡 Verifică că Alfresco minimal rulează la $ALFRESCO_URL"
        echo "💡 Pentru configurația minimală, Alfresco poate dura până la 2-3 minute să pornească complet"
        
        # Oferă opțiuni de debugging
        read -p "🐛 Vrei să verific log-urile Docker? (y/N): " CHECK_LOGS
        if [[ "$CHECK_LOGS" =~ ^[Yy]$ ]] && command -v docker >/dev/null 2>&1; then
            echo "📋 Log-uri recente din containerul Alfresco:"
            docker logs --tail 20 $(docker ps -q --filter "ancestor=alfresco/alfresco-content-repository-community:6.2.1-A8") 2>/dev/null || echo "Nu pot accesa log-urile"
        fi
    fi
else
    echo "⚠️  curl nu este disponibil - nu pot testa conexiunea"
fi

# Creează fișierul de configurare
CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"

echo "📄 Creez configurația în: $CONFIG_FILE"

if [ "$IS_WSL" = true ]; then
    # Pentru WSL, folosim calea Linux în comanda WSL
    cat > "$CONFIG_FILE" << EOF
{
  "mcpServers": {
    "alfresco-server": {
      "command": "wsl.exe",
      "args": [
        "-e",
        "bash",
        "-c",
        "cd '$SCRIPT_DIR' && ALFRESCO_URL='$ALFRESCO_URL' ALFRESCO_USER='$ALFRESCO_USER' ALFRESCO_PASSWORD='$ALFRESCO_PASSWORD' source venv/bin/activate && python3 './alfresco_mcp_server.py'"
      ]
    }
  }
}
EOF
else
    # Pentru sisteme native Linux/macOS
    cat > "$CONFIG_FILE" << EOF
{
  "mcpServers": {
    "alfresco-server": {
      "command": "python3",
      "args": [
        "$SERVER_PATH"
      ],
      "env": {
        "ALFRESCO_URL": "$ALFRESCO_URL",
        "ALFRESCO_USER": "$ALFRESCO_USER",
        "ALFRESCO_PASSWORD": "$ALFRESCO_PASSWORD"
      }
    }
  }
}
EOF
fi

# Verifică că fișierul a fost creat
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Nu am putut crea fișierul de configurare"
    exit 1
fi

echo "✅ Configurația a fost salvată cu succes!"
echo ""
echo "📋 Configurația creată pentru Alfresco minimal:"
echo "   Fișier: $CONFIG_FILE"
echo "   Server: alfresco-server"
echo "   URL: $ALFRESCO_URL"
echo "   User: $ALFRESCO_USER"
echo ""
echo "⚠️  IMPORTANT pentru configurația minimală:"
echo "   🔍 INDEXAREA este DEZACTIVATĂ - căutarea nu va funcționa"
echo "   🔄 TRANSFORMĂRILE sunt DEZACTIVATE - nu se pot converti documente"
echo "   📱 SHARE UI nu este disponibil - doar API-ul REST"
echo "   📨 MESSAGING este DEZACTIVAT - nu sunt notificări"
echo ""
echo "🔄 Pași următori:"
echo "1. 🔄 Restartează Claude Desktop complet (închide din System Tray)"
echo "2. 🚀 Deschide Claude Desktop"
echo "3. 💬 În chat, serverul 'alfresco-server' ar trebui să apară ca disponibil"
echo "4. 🧪 Testează cu comenzi SIMPLE (configurația minimală):"
echo "   - 'Listează fișierele din root-ul Alfresco'"
echo "   - 'Creează un folder nou în root'"
echo "   - 'Încarcă un fișier simplu'"
echo "   ❌ NU încerca: căutare, conversii, interfața Share"
echo ""
echo "🐛 Pentru debugging:"
echo "   - Log server: /tmp/alfresco_mcp.log"
echo "   - Verifică Alfresco: $ALFRESCO_URL/alfresco (doar API, nu Share)"
echo "   - Testează manual serverul: python3 '$SERVER_PATH'"
echo "   - Verifică containers: docker ps"
echo "   - Log Alfresco: docker logs [alfresco-container-id]"
echo ""
if [ "$IS_WSL" = true ]; then
echo "💡 Sfaturi WSL pentru configurația minimală:"
echo "   - Asigură-te că ai mărit memoria WSL la minimum 4GB"
echo "   - Verifică că Python3 și Docker sunt instalate în WSL"
echo "   - Alfresco minimal poate dura 2-3 minute să pornească complet"
echo "   - În caz de probleme, rulează serverul direct în Windows"
fi

# Opțional: testează serverul manual
echo ""
read -p "🧪 Vrei să testez serverul acum? (y/N): " TEST_SERVER
if [[ "$TEST_SERVER" =~ ^[Yy]$ ]]; then
    echo "🚀 Pornesc serverul pentru test..."
    export ALFRESCO_URL="$ALFRESCO_URL"
    export ALFRESCO_USER="$ALFRESCO_USER"
    export ALFRESCO_PASSWORD="$ALFRESCO_PASSWORD"
    
    (
        if [ -d "venv" ]; then
            source venv/bin/activate
        fi
        timeout 10s python3 "$SERVER_PATH"
    ) || {
        echo "⚠️  Testul serverului a eșuat sau a fost oprit după 10 secunde"
        echo "💡 Verifică log-urile pentru mai multe detalii"
    }
fi

echo ""
echo "🎯 Configurația minimală este gata!"
echo "💾 Consumul estimat de RAM: ~3-4GB (în loc de 8-9GB)"
echo "⚡ Funcționalități disponibile: CRUD basic pe fișiere și foldere"
echo "❌ Funcționalități indisponibile: căutare, conversii, Share UI, messaging"