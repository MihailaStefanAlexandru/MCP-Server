#!/usr/bin/env python3
"""
Client MCP pentru comunicație HTTP
"""
import ast
import re
import sys
import json
import time
import uuid
from typing import Optional, Dict, Any, List
import httpx
import asyncio
import logging

logger = logging.getLogger("mcp_http_client")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler("mcp_client.log", mode="w", encoding="utf-8")
fh.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
fh.setFormatter(formatter)

ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
ch.setFormatter(formatter)

logger.addHandler(fh)
logger.addHandler(ch)


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
        self.session_context: List[Dict[str, Any]] = []
        self.running = True
        self.mcp_tools: Dict[str, Any] = {}
        self.mcp_resources: Dict[str, Any] = {}
        self.mcp_prompts: Dict[str, Any] = {}
        self.mcp_connected = False
        self.session_id = str(uuid.uuid4())

        # Client HTTP — inițializat în metoda async
        self.http_client: Optional[httpx.AsyncClient] = None

        # Session timing
        self.last_activity = time.time()
        self.session_timeout = 300

        print(f"🔧 Inițializez clientul {self.provider.upper()} cu MCP HTTP")
        self._init_llm_client()

    def _init_llm_client(self):
        """Inițializează clientul LLM."""
        try:
            if self.provider == "openai":
                import openai
                self.openai_client = openai.OpenAI(
                    api_key=self.api_key,
                    timeout=30,
                    max_retries=2
                )
                self.openai_client.models.list()
                print("✅ OpenAI client inițializat")
        except Exception as e:
            print(f"❌ Eroare inițializare {self.provider}: {e}")
            print("💡 Verifică API key-ul și conexiunea la internet")
            sys.exit(1)

    async def _init_http_client(self):
        """Inițializează clientul HTTP async."""
        if not self.http_client:
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True
            )

    def _log_request(self, request: httpx.Request):
        logger.debug(f"➡️ REQUEST: {request.method} {request.url}")
        if request.content:
            try:
                body = request.content.decode() if isinstance(request.content, bytes) else request.content
                logger.debug(f"Body: {body}")
            except Exception:
                logger.debug("Body: <non-decodable>")

    def _log_response(self, response: httpx.Response):
        logger.debug(f"⬅️ RESPONSE: {response.status_code} {response.reason_phrase}")
        try:
            logger.debug(f"Body: {response.text[:2000]}")
        except Exception:
            logger.debug("Body: <non-decodable>")

    async def start_mcp_server_http(self) -> bool:
        """Pornește serverul MCP HTTP și stabilește conexiunea."""
        try:
            await self._init_http_client()

            if await self.check_server_health():
                print("✅ Serverul MCP HTTP rulează deja")
                return await self.initialize_mcp_http_protocol()

            print("🚀 Aștept serverul MCP HTTP...")
            for i in range(30):
                if await self.check_server_health():
                    print(f"✅ Server MCP HTTP disponibil după {i + 1}s")
                    return await self.initialize_mcp_http_protocol()
                await asyncio.sleep(1)

            print("❌ Serverul MCP HTTP nu a pornit în timpul alocat")
            return False

        except Exception as e:
            print(f"❌ Eroare pornire server MCP HTTP: {e}")
            return False

    async def check_server_health(self) -> bool:
        """Verifică dacă serverul MCP HTTP este disponibil."""
        url = f"{self.mcp_server_url}/health"
        try:
            if not self.http_client:
                await self._init_http_client()
            response = await self.http_client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Eroare check_server_health: {e}")
            return False

    async def initialize_mcp_http_protocol(self) -> bool:
        """Inițializează protocolul MCP prin HTTP."""
        try:
            print("🤝 Inițializez protocolul MCP prin HTTP...")

            if not self.http_client:
                await self._init_http_client()

            init_data = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                    "clientInfo": {"name": "llm-mcp-http-client", "version": "1.0.0"}
                }
            }

            response = await self.http_client.post(f"{self.mcp_server_url}/mcp", json=init_data)
            response.raise_for_status()
            result = response.json()

            if result.get('result'):
                print("✅ Protocol MCP HTTP inițializat cu succes")

                notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                await self.http_client.post(f"{self.mcp_server_url}/mcp/notify", json=notification)

                self.mcp_connected = True
                return await self._discover_mcp_capabilities_http()
            else:
                print("❌ Inițializare MCP HTTP eșuată")
                return False

        except Exception as e:
            print(f"❌ Eroare inițializare protocol MCP HTTP: {e}")
            return False

    async def _discover_mcp_capabilities_http(self) -> bool:
        """Descoperă tool-urile prin HTTP."""
        try:
            print("🔧 Obțin tool-urile prin HTTP...")
            tools_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/list"
            }

            response = await self.http_client.post(f"{self.mcp_server_url}/mcp", json=tools_request)
            response.raise_for_status()
            result = response.json()

            if result.get('result') and 'tools' in result['result']:
                for tool in result['result']['tools']:
                    self.mcp_tools[tool['name']] = tool
                print(f"✅ Găsite {len(self.mcp_tools)} tool-uri HTTP: {list(self.mcp_tools.keys())}")
                return True
            else:
                print("⚠️ Nu s-au găsit tool-uri HTTP")
                return False

        except Exception as e:
            print(f"❌ Eroare obținere tool-uri HTTP: {e}")
            return False

    async def test_mcp_connection_http(self) -> bool:
        """Testează conexiunea HTTP cu serverul MCP."""
        if not self.mcp_connected:
            print("❌ Nu sunt conectat la serverul MCP HTTP")
            return False

        print("🔍 Testez conexiunea MCP HTTP...")
        try:
            if not self.http_client:
                await self._init_http_client()

            health_ok = await self.check_server_health()
            if not health_ok:
                print("❌ Health check eșuat")
                return False

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

    async def call_mcp_tool_http(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any],
        alfresco_username: Optional[str] = None,
        alfresco_password: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        
        """Apelează un tool MCP prin HTTP."""
        if tool_name not in self.mcp_tools:
            return {"error": f"Tool-ul '{tool_name}' nu este disponibil"}

        if not self.mcp_connected:
            return {"error": "Nu sunt conectat la serverul MCP HTTP"}

        url = f"{self.mcp_server_url}/mcp"

        extra_headers = {}
        if alfresco_username and alfresco_password:
            extra_headers["X-Alfresco-Username"] = alfresco_username
            extra_headers["X-Alfresco-Password"] = alfresco_password

        try:
            logger.debug(f"🔧 Apelez tool MCP HTTP: {tool_name}")

            if not self.http_client:
                await self._init_http_client()

            call_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            logger.debug(f"➡️ REQUEST: POST {url} {json.dumps(call_request, indent=2)}")

            response = await self.http_client.post(url, json=call_request, headers=extra_headers)
            logger.debug(f"⬅️ RESPONSE {response.status_code} {response.reason_phrase}")
            logger.debug(f"Body: {response.text[:2000]}")

            response.raise_for_status()
            result = response.json()

            if result.get('result'):
                logger.info(f"✅ Tool HTTP {tool_name} executat cu succes")
                logger.debug(f"Result: {result}")
                return result
            elif result.get('error'):
                logger.warning(f"⚠️ Tool {tool_name} eroare: {result['error']}")
                return {"error": f"Eroare server: {result['error']}"}
            else:
                logger.warning(f"⚠️ Răspuns neașteptat pentru tool {tool_name}: {result}")
                return {"error": "Răspuns neașteptat de la server"}

        except Exception as e:
            logger.error(f"❌ Eroare apelare tool MCP HTTP {tool_name}: {e}", exc_info=True)
            return {"error": str(e)}

    def format_tool_result(self, tool_name: str, tool_result) -> str:
        """
        Formatează consistent rezultatul de la un tool MCP.
        Gestionează structura: result -> content -> [{"type": "text", "text": "..."}]
        """
        if tool_result is None:
            return f"❌ Tool-ul {tool_name} nu a returnat niciun rezultat"

        if isinstance(tool_result, str):
            return tool_result

        if isinstance(tool_result, dict):
            # Eroare explicită
            if tool_result.get('error') and not tool_result.get('result'):
                return f"❌ Eroare: {tool_result['error']}"

            # Structura MCP standard: {result: {content: [{type, text}]}}
            content_list = None
            if 'result' in tool_result and isinstance(tool_result['result'], dict):
                content_list = tool_result['result'].get('content')
            elif 'content' in tool_result:
                content_list = tool_result['content']

            if content_list and isinstance(content_list, list):
                return "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content_list
                )

            return json.dumps(tool_result, indent=2, ensure_ascii=False)

        return str(tool_result)

    def _extract_data_from_result(self, tool_result) -> dict:
        """
        Extrage dict-ul de date real din răspunsul MCP.

        Serverul Alfresco returnează text în format Python repr (single quotes),
        nu JSON valid. Gestionăm ambele formate.
        """
        if not isinstance(tool_result, dict):
            return {}

        # Unwrap MCP response: {result: {content: [{type, text}]}}
        content_list = None
        if 'result' in tool_result and isinstance(tool_result['result'], dict):
            content_list = tool_result['result'].get('content', [])
        elif 'content' in tool_result:
            content_list = tool_result.get('content', [])

        if not content_list:
            return {}

        text_content = "".join(
            item.get("text", "") for item in content_list
            if isinstance(item, dict) and item.get("type") == "text"
        )

        if not text_content:
            return {}

        # Încearcă JSON standard
        try:
            return json.loads(text_content)
        except json.JSONDecodeError:
            pass

        # Fallback: Python repr cu single quotes (comportamentul serverului tău)
        try:
            return ast.literal_eval(text_content)
        except Exception:
            pass

        return {}

    def _is_valid_uuid(self, value: str) -> bool:
        """Verifică dacă un string este UUID valid."""
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(pattern, str(value).strip(), re.IGNORECASE))

    def _extract_uuid_from_text(self, text: str) -> Optional[str]:
        """Extrage primul UUID valid dintr-un text."""
        pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        matches = re.findall(pattern, str(text), re.IGNORECASE)
        return matches[0] if matches else None

    def _resolve_placeholders(self, arguments: dict, agent_state: dict) -> dict:
        """
        Înlocuiește orice valoare non-UUID în câmpurile *_id / *id*
        cu UUID-ul real din agent_state.
        Aceasta este principala protecție împotriva placeholder-urilor inventate de LLM.
        """
        resolved = dict(arguments)
        for key, value in resolved.items():
            if 'id' in key.lower() and isinstance(value, str):
                if not self._is_valid_uuid(value):
                    fallback = (
                        agent_state.get('last_node_id') or
                        agent_state.get('first_node_id')
                    )
                    if fallback:
                        logger.warning(
                            f"Placeholder '{value}' în '{key}' → înlocuit cu '{fallback}'"
                        )
                        resolved[key] = fallback
                    else:
                        logger.warning(
                            f"Placeholder '{value}' în '{key}' — fără fallback în state"
                        )
        return resolved

    def _update_agent_state(
        self,
        agent_state: dict,
        tool_name: str,
        raw_result,
        observation_text: str
    ) -> None:
        """
        Actualizează agent_state cu datele extrase din rezultatul unui tool.
        Fiecare tool are o logică specifică de extragere.
        """
        data = self._extract_data_from_result(raw_result)

        if tool_name == "list_root_children":
            items = data.get("items", [])
            if items:
                first = items[0]
                first_id = first.get("id", "")
                first_name = first.get("name", "")

                if self._is_valid_uuid(first_id):
                    agent_state['first_node_id'] = first_id
                    agent_state['last_node_id'] = first_id
                    agent_state['first_node_name'] = first_name
                    agent_state['all_items'] = [
                        {
                            "id": it.get("id", ""),
                            "name": it.get("name", ""),
                            "type": it.get("type", "")
                        }
                        for it in items
                    ]
                    logger.info(f"State actualizat: first_node_id={first_id}, name={first_name}")

        elif tool_name == "get_node_id_by_name":
            node_id = data.get("node_id", "")
            name = data.get("name", "")
            if self._is_valid_uuid(node_id):
                agent_state['last_node_id'] = node_id
                if 'first_node_id' not in agent_state:
                    agent_state['first_node_id'] = node_id
                if name:
                    agent_state['resolved_name'] = name
                logger.info(f"State actualizat: last_node_id={node_id} pentru name={name}")

        elif tool_name == "get_node_info":
            node = data.get("node", {})
            node_id = node.get("id", "")
            if self._is_valid_uuid(node_id):
                agent_state['current_node_id'] = node_id
                agent_state['current_node_info'] = node
                logger.info(f"State actualizat: current_node_info pentru id={node_id}")

        elif tool_name in ("get_node_children", "browse_by_path"):
            items = data.get("items", [])
            if items:
                # Salvează toate nodurile după nume pentru lookup ulterior
                for item in items:
                    item_id = item.get("id", "")
                    item_name = item.get("name", "")
                    if self._is_valid_uuid(item_id) and item_name:
                        agent_state[f"node_id_{item_name.lower()}"] = item_id
                
                # last_node_id = primul item (comportament existent)
                first_id = items[0].get("id", "")
                if self._is_valid_uuid(first_id):
                    agent_state['last_node_id'] = first_id
                    logger.info(f"State actualizat: last_node_id={first_id}")

        elif tool_name == "create_folder":
            folder_id = data.get("folder_id", "")
            if self._is_valid_uuid(folder_id):
                agent_state['last_node_id'] = folder_id
                agent_state['created_folder_id'] = folder_id
                logger.info(f"State actualizat: created_folder_id={folder_id}")

        # Fallback general: caută orice UUID în text dacă state e încă gol
        if 'last_node_id' not in agent_state:
            uuid_found = self._extract_uuid_from_text(observation_text)
            if uuid_found:
                agent_state['last_node_id'] = uuid_found
                logger.info(f"State (fallback regex): last_node_id={uuid_found}")

    def _build_tools_description(self, allowed_tools: Optional[List[str]] = None) -> str:
        """Construiește descrierea tool-urilor, filtrate după allowed_tools dacă e furnizat."""
        desc = ""
        for tool_name, tool_info in self.mcp_tools.items():
            if allowed_tools and tool_name not in allowed_tools:
                continue
            tool_desc = tool_info.get("description", "Fără descriere")
            schema = tool_info.get("inputSchema", {})
            props = schema.get("properties", {})
            required = schema.get("required", [])
            params = []
            for p_name, p_schema in props.items():
                req = "*" if p_name in required else ""
                p_type = p_schema.get("type", "string")
                params.append(f"{p_name}{req}({p_type})")
            desc += f"- **{tool_name}**: {tool_desc}\n"
            if params:
                desc += f"  Parametri (* = obligatoriu): {', '.join(params)}\n"
        return desc

    def _build_state_context(self, agent_state: dict) -> str:
        """Construiește secțiunea de state pentru prompt cu valorile REALE."""
        if not agent_state:
            return ""
        lines = ["**State curent (valori REALE din tool-uri — copiază-le EXACT în arguments):**"]
        for k, v in agent_state.items():
            if k == "all_items":
                preview = v[:3] if isinstance(v, list) else v
                lines.append(f"  - {k}: {json.dumps(preview, ensure_ascii=False)} ...")
            elif k == "current_node_info":
                # Afișează doar câmpurile esențiale
                if isinstance(v, dict):
                    essential = {kk: vv for kk, vv in v.items()
                                 if kk in ('id', 'name', 'type', 'nodeType', 'parentId')}
                    lines.append(f"  - {k}: {json.dumps(essential, ensure_ascii=False)}")
                else:
                    lines.append(f"  - {k}: {v}")
            else:
                lines.append(f"  - {k}: `{v}`")
        lines.append(
            "**IMPORTANT: Când ai nevoie de node_id, folosește valorile de mai sus EXACT, "
            "nu inventa placeholder-uri descriptive!**"
        )
        return "\n".join(lines)

    def _parse_llm_json(self, raw: str) -> Optional[dict]:
        """Parsează JSON din răspunsul LLM, tolerant la markdown fences."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None


    async def analyze_intent_and_call_tools_async(
        self, 
        user_input: str,
        alfresco_username: Optional[str] = None,
        alfresco_password: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> str:
        """
        Agent ReAct async — fiecare tool call e decis DUPĂ observarea
        rezultatului celui precedent.

        Înlocuiește arhitectura 'pipeline' care cauzează placeholder-uri:
        în pipeline, LLM-ul scria argumentele pentru toți pașii simultan,
        înainte să știe UUID-urile reale. Acum, fiecare pas e decis separat.
        """
        if not self.mcp_connected or not self.mcp_tools:
            return "ℹ️ Nu sunt conectat la serverul MCP HTTP sau nu sunt tool-uri disponibile."

        max_steps = 8
        agent_scratchpad = ""   # Istoricul vizibil pentru LLM (Thought/Action/Observation)
        agent_state = {}        # UUID-uri și date reale extrase din rezultate

        effective_tools = {
            name: info for name, info in self.mcp_tools.items()
            if allowed_tools is None or name in allowed_tools
        }

        if not effective_tools:
            return "ℹ️ Nu aveți permisiuni pentru tool-urile necesare acestei operațiuni."

        tools_description = self._build_tools_description(allowed_tools)

        for step in range(max_steps):

            state_context = self._build_state_context(agent_state)

            prompt = f"""Ești un agent AI care rezolvă cereri Alfresco pas cu pas folosind tool-uri MCP.

