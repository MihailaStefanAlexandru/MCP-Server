import json
import uuid
import pytest
import respx
import httpx
import asyncio
import time
import types

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Clase.MCPHTTPClient import MCPHTTPCLient

@pytest.fixture()
def temp_config(tmp_path):

    cfg = {
        "llm": {
            "provider": "openai",
            "api_key": "test",
            "model": "gpt-test"
        },
        "mcp": {
            "server_url": "http://localhost:8002",
            "server_config": {}
        }
    }

    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return str(p)

@pytest.fixture()
def client(temp_config, monkeypatch):

    # Inlocuieşte iniţializarea reală cu OpenAi
    monkeypatch.setattr(MCPHTTPCLient, "_init_llm_client", lambda self: None)
    c = MCPHTTPCLient(temp_config)
    return c

@respx.mock
@pytest.mark.asyncio
async def test_check_server_health_ok(client):

    respx.get("http://localhost:8002/health").mock(return_value=httpx.Response(200))
    ok = await client.check_server_health()
    
    assert ok is True

@respx.mock
@pytest.mark.asyncio
async def test_check_server_health_fail(client):

    respx.get("http://localhost:8002/health").mock(return_value=httpx.Response(503))
    ok = await client.check_server_health()

    assert ok is False

@respx.mock
@pytest.mark.asyncio
async def test_initialize_mcp_http_protocol_succes(client):

    # initialize
    respx.post("http://localhost:8002/mcp").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": str(uuid.uuid4()), "result": {"capabilities": {}}})
    )

    # notify
    respx.post("http://localhost:8002/mcp/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    # tools/list
    tools_payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "result": {
            "tools": [
                {
                    "name": "list_nodes",
                    "description": "Listare noduri",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"}
                        }
                    },
                },
                {
                    "name": "create_folder",
                    "description": "Creeaza folder",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"}
                        }
                    },
                },
            ]
        },
    }

    respx.post("http://localhost:8002/mcp").mock(return_value=httpx.Response(200, json=tools_payload))

    ok = await client.initialize_mcp_http_protocol()
    assert ok is True
    assert client.mcp_connected is True
    assert set(client.mcp_tools.keys()) == {"list_nodes", "create_folder"}

@respx.mock
@pytest.mark.asyncio
async def test_initialize_mcp_http_protocol_error(client):

    # initialize fără result
    respx.post("http://localhost:8002/mcp").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": str(uuid.uuid4()), "error": {"code": -32601}})
    )
    ok = await client.initialize_mcp_http_protocol()
    assert ok is False
    assert client.mcp_connected is False

@respx.mock
@pytest.mark.asyncio
async def test_call_mcp_tool_http_not_connected(client):

    client.mcp_tools = {"list_nodes": {}}
    client.mcp_connected = False
    resp = await client.call_mcp_tool_http("list_nodes", {"path": "/"})
    assert resp["error"].startswith("Nu sunt conectat")

@respx.mock
@pytest.mark.asyncio
async def test_call_mcp_tool_http_missing(client):

    client.mcp_tools = {}
    client.mcp_connected = True
    resp = await client.call_mcp_tool_http("list_nodes", {"path": "/"})
    assert resp["error"].startswith("Tool-ul 'list_nodes'")

@respx.mock
@pytest.mark.asyncio
async def test_call_mcp_tool_http_succes(client):

    client.mcp_connected = True
    client.mcp_tools = {"list_nodes": {"name": "list_nodes"}}

    result_payload={
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": "/Company Home, /Sites"
                }
            ]
        },
    }

    respx.post("http://localhost:8002/mcp").mock(return_value=httpx.Response(200, json=result_payload))

    resp = await client.call_mcp_tool_http("list_nodes", {"path": "/"})
    assert "content" in resp
    assert resp["content"][0]["text"].startswith("/Company Home")

@respx.mock
@pytest.mark.asyncio
async def test_call_mcp_tool_http_server_error(client):

    client.mcp_connected = True
    client.mcp_tools = {"list_nodes": {"name": "list_nodes"}}

    error_payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "error": {
            "code": -32000,
            "message": "Internal error"
        },
    }
    respx.post("http://localhost:8002/mcp").mock(return_value=httpx.Response(200, json=error_payload))

    resp = await client.call_mcp_tool_http("list_nodes", {"path": "/"})
    assert resp["error"].startswith("Eroare server:")

@respx.mock
@pytest.mark.asyncio
async def test_analyze_intent_and_call_tools(client, monkeypatch):

    client.mcp_connected = True
    client.mcp_tools = {
        "list_nodes": {
            "name": "list_nodes",
            "description": "",
            "inputSchema": {
                "properties": {
                    "path": {}
                }
            }
        }
    }

    # llm-ul decide ce tool foloseste
    llm_json = json.dumps({
        "action": "call_tool",
        "tool_name": "list_nodes",
        "arguments": {"path": "/"},
        "explanation": "listare radacina"
    })

    monkeypatch.setattr(client, "query_llm_with_retry", lambda *a, **k: llm_json)

    # Mock rapsuns
    respx.post("http://localhost:8002/mcp").mock(
        return_value=httpx.Response(200, json={
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "result": {
                "content": [{
                    "type": "text",
                    "text": "OK"
                }]
            }
        })
    )

    res = await client._analyze_intent_and_call_tools_async("listeaza nodurile din root")
    assert res.startswith("🔧 Rezultat list_nodes:\nOK")

