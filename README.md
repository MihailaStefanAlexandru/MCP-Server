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
| Integrare mai ușoară cu OpenWebUI sau cu alte aplicații care folosesc HTTP | Izolare ceea ce contribuie la securitate |
| Testare și Debugging mai simple | Performanță mai bună deoarece nu avem overhead de rețea |
| Scalabilitate, se poate adauga autentificare, logging centralizat | Bun pentru testare și integrare în sisteme CLI |

#### Serverul

Pentru implementarea protocolului este necesară prezența a două entități. Acestea sunt serverul și clientul.

Serverul este puntea de legătură dintre sistemul de gestiune al fișierelor (sau o altă construcție cu totul) și client. El trebuie să expună instrumentele utilizabile către client astfel încât llm-ul să poată ști ce are la dispoziție pentru a îndeplini cerințele user-ului.

Tool-urile sunt definite conform documnetației astfel:

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

## Instalare și Configurare

## Ghid de utilizare

## Testare

## Test prompts

Exemplele de testare au fost mutate în fișierul Test-prompts.md pentru a nu încărca fișierul de documentație.

## Resurse