**Tool-uri disponibile:**
{tools_description}

**Cererea utilizatorului:**
{user_input}

**Istoric execuție (pași anteriori):**
{agent_scratchpad if agent_scratchpad else "Niciun pas executat încă."}

{state_context}

**Instrucțiuni CRITICE:**
1. Decide UN SINGUR pas următor bazat pe ce s-a executat deja și ce mai rămâne de făcut
2. Dacă ai nevoie de un node_id, verifică secțiunea "State curent" și folosește valoarea EXACTĂ de acolo
3. NU inventa UUID-uri sau placeholder-uri descriptive (ex: "id-ul-folderului", "ID-ul_primit") — acestea cauzează erori 404
4. Dacă task-ul e complet (ai toate informațiile cerute), returnează final_answer cu un răspuns detaliat

Răspunde DOAR cu JSON valid, fără text în afara JSON-ului:

Pentru a apela un tool:
{{"action": "call_tool", "tool_name": "nume_tool", "arguments": {{}}, "reasoning": "de ce apelezi acest tool acum"}}

Când ai terminat și ai toate informațiile:
{{"action": "final_answer", "answer": "răspunsul complet și detaliat pentru utilizator"}}
"""

            raw = self.query_llm_with_retry(prompt, max_tokens=400)
            analysis = self._parse_llm_json(raw)

            if analysis is None:
                logger.warning(f"Step {step + 1}: JSON invalid din LLM: {raw[:200]}")
                agent_scratchpad += f"\nStep {step + 1}: Eroare parsare răspuns LLM.\n"
                continue

            if analysis.get("action") is None:
                logger.info("Agent finished reasoning.")
                break

            if analysis.get("action") == "final_answer":
                answer = analysis.get("answer", "")
                if answer:
                    return answer
                logger.warning("final_answer fără conținut, continui...")
                continue

            if analysis.get("action") == "call_tool":
                tool_name = analysis.get("tool_name", "")
                arguments = analysis.get("arguments", {})
                reasoning = analysis.get("reasoning", "")

                # Verifică dacă tool-ul există și e permis
                if tool_name not in effective_tools:
                    if tool_name in self.mcp_tools:
                        agent_scratchpad += (
                            f"\nStep {step + 1}: Tool '{tool_name}' există dar "
                            f"nu este permis pentru rolul tău.\n"
                        )
                    else:
                        agent_scratchpad += f"\nStep {step + 1}: Tool '{tool_name}' inexistent.\n"
                    continue

                # CRITICAL FIX: înlocuiește placeholder-urile cu UUID-uri reale din state
                arguments = self._resolve_placeholders(arguments, agent_state)

                # Validare finală: dacă node_id e necesar și tot nu e valid, abortăm pasul
                if "node_id" in arguments and not self._is_valid_uuid(arguments["node_id"]):
                    node_ids_in_state = {
                        k: v for k, v in agent_state.items()
                        if 'id' in k.lower() and self._is_valid_uuid(str(v))
                    }
                    agent_scratchpad += f"""
