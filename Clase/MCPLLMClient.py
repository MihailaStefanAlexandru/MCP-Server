import os
import sys
import json
import time
import subprocess
import threading
import queue
from typing import Optional, Dict, Any
import uuid
import re

class MCPStdioLLMClient:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.provider = self.config['llm']['provider']
        self.api_key = self.config['llm']['api_key']
        self.model = self.config['llm']['model']
        
        # Configurare server MCP prin subprocess
        self.mcp_server_cmd = self.config.get('mcp', {}).get('server_command', ['python3', 'alfresco_mcp_server.py'])
        self.mcp_server_args = self.config.get('mcp', {}).get('server_args', [])
        self.mcp_server_env = self.config.get('mcp', {}).get('server_env', {})
        
        self.session_context = []
        self.input_queue = queue.Queue()
        self.running = True
        self.mcp_tools = {}
        self.mcp_resources = {}
        self.mcp_prompts = {}
        self.mcp_connected = False
        self.session_id = str(uuid.uuid4())
        
        # Server process și comunicație
        self.mcp_process = None
        self.message_queue = queue.Queue()
        self.response_events = {}  # Pentru a aștepta răspunsuri specifice
        
        # Session timeout pentru cleanup
        self.last_activity = time.time()
        self.session_timeout = 300  # 5 minute
        
        print(f"🔧 Inițializez clientul {self.provider.upper()} cu MCP STDIO")
        self._init_llm_client()

    def _init_llm_client(self):
        """Inițializează clientul LLM cu error handling îmbunătățit"""
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

    def start_mcp_server(self):
        """Pornește serverul MCP ca subprocess și stabilește comunicația prin STDIO"""
        try:
            print(f"🚀 Pornesc serverul MCP: {' '.join(self.mcp_server_cmd + self.mcp_server_args)}")
            
            # Pregătește environment-ul pentru server
            env = os.environ.copy()
            env.update(self.mcp_server_env)
            
            # Pornește procesul server MCP
            self.mcp_process = subprocess.Popen(
                self.mcp_server_cmd + self.mcp_server_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,  # Unbuffered pentru comunicație în timp real
                env=env,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None  # Pentru cleanup mai bun
            )
            
            print(f"✅ Server MCP pornit cu PID: {self.mcp_process.pid}")
            
            # Pornește thread-urile pentru citirea output-ului
            self.start_io_threads()
            
            # Încearcă inițializarea protocolului MCP
            return self.initialize_mcp_protocol()
            
        except FileNotFoundError:
            print(f"❌ Nu pot găsi serverul MCP: {self.mcp_server_cmd[0]}")
            print("💡 Verifică că path-ul către server este corect în configurație")
            return False
        except Exception as e:
            print(f"❌ Eroare pornire server MCP: {e}")
            return False

    def start_io_threads(self):
        """Pornește thread-urile pentru comunicația STDIO cu serverul MCP"""
        # Thread pentru citirea stdout (mesaje de la server)
        self.stdout_thread = threading.Thread(
            target=self._read_stdout, 
            daemon=True,
            name="MCP-STDOUT-Reader"
        )
        self.stdout_thread.start()
        
        # Thread pentru citirea stderr (loguri și erori)
        self.stderr_thread = threading.Thread(
            target=self._read_stderr, 
            daemon=True,
            name="MCP-STDERR-Reader"
        )
        self.stderr_thread.start()

    def _read_stdout(self):
        """Citește mesajele JSON-RPC de pe stdout al serverului"""
        while self.running and self.mcp_process:
            try:
                if self.mcp_process.poll() is not None:
                    print("⚠️  Procesul server MCP s-a oprit neașteptat")
                    break
                
                line = self.mcp_process.stdout.readline()
                if not line:
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                try:
                    message = json.loads(line)
                    self._handle_mcp_message(message)
                except json.JSONDecodeError:
                    print(f"⚠️  Mesaj non-JSON primit: {line[:100]}")
                    
            except Exception as e:
                if self.running:
                    print(f"❌ Eroare citire stdout: {e}")
                break

    def _read_stderr(self):
        """Citește erorile și logurile de pe stderr al serverului"""
        while self.running and self.mcp_process:
            try:
                if self.mcp_process.poll() is not None:
                    break
                
                line = self.mcp_process.stderr.readline()
                if not line:
                    continue
                
                line = line.strip()
                if line:
                    print(f"🔍 Server stderr: {line}")
                    
            except Exception as e:
                if self.running:
                    print(f"❌ Eroare citire stderr: {e}")
                break

    def _handle_mcp_message(self, message: Dict[str, Any]):
        """Procesează mesajele primite de la serverul MCP"""
        try:
            # Mesaj cu ID - este un răspuns la o cerere
            if 'id' in message:
                message_id = message['id']
                if message_id in self.response_events:
                    self.response_events[message_id]['response'] = message
                    self.response_events[message_id]['event'].set()
                else:
                    print(f"⚠️  Răspuns neașteptat cu ID: {message_id}")
            
            # Mesaj fără ID - este o notificare
            elif 'method' in message:
                method = message['method']
                print(f"📢 Notificare server: {method}")
                # Aici poți adăuga handling pentru notificări specifice
            
            else:
                print(f"🔍 Mesaj MCP necunoscut: {message}")
                
        except Exception as e:
            print(f"❌ Eroare procesare mesaj MCP: {e}")

    def send_mcp_request(self, method: str, params: Dict[str, Any] = None, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Trimite o cerere JSON-RPC la serverul MCP și așteaptă răspunsul"""
        if not self.mcp_process or self.mcp_process.poll() is not None:
            print("❌ Serverul MCP nu rulează")
            return None
        
        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }
        
        if params is not None:
            request["params"] = params
        
        # Pregătește event-ul pentru răspuns
        response_event = threading.Event()
        self.response_events[request_id] = {
            'event': response_event,
            'response': None
        }
        
        try:
            # Trimite cererea
            request_json = json.dumps(request) + '\n'
            print(f"📤 Trimit cerere MCP: {method}")
            self.mcp_process.stdin.write(request_json)
            self.mcp_process.stdin.flush()
            
            # Așteaptă răspunsul
            if response_event.wait(timeout=timeout):
                response = self.response_events[request_id]['response']
                del self.response_events[request_id]
                
                if 'error' in response:
                    print(f"❌ Eroare MCP: {response['error']}")
                    return None
                
                return response.get('result')
            else:
                print(f"⏰ Timeout la cererea MCP: {method}")
                del self.response_events[request_id]
                return None
                
        except Exception as e:
            print(f"❌ Eroare trimitere cerere MCP: {e}")
            if request_id in self.response_events:
                del self.response_events[request_id]
            return None

    def initialize_mcp_protocol(self):
        """Inițializează protocolul MCP prin STDIO"""
        try:
            print("🤝 Inițializez protocolul MCP...")
            
            # Trimite cererea de inițializare
            init_params = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {}
                },
                "clientInfo": {
                    "name": "llm-mcp-stdio-client",
                    "version": "1.0.0"
                }
            }
            
            result = self.send_mcp_request("initialize", init_params)
            
            if result:
                print("✅ Protocol MCP inițializat cu succes")
                
                # Salvează capabilitățile serverului
                server_capabilities = result.get('capabilities', {})
                print(f"🔧 Capabilități server: {list(server_capabilities.keys())}")
                
                # Trimite notificarea de finalizare inițializare
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                }
                notification_json = json.dumps(notification) + '\n'
                self.mcp_process.stdin.write(notification_json)
                self.mcp_process.stdin.flush()
                print("📢 Notificare initialized trimisă")
                
                self.mcp_connected = True
                
                # Obține tool-urile disponibile
                return self._discover_mcp_capabilities()
            else:
                print("❌ Inițializare MCP eșuată")
                return False
                
        except Exception as e:
            print(f"❌ Eroare inițializare protocol MCP: {e}")
            return False

    def _discover_mcp_capabilities(self):
        """Descoperă tool-urile, resursele și prompt-urile disponibile"""
        success = True
        
        # Obține tool-urile
        try:
            print("🔧 Obțin tool-urile disponibile...")
            tools_result = self.send_mcp_request("tools/list")
            if tools_result and 'tools' in tools_result:
                for tool in tools_result['tools']:
                    self.mcp_tools[tool['name']] = tool
                print(f"✅ Găsite {len(self.mcp_tools)} tool-uri: {list(self.mcp_tools.keys())}")
            else:
                print("⚠️  Nu s-au găsit tool-uri")
                success = False
        except Exception as e:
            print(f"❌ Eroare obținere tool-uri: {e}")
            success = False
        
        # Obține resursele
        try:
            print("📁 Obțin resursele disponibile...")
            resources_result = self.send_mcp_request("resources/list")
            if resources_result and 'resources' in resources_result:
                for resource in resources_result['resources']:
                    self.mcp_resources[resource['uri']] = resource
                print(f"✅ Găsite {len(self.mcp_resources)} resurse")
            else:
                print("ℹ️  Nu s-au găsit resurse")
        except Exception as e:
            print(f"⚠️  Eroare obținere resurse: {e}")
        
        # Obține prompt-urile
        try:
            print("💭 Obțin prompt-urile disponibile...")
            prompts_result = self.send_mcp_request("prompts/list")
            if prompts_result and 'prompts' in prompts_result:
                for prompt in prompts_result['prompts']:
                    self.mcp_prompts[prompt['name']] = prompt
                print(f"✅ Găsite {len(self.mcp_prompts)} prompt-uri")
            else:
                print("ℹ️  Nu s-au găsit prompt-uri")
        except Exception as e:
            print(f"⚠️  Eroare obținere prompt-uri: {e}")
        
        return success

    def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Apelează un tool MCP prin STDIO"""
        if tool_name not in self.mcp_tools:
            return {"error": f"Tool-ul '{tool_name}' nu este disponibil"}
        
        if not self.mcp_connected:
            return {"error": "Nu sunt conectat la serverul MCP"}
        
        try:
            print(f"🔧 Apelez tool MCP: {tool_name}")
            
            # Trimite cererea de apelare tool
            call_params = {
                "name": tool_name,
                "arguments": arguments
            }
            
            result = self.send_mcp_request("tools/call", call_params, timeout=60.0)
            
            # DEBUG: Log exact ce returnează serverul
            print(f"🔍 DEBUG: Tool result type: {type(result)}")
            print(f"🔍 DEBUG: Tool result content: {str(result)[:200]}...")
            
            if result:
                print(f"✅ Tool {tool_name} executat cu succes")
                return result
            else:
                return {"error": f"Apelarea tool-ului {tool_name} a eșuat"}
                
        except Exception as e:
            print(f"❌ Eroare apelare tool MCP: {e}")
            return {"error": str(e)}

    def analyze_intent_and_call_tools(self, user_input: str) -> str:
        """Analizează intenția utilizatorului și apelează tool-urile MCP corespunzătoare"""
        if not self.mcp_connected or not self.mcp_tools:
            return "ℹ️  Nu sunt conectat la serverul MCP sau nu sunt tool-uri disponibile."
        
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

        # Obține analiza de la LLM
        analysis_response = self.query_llm_with_retry(analysis_prompt, max_tokens=300)
        
        try:
            # Curăță răspunsul și încearcă să parseze JSON-ul
            cleaned_response = analysis_response.strip()
            
            # Elimină markdown code blocks dacă există
            if cleaned_response.startswith('```'):
                lines = cleaned_response.split('\n')
                cleaned_response = '\n'.join(lines[1:-1])
            
            # Găsește JSON-ul în răspuns
            json_match = re.search(r'\{.*\}', cleaned_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                print(f"🔍 JSON detectat: {json_str}")
                analysis = json.loads(json_str)
                
                if analysis.get('action') == 'call_tool':
                    tool_name = analysis.get('tool_name')
                    arguments = analysis.get('arguments', {})
                    explanation = analysis.get('explanation', '')
                    
                    if tool_name in self.mcp_tools:
                        print(f"🎯 Execut: {explanation}")
                        # Apelează tool-ul MCP
                        tool_result = self.call_mcp_tool(tool_name, arguments)
                        
                        # FIX: Verifică tipul răspunsului ÎNAINTE de a apela .get()
                        if isinstance(tool_result, str):
                            # Dacă tool_result este string, înseamnă că e un mesaj de eroare
                            return f"❌ Eroare la executarea {tool_name}: {tool_result}"
                        
                        if isinstance(tool_result, dict):
                            # Verifică dacă există eroare în dict
                            if tool_result.get('error'):
                                error_msg = tool_result.get('error', 'Eroare necunoscută')
                                return f"❌ Eroare la executarea {tool_name}: {error_msg}"
                            
                            # Procesează rezultatul cu succes
                            if 'content' in tool_result:
                                # Rezultat cu conținut structurat
                                content_items = tool_result['content']
                                result_text = ""
                                for item in content_items:
                                    if isinstance(item, dict) and item.get('type') == 'text':
                                        result_text += item.get('text', '')
                                    elif isinstance(item, str):
                                        result_text += item
                                return f"🔧 Rezultat {tool_name}:\n{result_text}"
                            else:
                                # Rezultat simplu
                                result_str = json.dumps(tool_result, indent=2, ensure_ascii=False)
                                return f"🔧 Rezultat {tool_name}:\n{result_str}"
                        
                        # Fallback pentru alte tipuri
                        return f"🔧 Rezultat {tool_name}:\n{str(tool_result)}"
                        
                    else:
                        return f"❌ Tool-ul '{tool_name}' nu este disponibil"
                else:
                    return "ℹ️  Cererea nu necesită apelarea unui tool MCP specific."
                    
        except json.JSONDecodeError as e:
            print(f"⚠️  Nu pot parsa JSON din răspunsul LLM: {e}")
            print(f"📄 Răspuns raw: {analysis_response}")
            return "❌ Nu pot interpreta analiza pentru tool-urile MCP."
        except Exception as e:
            print(f"⚠️  Eroare în analiză: {e}")
            return f"❌ Eroare în procesarea cererii pentru tool-urile MCP: {str(e)}"

    def query_llm_with_retry(self, prompt: str, max_tokens: int = 400, retries: int = 3) -> str:
        """Interogează LLM cu retry logic și timeout"""
        for attempt in range(retries):
            try:
                if attempt > 0:
                    print(f"🔄 Reîncerc ({attempt + 1}/{retries})...")
                    time.sleep(2 ** attempt)
                
                return self._query_llm_single(prompt, max_tokens)
                
            except Exception as e:
                print(f"⚠️  Tentativa {attempt + 1} eșuată: {str(e)[:100]}")
                if attempt == retries - 1:
                    return f"❌ Nu pot accesa {self.provider} după {retries} încercări."
        
        return "❌ Eroare necunoscută"

    def _query_llm_single(self, prompt: str, max_tokens: int) -> str:
        """O singură interogare LLM cu timeout strict"""
        if self.provider == "openai":
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3,
                timeout=30
            )
            return response.choices[0].message.content.strip()

        elif self.provider == "groq":
            response = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()

        raise Exception(f"Provider necunoscut: {self.provider}")

    def process_user_input_async(self):
        """Thread pentru input non-blocking"""
        while self.running:
            try:
                import select
                if sys.stdin in select.select([sys.stdin], [], [], 1)[0]:
                    user_input = sys.stdin.readline().strip()
                    if user_input:
                        self.input_queue.put(user_input)
                        self.last_activity = time.time()
            except:
                break

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
            tools_info = f"\nTool-uri MCP disponibile: {', '.join(self.mcp_tools.keys())}"

        connection_info = f"Conexiune MCP: {'✅ Conectat via STDIO' if self.mcp_connected else '❌ Deconectat'}"

        system_prompt = f"""Ești un asistent AI expert în Alfresco Document Management System cu acces la tool-uri MCP prin STDIO.

{connection_info}
Model: {self.provider.upper()} - {self.model}
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

    def test_mcp_connection(self):
        """Testează conexiunea cu serverul MCP"""
        if not self.mcp_connected or not self.mcp_process:
            print("❌ Nu sunt conectat la serverul MCP")
            return False
        
        if self.mcp_process.poll() is not None:
            print("❌ Procesul server MCP s-a oprit")
            return False
        
        print("🔍 Testez conexiunea MCP...")
        
        try:
            # Test simplu - cere din nou lista de tool-uri
            result = self.send_mcp_request("tools/list", timeout=5.0)
            if result:
                print(f"✅ Server MCP răspunde - {len(result.get('tools', []))} tool-uri")
                return True
            else:
                print("❌ Serverul nu răspunde la teste")
                return False
                
        except Exception as e:
            print(f"❌ Eroare test conexiune: {e}")
            return False

    def interactive_session_stdio(self):
        """Sesiune interactivă cu server MCP prin STDIO"""
        print(f"🤖 Client LLM pentru MCP Alfresco prin STDIO")
        print(f"⚡ Provider: {self.provider.upper()}")
        print(f"🧠 Model: {self.model}")
        print(f"🔌 Server MCP: {'🟢 Conectat via STDIO' if self.mcp_connected else '🔴 Deconectat'}")
        print(f"🔧 Tool-uri MCP: {len(self.mcp_tools)}")
        if self.mcp_tools:
            print(f"   📋 Lista: {', '.join(list(self.mcp_tools.keys())[:5])}")
        print(f"📁 Resurse MCP: {len(self.mcp_resources)}")
        print(f"💭 Prompt-uri MCP: {len(self.mcp_prompts)}")
        print("💡 Comenzi: 'quit'/'exit', 'clear', 'tools', 'resources', 'status', 'restart'")
        print("=" * 70)

        # Pornește thread pentru input non-blocking
        input_thread = threading.Thread(target=self.process_user_input_async, daemon=True)
        input_thread.start()

        print("\n🔤 Tu: ", end="", flush=True)

        while self.running:
            try:
                # Verifică timeout sesiune
                if time.time() - self.last_activity > self.session_timeout:
                    print(f"\n⏰ Sesiune expirată după {self.session_timeout}s")
                    break

                # Verifică dacă serverul MCP încă rulează
                if self.mcp_process and self.mcp_process.poll() is not None:
                    print(f"\n❌ Serverul MCP s-a oprit neașteptat (cod: {self.mcp_process.returncode})")
                    self.mcp_connected = False

                # Verifică input nou
                try:
                    user_input = self.input_queue.get(timeout=1)
                except queue.Empty:
                    continue

                # Procesează comenzi speciale
                if user_input.lower() in ['quit', 'exit', 'bye']:
                    print("👋 Închid sesiunea...")
                    break
                elif user_input.lower() == 'clear':
                    self.session_context.clear()
                    print("🧹 Context curățat!")
                    print("🔤 Tu: ", end="", flush=True)
                    continue
                elif user_input.lower() == 'tools':
                    if self.mcp_tools:
                        print("🔧 Tool-uri MCP disponibile:")
                        for name, tool in self.mcp_tools.items():
                            desc = tool.get('description', 'Fără descriere')
                            schema = tool.get('inputSchema', {})
                            props = schema.get('properties', {})
                            print(f"  - {name}: {desc}")
                            if props:
                                print(f"    Parametri: {', '.join(props.keys())}")
                    else:
                        print("⚠️  Nu sunt tool-uri MCP disponibile")
                    print("🔤 Tu: ", end="", flush=True)
                    continue
                elif user_input.lower() == 'resources':
                    if self.mcp_resources:
                        print("📁 Resurse MCP disponibile:")
                        for uri, resource in self.mcp_resources.items():
                            name = resource.get('name', uri)
                            desc = resource.get('description', 'Fără descriere')
                            print(f"  - {name}: {desc}")
                    else:
                        print("ℹ️  Nu sunt resurse MCP disponibile")
                    print("🔤 Tu: ", end="", flush=True)
                    continue
                elif user_input.lower() == 'status':
                    print(f"📡 Status conexiune: {'🟢 Conectat via STDIO' if self.mcp_connected else '🔴 Deconectat'}")
                    print(f"🔧 Tool-uri: {len(self.mcp_tools)}")
                    print(f"📁 Resurse: {len(self.mcp_resources)}")
                    print(f"💭 Prompt-uri: {len(self.mcp_prompts)}")
                    if self.mcp_process:
                        status = "🟢 Rulează" if self.mcp_process.poll() is None else f"🔴 Oprit (cod: {self.mcp_process.returncode})"
                        print(f"⚙️  Proces server: PID {self.mcp_process.pid} - {status}")
                    if self.mcp_connected:
                        self.test_mcp_connection()
                    print("🔤 Tu: ", end="", flush=True)
                    continue
                elif user_input.lower() == 'restart':
                    print("🔄 Restart server MCP...")
                    self.stop_mcp_server()
                    time.sleep(1)
                    if self.start_mcp_server():
                        print("✅ Server MCP restartat cu succes!")
                    else:
                        print("❌ Restart server MCP eșuat")
                    print("🔤 Tu: ", end="", flush=True)
                    continue
                elif not user_input.strip():
                    print("🔤 Tu: ", end="", flush=True)
                    continue

                print(f"🤖 {self.provider.title()} (procesez{'cu MCP' if self.mcp_connected else ' fără MCP'}...)")
                start_time = time.time()
                
                # PASUL 1: Analizează și apelează tool-uri MCP dacă e necesar
                tool_results = ""
                if self.mcp_connected and self.mcp_tools:
                    tool_results = self.analyze_intent_and_call_tools(user_input)
                
                # PASUL 2: Creează prompt îmbunătățit cu rezultatele tool-urilor
                enhanced_prompt = self.create_enhanced_prompt(user_input, tool_results)
                
                # PASUL 3: Obține răspunsul final de la LLM
                response = self.query_llm_with_retry(enhanced_prompt, max_tokens=500)
                
                processing_time = time.time() - start_time
                print(f"🤖 {self.provider.title()} ({processing_time:.1f}s):")
                
                # Afișează rezultatele tool-urilor dacă există
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
                
                # Limitează contextul
                if len(self.session_context) > 5:
                    self.session_context.pop(0)
                
                print("\n🔤 Tu: ", end="", flush=True)
                
            except KeyboardInterrupt:
                print("\n🛑 Întrerupt de utilizator")
                break
            except Exception as e:
                print(f"\n❌ Eroare în sesiune: {e}")
                print("🔄 Încerc să continui...")
                print("🔤 Tu: ", end="", flush=True)

        self.running = False
        print(f"\n✅ Sesiune {self.provider} închisă!")

    def stop_mcp_server(self):
        """Oprește serverul MCP și curăță resursele"""
        self.running = False
        self.mcp_connected = False
        
        if self.mcp_process:
            try:
                print("🛑 Opresc serverul MCP...")
                
                # Încearcă să închidă procesul elegant
                self.mcp_process.stdin.close()
                
                # Așteaptă un pic să se închidă
                try:
                    self.mcp_process.wait(timeout=5)
                    print(f"✅ Server MCP oprit elegant (cod: {self.mcp_process.returncode})")
                except subprocess.TimeoutExpired:
                    print("⚠️  Timeout - forțez oprirea serverului...")
                    self.mcp_process.kill()
                    self.mcp_process.wait()
                    print("✅ Server MCP oprit forțat")
                    
            except Exception as e:
                print(f"⚠️  Eroare oprire server: {e}")
                try:
                    self.mcp_process.kill()
                except:
                    pass
            finally:
                self.mcp_process = None
        
        # Curăță cache-urile
        self.mcp_tools.clear()
        self.mcp_resources.clear()
        self.mcp_prompts.clear()
        self.response_events.clear()
        
        print("🧹 Resurse MCP curățate")

    def __del__(self):
        """Destructor pentru cleanup garantat"""
        self.stop_mcp_server()