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