Step {step + 1} - Tool: {tool_name}
Reasoning: {reasoning}
EROARE: node_id '{arguments["node_id"]}' nu este UUID valid și nu există fallback în state.
UUID-uri disponibile în state: {json.dumps(node_ids_in_state, ensure_ascii=False)}
HINT: Apelează mai întâi list_root_children sau get_node_id_by_name pentru a obține un UUID real.
"""
                    continue

                logger.info(
                    f"Step {step + 1}/{max_steps}: {tool_name}("
                    f"{json.dumps(arguments, ensure_ascii=False)})"
                )

                # Execută tool-ul
                raw_result = await self.call_mcp_tool_http(
                    tool_name=tool_name,
                    arguments=arguments,
                    alfresco_username=alfresco_username,
                    alfresco_password=alfresco_password,
                )

                # Formatează observația pentru scratchpad
                observation_text = self.format_tool_result(tool_name, raw_result)

                # Actualizează state cu datele reale din rezultat
                self._update_agent_state(agent_state, tool_name, raw_result, observation_text)

                # Adaugă în scratchpad pentru LLM
                agent_scratchpad += f"""
Step {step + 1} - Tool: {tool_name}
Reasoning: {reasoning}
Arguments: {json.dumps(arguments, ensure_ascii=False)}
Observation:
{observation_text[:3000]}{"...[trunchiat]" if len(observation_text) > 3000 else ""}
"""
                continue

            # Action necunoscută
            logger.warning(f"Step {step + 1}: Action necunoscută '{analysis.get('action')}'")
            agent_scratchpad += f"\nStep {step + 1}: Action necunoscută '{analysis.get('action')}'.\n"

        # Limita de pași atinsă — returnează ce am colectat
        if agent_state:
            # Filtrează all_items și current_node_info pentru un output mai curat
            summary = {k: v for k, v in agent_state.items()
                       if k not in ('all_items', 'current_node_info')}
            if 'current_node_info' in agent_state:
                summary['node_info'] = agent_state['current_node_info']
            return (
                f"Am executat operațiunile cerute (limita de {max_steps} pași atinsă).\n"
                f"Date colectate:\n{json.dumps(summary, indent=2, ensure_ascii=False)}"
            )

        return f"⚠️ Limita de {max_steps} pași atinsă fără rezultat final."

    def query_llm_with_retry(self, prompt: str, max_tokens: int = 400, retries: int = 3) -> str:
        """Interogează LLM cu retry logic și exponential backoff."""
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
        """O singură interogare LLM — funcție sincronă."""
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

    def create_enhanced_prompt(
        self, 
        user_input: str, 
        tool_results: str = "",
        user_role: Optional[str] = None,
        alfresco_username: Optional[str] = None,
    ) -> str:
        """Creează prompt îmbunătățit cu rezultate de la tool-uri MCP."""
        context_str = ""
        if self.session_context:
            recent_context = self.session_context[-3:]
            context_str = "\nContext anterior:\n"
            for ctx in recent_context:
                context_str += f"User: {ctx['user']}\nAI: {ctx['ai']}\n"

        tools_info = ""
        if self.mcp_tools:
            tools_info = "\nTool-uri MCP disponibile:\n"
            for tool_name, tool_info in self.mcp_tools.items():
                desc = tool_info.get('description', 'Fără descriere')
                schema = tool_info.get('inputSchema', {})
                props = schema.get('properties', {})
                params = list(props.keys()) if props else []
                tools_info += f"- {tool_name}: {desc}\n"
                if params:
                    tools_info += f"  Parametri: {', '.join(params)}\n"

        connection_info = (
            f"Conexiune MCP: {'✅ Conectat via HTTP' if self.mcp_connected else '❌ Deconectat'}"
        )

        tool_results_str = ""
        if tool_results and isinstance(tool_results, str) and tool_results.strip():
            tool_results_str = f"\nRezultate operațiuni MCP:\n{tool_results}\n"

        role_info = ""
        if user_role:
            role_info = f"\nRolul utilizatorului curent: {user_role}"
            if alfresco_username:
                role_info += f" (cont Alfresco: {alfresco_username})"

        system_prompt = f"""=== CONTEXT SYSTEM ===

