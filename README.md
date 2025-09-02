# MCP

## MCP protocol

MCP este un protocol deschis care standardizează modul în care aplicațiile oferă context modelelor lingvistice mari (LLM). MCP este asemenea unui port USB-C pentru aplicații de inteligență artificială. Așa cum USB-C oferă o modalitate standardizată de a conecta dispozitivele la diverse periferice și accesorii, MCP oferă o modalitate standardizată de a conecta modelele de inteligență artificială la diferite surse de date și instrumente. MCP permite construcția de agenți și fluxuri de lucru complexe pe baza LLM-urilor și conectarea modelele cu lumea.

MCP oferă:

- O listă mare de integrări predefinite la care LLM-ul se poate conecta direct.
- O modalitate standard pentru a construi integrări personalizate pentru aplicațiile AI.
- Un protocol deschis pe care toată lumea îl poate implementa și folosi.
- Flexibilitatea de a schimba între diferite aplicații și de a lua contextul pentru utilizare.

MCP constă în două layere:

- Data Layer: definește protocolul bazat pe JSON-RPC pentru comunicarea client-server, incluzând managementul ciclului de viață, primitive esențiale, cum ar fi instrumente, resurse, prompt-uri și notificări.
- Transport Layer: definește mecanismul de comunicare și canalele care permit schimbul de date dintre client și server, incluzând și stabilizarea conexiunii specifice transportului, înrămarea mesajelor și autorizare.

## Arhitectura Proiectului

### Schema Bloc Software

![Schema_Bloc](Schema_Bloc.svg)

### Considerații teoretice de implementare utilizate

Comunicarea dintre server și client se poate efectua prin fluxuri standard (STDIO) și prin protocolul HTTP.

În această implementare a fost aleasă o abordare bazată pe protocolul HTTP întrucât cel mai adesea, pentru mulți utilizatori, serverul și clientul nu le sunt ambele accesibile, aceștia putând avea la dispoziție doar una din cele două componente care operează local.
Cu toate acestea a fost studiată și o implementare prin fluxuri standard.

| HTTP | STDIO |
| ---------- | --------- |
| Serverul poate rula pe altă mașină în cloud, containerizat | Comunicare în cadrul aceluiași proces |
| Integrare mai ușoară cu OpenWebUI sau cu alte aplicații care folosesc HTTP | Izolare mai bună, ceea ce crește securitatea |
| Testare și Debugging mai simple | Performanță bună(nu există overhead) |
| Scalabilitate, se poate adauga autentificare, logging centralizat | Bun pentru testare și integrare în sisteme CLI |

#### Serverul

Protocolul MCP presupune existența a două entități: serverul, care expune instrumente, și clientul, care le consumă prin intermediul unui LLM.

Serverul este puntea de legătură dintre sistemul de gestiune al fișierelor (sau o altă construcție cu totul) și client. El trebuie să expună instrumentele utilizabile către client astfel încât llm-ul să poată ști ce are la dispoziție pentru a îndeplini cerințele user-ului.

Tool-urile sunt definite conform specificației MCP, fiecare având un nume, o descriere și un schelet JSON-Schema pentru parametri:

(exemplu este implementarea tool-ului list_root_children)
```
Tool(
  name="list_root_children",
  description="Listează fișierele și folderele din root-ul Alfresco",
  inputSchema={
    "type": "object",
    "properties": {
    "maxItems": {
        "type": "integer",
        "description": "Numărul maxim de elemente de returnat (default: 20)",
        "default": 20
      }
    }
  }
)
```

Serverul are trei responsabilități principale:
- expune tool-urile disponibile către client.
- gestionează apelurile de la client și returnează răspunsurile în format MCP.
- asigură conectarea la sursa de date(în acest caz, Alfresco).

#### Clientul

Clientul asigură conexiunea dintre utilizator și LLM, astfel că utilizatorul poate vedea în timp real rezultatele furnizate de LLM și în funcție de aceste rezultate poate veni cu alte cerințe mai complexe care în cele din urmă se vor definitiva în ceea ce voia utilizatorul să facă.

De asemenea, system prompt-ul și function calling-ul se regăsesc aici, deoarece, în client, acestea sunt cât mai apropiate de LLM, ele find destinate cu precădere acestuia. Acestea au rolul de servi scopului final pentru care utilizatorul vrea să folosească LLM-ul.

System prompt-ul are definit rolul în care LLM-ul trebuie să se regăsească pentru a duce la îndeplinire sarcinile. Acesta conține și lista de tool-uri disponibile și modalitatea în care răspunsul trebuie să fie formulat pentru utilizator:

```
system_prompt = f"""=== CONTEXT SYSTEM ===
        
    Ești un asistent AI expert în Alfresco Document Management System cu acces la tool-uri MCP prin HTTP.

    Server MCP: {self.mcp_server_url}
    Model: {self.provider.upper()} - {self.model}
    {connection_info}

    Ai aceste informații despre tool-urile disponibile și modalitatea în care sunt ele folosite:
    {tools_info}

    Acesta este contextul curent:
    {context_str}

    Acestea sunt rezultatele anterioare returnate de tool-uri
    {tool_results_str}

    === INSTRUCȚIUNI ===
    - Dacă ai rezultate de la tool-uri MCP, folosește-le în răspuns
    - Respectă schema parametrilor din tool-uri; tipurile numerice trebuie să fie integer.
    - Dacă tool-ul nu este disponibil sau eșuează, explică utilizatorului.
    - Folosește contextul și rezultatele anterioare pentru a explica acțiunile.
    - Folosește tool-ul care se potrivește cât mai bine cu cererea.
    - Răspunde concis și profesional, fără a repeta inutil contextul.
    - Generează doar răspunsuri utile pentru cererea curentă, evitând textul suplimentar.
    - Nu încerca să apelezi tool-uri direct din acest prompt — asta se face separat prin analiza intenției.

    === CERERE UTILIZATOR ===
    {user_input}

    === RĂSPUNS ===
    """

        return system_prompt
```

Function calling-ul este utilizat pentru a-i furniza LLM-ului informații despre cum trebuie să apeleze tool-urile pe care le are la dispoziție. Adică trebuie să extrag din input-ul user-ului argumentele pentru a apela acele tool-uri care se potrivesc cu cerințele user-ului:

```
if action == "call_tool":
  tool_name = analysis.get('tool_name')
  arguments = analysis.get('arguments', {})
  explanation = analysis.get('explanation', '')

  if tool_name not in self.mcp_tools:
    return f"❌ Tool-ul '{tool_name}' nu este disponibil"

  print(f"🎯 Execut: {explanation}")
  tool_result = await self.call_mcp_tool_http(tool_name, arguments)
  formatted = self.format_tool_result(tool_name, tool_result)
  return f"📝 Explicație: {explanation}\n\n🔧 Rezultat {tool_name}:\n{formatted}"
```

Clientul nu implementează logica tool-urilor, ci doar apelează tool-urile expuse de server prin MCP și prezintă rezultatele utilizatorului.

#### Diagramă de flux

#### OpenWebUI

OpenWebUI a fost folosit pentru a oferi o interfata grafica în cadrul căreia să se expună într-un mod mai simplu de vizualizat pentru utilizator răspunsurile la cererile sale.

Rezultatele furnizate de către llm sunt trimise de către client la interfața OpenWebUI cu ajutorul protocolului http.

În cadrul OpenWebUI se găsește un model de ai care nu este nimic altceva decât LLM-ul menționat anterior doar că a fost creat un endpoint de legătură pentru a da impresia că acesta are acces direct la interfață. În cadrul acelui endpoint sunt expuse numele noului model și alte informații printre care și numele tool-urile expuse de server.

## Instalare și Configurare

Se deschide un virtual environment pentru python 3.12 în care se vor instala utilizând comanda `pip install --r requiremnets.txt` utilitarele necesare pentru rularea fișierelor.

## Ghid de utilizare

1. Se pornesc containerele docker pentru Alfresco folosind ` docker compose up -d`.

2. Se pornește serverul MCP: `./alfresco_mcp_server.py`

3. Se pornește adapter.py care permite deschiderea OpenWebUI și a clientului. `python3 adapter.py`

4. Se pornește imaginea de docker pentru OpenWebUI:

```
docker run -d   
  -p 3000:3000   
  -v openwebui-data:/app/backend/data   
  -e PORT=3000   
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8001/v1   
  -e OPENAI_API_KEY=sk-anything   
  -e WEBUI_SECRET_KEY=your-secret-key   
  --add-host=host.docker.internal:host-gateway   
  --name openwebui   
  ghcr.io/open-webui/open-webui:main
```

OpenWebUI se deschide la http://localhost:3000. În cazul în care se lucrează cu port fowarding atunci localhost se schimbă într-o adresă ip.

## Testare

## Test prompts

Exemplele de testare au fost mutate în fișierul Test-prompts.md pentru a nu încărca fișierul de documentație.

## Resurse

