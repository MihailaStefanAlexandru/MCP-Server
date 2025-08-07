import pytest
from unittest.mock import AsyncMock, Mock
from fastapi.testclient import TestClient
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Clase.HttpServer import HTTPAlfrescoMCPServer
from mcp.types import TextContent

@pytest.fixture
def mock_alfresco_server():

    mock_server = Mock()
    mock_tool_handler = AsyncMock()
    mock_tool_handler.__doc__ = "Mock_tool_description"

    mock_mcp_server = Mock()
    mock_mcp_server._tools = {
        "mock_tool": mock_tool_handler
    }

    mock_server.get_server.return_value = mock_mcp_server
    return mock_server

@pytest.fixture
def http_server(mock_alfresco_server):

    server = HTTPAlfrescoMCPServer("http://fake-url", "admin", "admin")
    server.alfresco_server = mock_alfresco_server
    server.initialized = True
    
    return server

@pytest.mark.asyncio
async def test_tools_list(http_server):

    client = TestClient(http_server.app)
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/list"
    })

    assert response.status_code == 200
    json_data = response.json()
    tools = json_data["result"]["tools"]
    assert isinstance(tools, list)
    assert tools[0]["name"] == "mock_tool"
    assert tools[0]["description"] == "Mock_tool_description"

@pytest.mark.asyncio
async def test_tools_call(http_server):

    mock_tool_handler = AsyncMock(return_value=[
        {
            "type": "text",
            "text": "success",
            "annotations": None,
            "_meta": None
        }
    ])

    mock_mcp_server = Mock()
    mock_mcp_server._tools = {
        "mock_tool": mock_tool_handler
    }

    http_server.alfresco_server.get_server.return_value = mock_mcp_server

    client = TestClient(http_server.app)
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": "42",
        "method": "tools/calls",
        "params": {
            "name": "mock_tool",
            "arguments": {}
        }
    })

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "content" in data["result"]
    print(data["result"]["content"][0]["text"])
    assert data["result"]["content"][0]["text"] == "success"
    mock_tool_handler.assert_awaited_once()