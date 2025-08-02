import pytest
import pytest_asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Clase.MinimalAlfrescoServer import MinimalAlfrescoServer
from httpx import Response
from unittest.mock import MagicMock, AsyncMock, patch

@pytest_asyncio.fixture
async def server():
    srv = MinimalAlfrescoServer("http://localhost:8080", "admin", "admin")
    srv.client = AsyncMock()
    return srv

@pytest.mark.asyncio
async def test_list_root_children(server):

    # Mock response
    mock_response = {
        "list": {
            "entries": [{
                "entry": {
                    "id": "123",
                    "name": "TestFolder",
                    "isFolder": True,
                    "nodeType": "cm:folder",
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "modifiedAt": "2024-01-02T00:00:00.000Z",
                    "createdByUser": {"displayName": "Admin"},
                    "modifiedByUser": {"displayName": "Admin"},
                    "path": {"name": "/Company Home/TestFolder"}
                }
            }]
        }
    }

    # Mock complet pentru răspunsul HTTP
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=mock_response)

    # Injectăm răspunsul mock
    server.client.get = AsyncMock(return_value=response)

    result = await server.list_root_children()
    assert result["total"] == 1
    assert result["items"][0]["name"] == "TestFolder"
    assert "message" in result

@pytest.mark.asyncio
async def test_format_simple_response(server):

    raw = {
        "message": "Test Response",
        "items": [{"name": "FolderA", "type": "folder", "id": "id-001"}]
    }

    formatted = server.format_simple_response(raw, "context_test")
    assert formatted["summary"] == "Test Response"
    assert "- FolderA [folder] (ID: id-001)" in formatted["items"][0]