Ești un asistent AI expert în Alfresco Document Management System cu acces la tool-uri MCP prin HTTP.

Server MCP: {self.mcp_server_url}
Model: {self.provider.upper()} - {self.model}
{connection_info}
{role_info}
{tools_info}
{context_str}
{tool_results_str}

=== INSTRUCȚIUNI ===
- Dacă ai rezultate de la tool-uri MCP, prezintă-le clar și structurat utilizatorului
- Explică ce operațiuni au fost efectuate și ce s-a găsit
- Dacă au apărut erori, explică ce s-a întâmplat și ce ar putea fi cauza
- Răspunde concis și profesional în limba română
- Nu repeta inutil informațiile din context

=== CERERE UTILIZATOR ===
{user_input}

=== RĂSPUNS ===
"""
        return system_prompt

    async def handle_user_input_async(self, user_input: str):
        """Handler async pentru input-ul utilizatorului."""
        try:
            print(f"🤖 {self.provider.title()} (procesez cu MCP HTTP...)")
            start_time = time.time()

            # ReAct agent — returnează string cu rezultatele complete
            tool_results = await self.analyze_intent_and_call_tools_async(user_input)

            # Creează prompt îmbunătățit pentru răspunsul final
            enhanced_prompt = self.create_enhanced_prompt(user_input, tool_results)

            # Obține răspunsul final de la LLM
            response = self.query_llm_with_retry(enhanced_prompt, max_tokens=500)

            processing_time = time.time() - start_time
            print(f"🤖 {self.provider.title()} ({processing_time:.1f}s):")

            if tool_results and "ℹ️ Cererea nu necesită" not in tool_results:
                print(f"   🔧 Tool results: {tool_results[:150]}...")

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
            import traceback
            traceback.print_exc()

    async def interactive_session_http_async(self):
        """Sesiune interactivă ASYNC cu server MCP prin HTTP."""
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

                await self.handle_user_input_async(user_input)

            except KeyboardInterrupt:
                print("\n🛑 Întrerupt de utilizator")
                break
            except Exception as e:
                print(f"\n❌ Eroare în sesiune HTTP: {e}")

        self.running = False
        print(f"\n✅ Sesiune HTTP {self.provider} închisă!")

    async def _get_user_input_async(self) -> str:
        """Obține input de la utilizator în mod async."""
        def get_input():
            try:
                return input("\n🔤 Tu: ").strip()
            except (EOFError, KeyboardInterrupt):
                return "quit"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_input)

    async def cleanup_http(self):
        """Curăță resursele HTTP."""
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