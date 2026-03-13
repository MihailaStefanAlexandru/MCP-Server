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

def is_valid_uuid(value):
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False

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

            print("DEBUG TOOL ARGUMENTS:", arguments)
            
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
        
    def extract_node_id_from_result(tool_result) -> str | None:
        """
        Extrage primul UUID valid.
        Gestionează wrapper-ul {"tool", "context", "result"} al serverului.
        """
        if isinstance(tool_result, dict):
            # Unwrap răspunsul serverului dacă e necesar
            if "result" in tool_result and isinstance(tool_result["result"], dict):
                tool_result = tool_result["result"]
            
            # Caută în câmpuri comune
            for key in ('id', 'node_id', 'nodeId'):
                val = tool_result.get(key, "")
                if isinstance(val, str) and is_valid_uuid(val):
                    return val
            
            # Caută în 'entry'
            entry = tool_result.get('entry', {})
            if isinstance(entry, dict):
                for key in ('id', 'node_id'):
                    val = entry.get(key, "")
                    if val and is_valid_uuid(val):
                        return val
            
            # Caută în 'items' (listă de noduri)
            items = tool_result.get('items', [])
            if isinstance(items, list) and items:
                first = items[0]
                if isinstance(first, dict):
                    val = first.get('id') or first.get('node_id', '')
                    if val and is_valid_uuid(val):
                        return val
        
        # Fallback: regex pe tot JSON-ul
        text = json.dumps(tool_result) if isinstance(tool_result, (dict, list)) else str(tool_result)
        uuids = re.findall(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            text, re.IGNORECASE
        )
        return uuids[0] if uuids else None


    def extract_items_from_result(tool_result) -> list:
        """
        Extrage lista de iteme.
        Gestionează wrapper-ul {"tool", "context", "result"} al serverului.
        """
        # Unwrap răspunsul serverului
        if isinstance(tool_result, dict) and "result" in tool_result:
            tool_result = tool_result["result"]
        
        if not isinstance(tool_result, dict):
            return []
        
        # Structura serverului tău: {"items": [...], "total": N, "message": "..."}
        items = tool_result.get("items", [])
        if isinstance(items, list):
            # Filtrează doar itemele cu 'id' și 'name' (nu cele label/value din get_node_info)
            node_items = [i for i in items if "id" in i and "name" in i]
            if node_items:
                return node_items
        
        # Fallback pentru structura Alfresco standard
        nested = tool_result.get('list', {})
        if isinstance(nested, dict):
            entries = nested.get('entries', [])
            return [e.get('entry', e) for e in entries if isinstance(e, dict)]
        
        return []
    
    def resolve_placeholder_arguments(arguments: dict, agent_state: dict) -> dict:
        """
        Înlocuiește orice valoare non-UUID în câmpurile *_id cu UUID-ul din agent_state.
        Previne trimiterea de placeholder-uri literale la Alfresco.
        """
        resolved = dict(arguments)
        
        for key, value in resolved.items():
            if 'id' in key.lower() and isinstance(value, str):
                if not is_valid_uuid(value):
                    # Valoarea e un placeholder — înlocuim cu ce avem în state
                    fallback = (
                        agent_state.get('last_node_id') or
                        agent_state.get('first_node_id')
                    )
                    if fallback:
                        print(f"⚠️  Placeholder detectat '{value}' → înlocuit cu '{fallback}'")
                        resolved[key] = fallback
                    else:
                        print(f"❌ Placeholder '{value}' fără fallback disponibil în agent_state")
        
        return resolved

    def analyze_intent_and_call_tools(self, user_input: str) -> str:

        max_steps = 8
        agent_scratchpad = ""
        # stare persistentă între pași: node_id-uri, nume, etc.
        agent_state = {}

        # construiește descrierea tool-urilor pentru prompt
        tools_description = ""
        for tool_name, tool_info in self.mcp_tools.items():
            desc = tool_info.get("description", "Fără descriere")
            schema = tool_info.get("inputSchema", {})
            props = schema.get("properties", {})
            required = schema.get("required", [])
            params_info = []
            for p_name, p_schema in props.items():
                req_marker = "*" if p_name in required else ""
                p_type = p_schema.get("type", "string")
                params_info.append(f"{p_name}{req_marker}({p_type})")
            
            tools_description += f"- **{tool_name}**: {desc}\n"
            if params_info:
                tools_description += f"  Parametri (* = obligatoriu): {', '.join(params_info)}\n"

        for step in range(max_steps):
            # construiește contextul de state pentru LLM
            state_context = ""
            if agent_state:
                state_context = "\n**State curent (valori REALE obținute din tool-uri):**\n"
                for k, v in agent_state.items():
                    state_context += f"  - {k}: `{v}`\n"
                state_context += "**IMPORTANT: Folosește aceste valori EXACT în arguments, nu inventa altele!**\n"

            prompt = f"""Ești un agent AI care rezolvă cereri pas cu pas folosind tool-uri MCP pentru Alfresco.

    **Tool-uri disponibile:**
    {tools_description}

    **Cererea utilizatorului:**
    {user_input}

    **Istoric execuție (pași anteriori):**
    {agent_scratchpad if agent_scratchpad else "Niciun pas executat încă."}
    {state_context}

    **Instrucțiuni CRITICE:**
    1. Analizează ce s-a făcut deja și ce mai trebuie făcut
    2. Dacă ai nevoie de un node_id, verifică State-ul curent — dacă e acolo, folosește-l EXACT
    3. NU inventa UUID-uri sau placeholder-uri (ex: "id-ul_folderului") — acestea cauzează erori 404
    4. Dacă task-ul e complet, returnează final_answer

    Răspunde DOAR cu JSON valid (fără markdown, fără text în afara JSON-ului):

    Dacă trebuie să apelezi un tool:
    {{"action": "call_tool", "tool_name": "nume_tool", "arguments": {{}}, "reasoning": "de ce apelezi acest tool acum"}}

    Dacă ai terminat și poți răspunde utilizatorului:
    {{"action": "final_answer", "answer": "răspunsul complet și detaliat"}}
    """

            raw_response = self.query_llm_with_retry(prompt, max_tokens=400)
            
            # parsează răspunsul LLM
            try:
                cleaned = raw_response.strip()
                # elimină fences markdown dacă există
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    cleaned = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
                
                # extrage JSON
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if not match:
                    print(f"⚠️  Step {step+1}: LLM nu a returnat JSON valid: {cleaned[:200]}")
                    agent_scratchpad += f"\nStep {step+1}: Eroare parsare răspuns LLM.\n"
                    continue
                
                analysis = json.loads(match.group())
                reasoning = analysis.get("reasoning", "")
                
            except json.JSONDecodeError as e:
                print(f"⚠️  Step {step+1}: JSON invalid: {e}")
                continue

            if analysis.get("action") == "final_answer":
                answer = analysis.get("answer", "")
                if answer:
                    return answer
                else:
                    print("⚠️  final_answer fără conținut, continui...")
                    continue

            if analysis.get("action") == "call_tool":
                tool_name = analysis.get("tool_name", "")
                arguments = analysis.get("arguments", {})
                
                if tool_name not in self.mcp_tools:
                    agent_scratchpad += f"\nStep {step+1}: Tool '{tool_name}' nu există.\n"
                    continue
                
                arguments = resolve_placeholder_arguments(arguments, agent_state)
                
                # verificare finală: dacă tool-ul necesită un node_id valid și nu-l avem, skip
                if "node_id" in arguments and not is_valid_uuid(arguments.get("node_id", "")):
                    agent_scratchpad += f"""
    Step {step+1} - Tool: {tool_name}
    Reasoning: {reasoning}
    Eroare: node_id invalid '{arguments.get('node_id')}' și nu există fallback în state.
    Sfat: Apelează mai întâi list_root_children sau get_node_id_by_name pentru a obține un UUID valid.
    """
                    continue
                
                print(f"🔧 Step {step+1}/{max_steps} - Execut: {tool_name}({json.dumps(arguments)})")
                
                tool_result = self.call_mcp_tool(tool_name, arguments)
                
                observation_text = ""
                
                if tool_result is None:
                    observation_text = "Tool a returnat None / eroare."
                
                elif isinstance(tool_result, dict) and "error" in tool_result:
                    observation_text = f"Eroare: {tool_result['error']}"
                
                else:
                    # serializează rezultatul pentru scratchpad
                    observation_text = json.dumps(tool_result, indent=2, ensure_ascii=False)
                    
                    # list_root_children → extrage primul item
                    items = extract_items_from_result(tool_result)
                    if items:
                        first_item = items[0]
                        first_id = first_item.get('id') or first_item.get('node_id', '')
                        first_name = first_item.get('name', '')
                        
                        if is_valid_uuid(first_id):
                            agent_state['first_node_id'] = first_id
                            agent_state['last_node_id'] = first_id
                            if first_name:
                                agent_state['first_node_name'] = first_name
                            
                            # stochează și toate itemele pentru referință
                            agent_state['all_items'] = [
                                {'id': it.get('id', ''), 'name': it.get('name', '')}
                                for it in items
                            ]
                            print(f"✅ State actualizat: first_node_id={first_id}, name={first_name}")
                    
                    # get_node_id_by_name sau orice tool care returnează un singur node
                    single_id = extract_node_id_from_result(tool_result)
                    if single_id and is_valid_uuid(single_id):
                        agent_state['last_node_id'] = single_id
                        if 'first_node_id' not in agent_state:
                            agent_state['first_node_id'] = single_id
                        print(f"✅ State actualizat: last_node_id={single_id}")
                    
                    # get_node_info → stochează info nod curent
                    if tool_name == "get_node_info":
                        # extrage date relevante din rezultat pentru a fi afișate în răspuns
                        node_data = tool_result
                        if isinstance(tool_result, dict):
                            node_data = tool_result.get('entry', tool_result)
                        agent_state['current_node_info'] = node_data
                
                # adauga în scratchpad
                agent_scratchpad += f"""
    Step {step+1} - Tool: {tool_name}
    Reasoning: {reasoning}
    Arguments: {json.dumps(arguments, ensure_ascii=False)}
    Observation:
    {observation_text[:2000]}{"...[trunchiat]" if len(observation_text) > 2000 else ""}
    """
                continue
            
            # action necunoscută
            print(f"⚠️  Action necunoscută: {analysis.get('action')}")
            agent_scratchpad += f"\nStep {step+1}: Action necunoscută '{analysis.get('action')}'.\n"

        # am epuizat pașii — returnează ce am colectat
        if agent_state.get('current_node_info'):
            return f"Am executat operațiunile cerute. Ultimul nod procesat:\n{json.dumps(agent_state['current_node_info'], indent=2, ensure_ascii=False)}"
        
        return f"⚠️ Limita de {max_steps} pași atinsă. State colectat: {json.dumps({k: v for k, v in agent_state.items() if k != 'all_items'}, ensure_ascii=False)}"

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