@pytest.mark.asyncio
async def test_analyze_intent_and_call_tools_no_tool(client, monkeypatch):

    client.mcp_connected = True
    client.mcp_tools = {"list_nodes": {"name": "list_nodes"}}
    monkeypatch.setattr(client, "query_llm_with_retry", lambda *a, **k: json.dumps({"action": "no_tool", "explanation": "n/a"}))

    out = await client._analyze_intent_and_call_tools_async("spune un salut")
    assert out == "ℹ️ Cererea nu necesită apelarea unui tool MCP specific."


@pytest.mark.asyncio
async def test_analyze_intent_missing_connection_or_tools(client):

    client.mcp_connected = False
    client.mcp_tools = {}
    out = await client._analyze_intent_and_call_tools_async("orice")
    assert out.startswith("ℹ️ Nu sunt conectat la serverul MCP HTTP")

@pytest.mark.asyncio
async def test__query_llm_single_openai(client, monkeypatch):

    client.provider = "openai"
    client.model = "gpt-3.5-turbo"

    mock_openai = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(
                create=lambda **kwargs: types.SimpleNamespace(
                    choices=[
                        types.SimpleNamespace(
                            message=types.SimpleNamespace(content=" răspuns ")
                        )
                    ]
                )
            )
        )
    )

    client.openai_client = mock_openai
    result = client._query_llm_single("test prompt", 200)
    assert result == "răspuns"

def test_query_llm_with_retry_success(client):

    client.provider = "openai"
    client._query_llm_single = lambda *a, **k: "OK"

    result = client.query_llm_with_retry("prompt", retries=3)
    assert result == "OK"

def test_query_llm_with_retry_fail(client, monkeypatch):

    client.provider = "openai"
    client._query_llm_single = lambda *a, **k: (_ for _ in ()).throw(Exception("fail"))

    monkeypatch.setattr(time, "sleep", lambda x: None)

    result = client.query_llm_with_retry("prompt", retries=2)
    assert "Nu pot accesa" in result

def test_create_enhanced_prompt_with_context_and_tools(client):

    client.session_context = [
        {"user": "u1", "ai": "a1"},
        {"user": "u2", "ai": "a2"},
    ]

    client.mcp_tools = {"tool1": {}, "tool2": {}}
    client.mcp_connected = True
    client.provider = "openai"
    client.model = "gpt-3.5-turbo"
    client.mcp_server_url = "http://mcp"

    result = client.create_enhanced_prompt("Ce faci?", "Rezultat tool")
    assert "Context anterior" in result
    assert "tool1" in result
    assert "Rezultat tool" in result
    assert "Ce faci?" in result

@pytest.mark.asyncio
async def test_test_mcp_connection_http_success(client):

    client.mcp_connected = True

    async def always_true():
        return True
    
    async def dummy_http_200(url):
        return types.SimpleNamespace(status_code=200)
    
    client.check_server_health = always_true
    client.http_client = types.SimpleNamespace(get=dummy_http_200)
    client.mcp_server_url = "http://test"

    result = await client.test_mcp_connection_http()
    assert result is True

@pytest.mark.asyncio
async def test_test_mcp_connection_http_fail_health(client):

    client.mcp_connected = True

    async def always_false():
        return False
    
    client.check_server_health = always_false

    async def dummy_http_none(url):
        return None
    
    client.http_client = types.SimpleNamespace(get=dummy_http_none)
    client.mcp_server_url = "http://test"

    result = await client.test_mcp_connection_http()
    assert result is False

@pytest.mark.asyncio
async def test_test_mcp_connection_http_fail_status(client):

    client.mcp_connected = True

    async def always_true():
        return True
    
    async def dummy_http_500(url):
        return types.SimpleNamespace(status_code=500)
    
    client.check_server_health = always_true
    client.http_client = types.SimpleNamespace(get=dummy_http_500)
    client.mcp_server_url = "http://test"

    result = await client.test_mcp_connection_http()
    assert result is False

@pytest.mark.asyncio
async def test_cleanup_http(client):

    client.running = True
    client.mcp_connected = True
    async def dummy_aclose():
        return None
    client.http_client = types.SimpleNamespace(aclose=dummy_aclose)
    client.mcp_tools = {"a": 1}
    client.mcp_resources = {"b": 2}
    client.mcp_prompts = {"c": 3}

    await client.cleanup_http()

    assert client.running is False
    assert client.mcp_connected is False
    assert client.mcp_tools == {}
    assert client.mcp_resources == {}
    assert client.mcp_prompts == {}

def test_del_calls_cleanup_without_warning(client, monkeypatch):
    """Verificăm că __del__ nu dă warning și apelează cleanup"""

    called = {}
    async def fake_cleanup():
        called["done"] = True
   
    client.cleanup_http = fake_cleanup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client.__del__()

    # execută task-ul creat
    loop.run_until_complete(asyncio.sleep(0))
    assert "done" in called
    loop.close()