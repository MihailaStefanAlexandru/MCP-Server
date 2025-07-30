# MCP-Server

## Testare pentru Claude Desktop

1. Listare conținut root

Listează toate fișierele și folderele din root-ul Alfresco.

2. Creare folder nou

Creează un folder numit "TestFolder" în root.

SAU

Creează un folder numit "TestFolder" cu titlul "Exemplu MCP" și descrierea "Folder creat pentru testare", în directorul root.

3. Listare copii ai unui nod

Arată conținutul folderului cu ID-ul [copiat din rezultatul anterior].

4. Informații despre un nod

Afișează toate informațiile disponibile despre nodul cu ID-ul [id-ul folderului TestFolder].

5. Ștergere logică

Șterge folderul cu ID-ul [id-ul folderului] și trimite-l în coșul de gunoi.

6. Ștergere permanentă

Șterge definitiv nodul cu ID-ul [id-ul folderului].

7. Navigare după path

Navighează la calea /Company Home/Documente.

## Pornire imagine docker openwebui

docker run -d \
  -p 3000:3000 \
  -v openwebui-data:/app/backend/data \
  -e PORT=3000 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8001/v1 \
  -e OPENAI_API_KEY=sk-anything \
  -e WEBUI_SECRET_KEY=your-secret-key \
  --add-host=host.docker.internal:host-gateway \
  --name openwebui \
  ghcr.io/open-webui/open-webui:main

## Adaugare model in openwebui

OpenAI API \
API Base URL: http://localhost:8001/v1 \
API Key: sk-any-key (orice string, nu e validat)

## Schemă Bloc software

![Schema_Bloc](Schema_bloc.svg)

system prompt
context pentru functii

system_prompt = {
            "role": "system",
            "content": (
                "You are an assistant with access to MCP filesystem tools. "
                "For any filesystem-related request (e.g., listing files, reading files, writing files, creating directories, etc.), "
                "immediately select and use the appropriate MCP filesystem tool based on the request's intent. "
                "Available tools include: list_directory_mcp_filesystem, read_file_mcp_filesystem, write_file_mcp_filesystem, "
                "edit_file_mcp_filesystem, create_directory_mcp_filesystem, list_directory_with_sizes_mcp_filesystem, "
                "directory_tree_mcp_filesystem, move_file_mcp_filesystem, search_files_mcp_filesystem, get_file_info_mcp_filesystem, "
                "list_allowed_directories_mcp_filesystem. "
                "Use the tool that best matches the request (e.g., list_directory_mcp_filesystem for listing files, read_file_mcp_filesystem for reading file contents). "
                "Do NOT generate descriptive text, explanations, or any content unless explicitly requested. "
                "Respond ONLY with the appropriate tool call."
            )
        }