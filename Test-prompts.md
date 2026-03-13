# Teste

| Tip test     | Ce verifică             |
| ------------ | ----------------------- |
| simple       | funcționarea toolurilor |
| chaining     | LLM tool reasoning      |
| state change | create/delete           |
| navigation   | path vs id              |
| robustness   | agent orchestration     |

## Task-uri simple

1. Listează primele 10 elemente din root-ul Alfresco.

2. Listează maxim 5 elemente din root.

3. Găsește ID-ul folderului Sites.

4. Găsește ID-ul folderului Shared.

5. Obține informațiile despre folderul Sites.

6. Obține informațiile despre folderul Shared.

## Task-uri cu două tool-uri

7. Găsește ID-ul folderului Sites și apoi listează conținutul acestuia.

8. Găsește ID-ul folderului Data Dictionary și extrage informațiile despre el.

9. Listează folderele din root și extrage informațiile despre primul folder găsit.

10. Listează folderele din root și extrage informațiile despre ultimul folder.

11. Găsește ID-ul folderului User Homes și listează conținutul acestuia.

12. Navighează la / folosind path și listează conținutul.

## Task-uri cu reasoning 3 tool-uri

13. Listează folderele din root, ia primul folder și extrage informațiile despre el.

14. Listează folderele din root, găsește ID-ul folderului Sites, apoi extrage informațiile despre el.

15. Navighează la root folosind path și extrage informațiile despre primul folder găsit.

16. Listează folderele din root și pentru fiecare afișează numele și ID-ul.

17. Listează folderele din root și extrage informațiile pentru primele două foldere.

## Task-uri create + verificare

18. Creează un folder numit TestFolder1 în root.

19. Creează un folder TestFolder2 și apoi extrage informațiile despre el.

20. Creează un folder DemoFolder și apoi listează conținutul root pentru a verifica că există.

21. Creează un folder AI-Experiment cu descriere.

22. Creează un folder ResearchNotes și apoi extrage ID-ul lui.

## Task-uri create + navigare

23. Creează un folder AgentTest, apoi extrage informațiile despre el.

24. Creează un folder ProjectData și apoi listează conținutul root.

25. Creează un folder Logs și verifică dacă există în root.

## Task-uri delete mai complexe

26. Găsește ID-ul folderului TestFolder1 și șterge-l.

27. Găsește ID-ul folderului TestFolder2 și șterge-l permanent.

28. Creează un folder TempFolder, apoi șterge-l.

## Task-uri mai complexe

29. Listează folderele din root, alege primul folder și extrage informațiile despre el.

30. Listează folderele din root, găsește ID-ul folderului Sites, apoi listează conținutul acestuia.
