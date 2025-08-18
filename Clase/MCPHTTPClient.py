#!/usr/bin/env python3
"""
Client MCP pentru comunicație HTTP - VERSIUNE CORECTATĂ
"""
import os
import sys
import json
import time
import uuid
import threading
import queue
from typing import Optional, Dict, Any, List
import httpx
import asyncio
import logging

# Configurare logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MCPHTTPClient:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Configurare LLM
        self.provider = self.config['llm']['provider']
        self.api_key = self.config['llm']['api_key']
        self.model = self.config['llm']['model']

        # Configurare server MCP HTTP
        self.mcp_server_url = self.config.get('mcp', {}).get('server_url', 'http://localhost:8002')
        self.mcp_server_config = self.config.get('mcp', {}).get('server_config', {})

        # Stare client
        self.session_context = []
        self.running = True
        self.mcp_tools = {}
        self.mcp_resources = {}
        self.mcp_prompts = {}
        self.mcp_connected = False
        self.session_id = str(uuid.uuid4())

        # Client HTTP pentru comunicația cu serverul MCP
        self.http_client = None  # Va fi inițializat în metoda async
        
        # Session timing
        self.last_activity = time.time()
        self.session_timeout = 300
        
        print(f"🔧 Inițializez clientul {self.provider.upper()} cu MCP HTTP")
        self._init_llm_client()

    def _init_llm_client(self):
        """Inițializează clientul LLM"""
        try:
            if self.provider == "openai":
                import openai
                self.openai_client = openai.OpenAI(
                    api_key=self.api_key,
                    timeout=30,
                    max_retries=2
                )
                # Test conexiune
                self.openai_client.models.list()
                print("✅ OpenAI client inițializat")
                    
        except Exception as e:
            print(f"❌ Eroare inițializare {self.provider}: {e}")
            print("💡 Verifică API key-ul și conexiunea la internet")
            sys.exit(1)

    async def _init_http_client(self):
        """Inițializează clientul HTTP async"""
        if not self.http_client:
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True
            )

    async def start_mcp_server_http(self):
        """Pornește serverul MCP HTTP și stabilește conexiunea"""
        try:
            await self._init_http_client()
            
            # Verifică dacă serverul rulează deja
            if await self.check_server_health():
                print("✅ Serverul MCP HTTP rulează deja")
                return await self.initialize_mcp_http_protocol()
            
            # Pornește serverul dacă nu rulează
            print(f"🚀 Pornesc serverul MCP HTTP...")
            
            # Logică pentru a porni serverul ca proces separat
            # Pentru moment, presupunem că serverul este pornit manual
            
            # Așteaptă ca serverul să pornească
            max_retries = 30
            for i in range(max_retries):
                if await self.check_server_health():
                    print(f"✅ Server MCP HTTP pornit după {i+1} încercări")
                    return await self.initialize_mcp_http_protocol()
                await asyncio.sleep(1)
            
            print("❌ Serverul MCP HTTP nu a pornit în timpul alocat")
            return False
            
        except Exception as e:
            print(f"❌ Eroare pornire server MCP HTTP: {e}")
            return False

    async def check_server_health(self) -> bool:
        """Verifică dacă serverul MCP HTTP este disponibil"""
        try:
            if not self.http_client:
                await self._init_http_client()
            response = await self.http_client.get(f"{self.mcp_server_url}/health")
            return response.status_code == 200
        except:
            return False
        
    async def initialize_mcp_http_protocol(self):
        """Inițializează protocolul MCP prin HTTP"""
        try:
            print("🤝 Inițializez protocolul MCP prin HTTP...")
            
            if not self.http_client:
                await self._init_http_client()
            
            # Trimite cererea de inițializare
            init_data = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {}
                    },
                    "clientInfo": {
                        "name": "llm-mcp-http-client",
                        "version": "1.0.0"
                    }
                }
            }
            
            response = await self.http_client.post(
                f"{self.mcp_server_url}/mcp",
                json=init_data
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('result'):
                print("✅ Protocol MCP HTTP inițializat cu succes")
                
                # Trimite notificarea de inițializare completă
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                }
                
                await self.http_client.post(
                    f"{self.mcp_server_url}/mcp/notify",
                    json=notification
                )
                
                self.mcp_connected = True
                
                # Descoperă capabilitățile
                return await self._discover_mcp_capabilities_http()
            else:
                print("❌ Inițializare MCP HTTP eșuată")
                return False
                
        except Exception as e:
            print(f"❌ Eroare inițializare protocol MCP HTTP: {e}")
            return False
        
    async def _discover_mcp_capabilities_http(self):
        """Descoperă tool-urile prin HTTP"""
        success = True
        
        # Obține tool-urile
        try:
            print("🔧 Obțin tool-urile prin HTTP...")
            tools_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/list"
            }
            
            response = await self.http_client.post(
                f"{self.mcp_server_url}/mcp",
                json=tools_request
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('result') and 'tools' in result['result']:
                for tool in result['result']['tools']:
                    self.mcp_tools[tool['name']] = tool
                print(f"✅ Găsite {len(self.mcp_tools)} tool-uri HTTP: {list(self.mcp_tools.keys())}")
            else:
                print("⚠️ Nu s-au găsit tool-uri HTTP")
                success = False
                
        except Exception as e:
            print(f"❌ Eroare obținere tool-uri HTTP: {e}")
            success = False
        
        return success
    
    async def call_mcp_tool_http(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Apelează un tool MCP prin HTTP"""
        if tool_name not in self.mcp_tools:
            return {"error": f"Tool-ul '{tool_name}' nu este disponibil"}
        
        if not self.mcp_connected:
            return {"error": "Nu sunt conectat la serverul MCP HTTP"}
        
        try:
            print(f"🔧 Apelez tool MCP HTTP: {tool_name}")
            
            if not self.http_client:
                await self._init_http_client()
            
            # Trimite cererea de apelare tool
            call_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            response = await self.http_client.post(
                f"{self.mcp_server_url}/mcp",
                json=call_request
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('result'):
                print(f"✅ Tool HTTP {tool_name} executat cu succes")
                return result['result']
            elif result.get('error'):
                return {"error": f"Eroare server: {result['error']}"}
            else:
                return {"error": f"Răspuns neașteptat de la server"}
                
        except Exception as e:
            print(f"❌ Eroare apelare tool MCP HTTP: {e}")
            return {"error": str(e)}
        
    async def analyze_intent_and_call_tools_async(self, user_input: str) -> str:
        """Analizează intenția și apelează tool-urile - versiune async"""
        if not self.mcp_connected or not self.mcp_tools:
            return "ℹ️ Nu sunt conectat la serverul MCP HTTP sau nu sunt tool-uri disponibile."
        
        # Creează un prompt pentru a determina ce tool-uri să apeleze
        tools_description = ""
        for tool_name, tool_info in self.mcp_tools.items():
            desc = tool_info.get('description', 'Fără descriere')
            schema = tool_info.get('inputSchema', {})
            props = schema.get('properties', {})
            params = list(props.keys()) if props else []
            tools_description += f"- {tool_name}: {desc}\n"
            if params:
                tools_description += f"  Parametri: {', '.join(params)}\n"
        
        analysis_prompt = f"""Analizează următoarea cerere și determină ce tool MCP să apelez și cu ce parametri.

Tool-uri MCP disponibile:
{tools_description}

Cererea utilizatorului: {user_input}

Răspunde în format JSON strict:
{{
    "action": "call_tool",
    "tool_name": "numele_tool_ului",
    "arguments": {{"param1": "valoare1"}},
    "explanation": "explicația acțiunii"
}}

Sau dacă nu este necesar un tool:
{{
    "action": "no_tool",
    "explanation": "nu este necesar un tool MCP"
}}

IMPORTANT: Răspunde DOAR cu JSON-ul, fără text suplimentar."""

        # SOLUȚIA: Fă apelul LLM în mod sincron, nu cu await
        analysis_response = self.query_llm_with_retry(analysis_prompt, max_tokens=300)
        
        try:
            # Parsează JSON-ul
            import re
            json_match = re.search(r'\{.*\}', analysis_response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                
                if analysis.get('action') == 'call_tool':
                    tool_name = analysis.get('tool_name')
                    arguments = analysis.get('arguments', {})
                    explanation = analysis.get('explanation', '')
                    
                    if tool_name in self.mcp_tools:
                        print(f"🎯 Execut: {explanation}")
                        # Apelează tool-ul MCP prin HTTP
                        tool_result = await self.call_mcp_tool_http(tool_name, arguments)
                        
                        # Procesează rezultatul
                        if isinstance(tool_result, dict):
                            if tool_result.get('error'):
                                return f"❌ Eroare la executarea {tool_name}: {tool_result['error']}"
                            
                            if 'content' in tool_result:
                                content_items = tool_result['content']
                                result_text = ""
                                for item in content_items:
                                    if isinstance(item, dict) and item.get('type') == 'text':
                                        result_text += item.get('text', '')
                                    elif isinstance(item, str):
                                        result_text += item
                                return f"🔧 Rezultat {tool_name}:\n{result_text}"
                            else:
                                result_str = json.dumps(tool_result, indent=2, ensure_ascii=False)
                                return f"🔧 Rezultat {tool_name}:\n{result_str}"
                        
                        return f"🔧 Rezultat {tool_name}:\n{str(tool_result)}"
                    else:
                        return f"❌ Tool-ul '{tool_name}' nu este disponibil"
                else:
                    return "ℹ️ Cererea nu necesită apelarea unui tool MCP specific."
                    
        except Exception as e:
            print(f"⚠️ Eroare în analiză: {e}")
            return f"❌ Eroare în procesarea cererii pentru tool-urile MCP HTTP: {str(e)}"
        
    def query_llm_with_retry(self, prompt: str, max_tokens: int = 400, retries: int = 3) -> str:
        """Interogează LLM cu retry logic - FUNCȚIE SINCRONĂ"""
        for attempt in range(retries):
            try:
                if attempt > 0:
                    print(f"🔄 Reîncerc ({attempt + 1}/{retries})...")
                    time.sleep(2 ** attempt)
                
                return self._query_llm_single(prompt, max_tokens)
                
            except Exception as e:
                print(f"⚠️ Tentativa {attempt + 1} eșuată: {str(e)[:100]}")
                if attempt == retries - 1:
                    return f"❌ Nu pot accesa {self.provider} după {retries} încercări."
        
        return "❌ Eroare necunoscută"

    def _query_llm_single(self, prompt: str, max_tokens: int) -> str:
        """O singură interogare LLM - FUNCȚIE SINCRONĂ"""
        if self.provider == "openai":
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3,
                timeout=30
            )
            return response.choices[0].message.content.strip()

        raise Exception(f"Provider necunoscut: {self.provider}")

    def create_enhanced_prompt(self, user_input: str, tool_results: str = "") -> str:
        """Creează prompt îmbunătățit cu rezultate de la tool-uri MCP"""
        context_str = ""
        if self.session_context:
            recent_context = self.session_context[-2:]
            context_str = "\nContext anterior:\n"
            for ctx in recent_context:
                context_str += f"User: {ctx['user']}\nAI: {ctx['ai']}\n"

        tools_info = ""
        if self.mcp_tools:
            tools_info = f"\nTool-uri MCP HTTP disponibile: {', '.join(self.mcp_tools.keys())}"

        connection_info = f"Conexiune MCP: {'✅ Conectat via HTTP' if self.mcp_connected else '❌ Deconectat'}"

        system_prompt = f"""Ești un asistent AI expert în Alfresco Document Management System cu acces la tool-uri MCP prin HTTP.

{connection_info}
Model: {self.provider.upper()} - {self.model}
Server MCP: {self.mcp_server_url}
{tools_info}

{context_str}

{tool_results}

Întrebarea curentă: {user_input}

Instrucțiuni:
- Dacă ai rezultate de la tool-uri MCP, folosește-le în răspuns
- Răspunde concis și profesional
- Explică ce operațiuni au fost efectuate
- Nu repeta contextul inutil

Răspuns:"""

        return system_prompt

    async def test_mcp_connection_http(self):
        """Testează conexiunea HTTP cu serverul MCP"""
        if not self.mcp_connected:
            print("❌ Nu sunt conectat la serverul MCP HTTP")
            return False
        
        print("🔍 Testez conexiunea MCP HTTP...")
        
        try:
            if not self.http_client:
                await self._init_http_client()
                
            # Test health check
            health_ok = await self.check_server_health()
            if not health_ok:
                print("❌ Health check eșuat")
                return False
            
            # Test capabilities
            response = await self.http_client.get(f"{self.mcp_server_url}/capabilities")
            if response.status_code == 200:
                print("✅ Server MCP HTTP răspunde")
                return True
            else:
                print(f"❌ Server status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Eroare test conexiune HTTP: {e}")
            return False

    async def handle_user_input_async(self, user_input: str):
        """Handler async pentru input-ul utilizatorului - SOLUȚIA PRINCIPALĂ"""
        try:
            print(f"🤖 {self.provider.title()} (procesez cu MCP HTTP...)")
            start_time = time.time()
            
            # Analizează și apelează tool-uri MCP
            tool_results = await self.analyze_intent_and_call_tools_async(user_input)
            
            # Creează prompt îmbunătățit
            enhanced_prompt = self.create_enhanced_prompt(user_input, tool_results)
            
            # Obține răspunsul final - ATENȚIE: apel sincron
            response = self.query_llm_with_retry(enhanced_prompt, max_tokens=500)
            
            processing_time = time.time() - start_time
            print(f"🤖 {self.provider.title()} ({processing_time:.1f}s):")
            
            if tool_results and not any(msg in tool_results for msg in ["Nu pot interpreta", "Nu sunt conectat", "nu necesită"]):
                print(f"   {tool_results}")
            
            print(f"   {response}")
            
            # Salvează în context
            self.session_context.append({
                "user": user_input,
                "tool_results": tool_results,
                "ai": response,
                "timestamp": time.time()
            })
            
            if len(self.session_context) > 5:
                self.session_context.pop(0)
                
        except Exception as e:
            print(f"❌ Eroare procesare input: {e}")
        
    async def interactive_session_http_async(self):
        """Sesiune interactivă ASYNC cu server MCP prin HTTP - SOLUȚIA CORECTATĂ"""
        print(f"🤖 Client LLM pentru MCP Alfresco prin HTTP")
        print(f"⚡ Provider: {self.provider.upper()}")
        print(f"🧠 Model: {self.model}")
        print(f"🌐 Server MCP HTTP: {self.mcp_server_url}")
        print(f"🔌 Status: {'🟢 Conectat via HTTP' if self.mcp_connected else '🔴 Deconectat'}")
        print(f"🔧 Tool-uri MCP: {len(self.mcp_tools)}")
        if self.mcp_tools:
            print(f"   📋 Lista: {', '.join(list(self.mcp_tools.keys())[:5])}")
        print("💡 Comenzi: 'quit'/'exit', 'clear', 'tools', 'status'")
        print("=" * 70)

        while self.running:
            try:
                # Input non-blocking folosind threading
                user_input = await self._get_user_input_async()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['quit', 'exit', 'bye']:
                    print("👋 Închid sesiunea HTTP...")
                    break
                elif user_input.lower() == 'clear':
                    self.session_context.clear()
                    print("🧹 Context curățat!")
                    continue
                elif user_input.lower() == 'tools':
                    if self.mcp_tools:
                        print("🔧 Tool-uri MCP HTTP disponibile:")
                        for name, tool in self.mcp_tools.items():
                            desc = tool.get('description', 'Fără descriere')
                            print(f"  - {name}: {desc}")
                    else:
                        print("⚠️ Nu sunt tool-uri MCP disponibile")
                    continue
                elif user_input.lower() == 'status':
                    print(f"📡 Status HTTP: {'🟢 Conectat' if self.mcp_connected else '🔴 Deconectat'}")
                    print(f"🌐 Server URL: {self.mcp_server_url}")
                    print(f"🔧 Tool-uri: {len(self.mcp_tools)}")
                    if self.mcp_connected:
                        await self.test_mcp_connection_http()
                    continue

                # Procesează input-ul utilizatorului
                await self.handle_user_input_async(user_input)
                
            except KeyboardInterrupt:
                print("\n🛑 Întrerupt de utilizator")
                break
            except Exception as e:
                print(f"\n❌ Eroare în sesiune HTTP: {e}")

        self.running = False
        print(f"\n✅ Sesiune HTTP {self.provider} închisă!")

    async def _get_user_input_async(self) -> str:
        """Obține input de la utilizator în mod async"""
        def get_input():
            try:
                return input("\n🔤 Tu: ").strip()
            except (EOFError, KeyboardInterrupt):
                return "quit"
        
        # Rulează input în thread separat pentru a nu bloca event loop-ul
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_input)

    async def cleanup_http(self):
        """Curăță resursele HTTP"""
        self.running = False
        self.mcp_connected = False
        
        if self.http_client:
            await self.http_client.aclose()
        
        self.mcp_tools.clear()
        self.mcp_resources.clear()
        self.mcp_prompts.clear()
        
        print("🧹 Resurse MCP HTTP curățate")

    def __del__(self):
        pass