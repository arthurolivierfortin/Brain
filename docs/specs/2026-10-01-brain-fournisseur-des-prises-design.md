# Brain comme fournisseur des prises du cockpit

Date : 2026-10-01. Décision d'Arthur : Brain reprend, en gardant la version existante, comme mémoire épisodique du cockpit et fournisseur de ses prises de hooks. Référence : cockpit `docs/superpowers/specs/2026-09-21-cockpit-architecture-design.md`, §1 (frontière), §7 (prises), §11 (frontière et pont, amendé ce jour).

## 1. Ce que Brain est, et n'est pas

- **Brain répond à « qu'est-ce que je me rappelle avoir vécu et appris ? »** : décisions reçues, erreurs, reprises et leurs causes, leçons vécues, préférences, consignes données en cours de session. Daté, par session et par projet, avec décroissance et renforcement à l'usage.
- **Le KB de dev-kit répond à « comment cette chose fonctionne-t-elle ? »** : faits durables sur les systèmes, en markdown dans git, consolidés par `/dream`.
- Test de placement : daté et vécu, Brain ; vrai indépendamment de la session, KB.
- Brain ne devient jamais l'index sémantique du KB ni une base de connaissances parcourable (surface MemPalace retirée, cockpit §11). Ses niveaux L0 à L3 (brut, résumé, connaissance, principe) ne changent pas.
- Ce qui est gardé tel quel : backend FastAPI, serveur MCP et ses cinq outils, ChromaDB avec `fastembed`, extraction par Gemini Flash, hooks de réveil et de capture, moniteur. Rien n'est réécrit ; les données d'avril restent ; le cockpit écrit dans un espace à lui.

## 2. Les prises et leur contrat

Le cockpit possède le câblage des quatre prises (cockpit §7). Chaque prise a un contrat de fournisseur : entrée, sortie, délai maximal, et comportement quand le fournisseur est absent ou en panne (la session continue toujours). Le KB sert les prises par scripts ; Brain en devient un fournisseur par appel HTTP local. Le remplacement d'un fournisseur ne change aucune fiche d'agent.

| Prise | Événement | Fournisseur script (B1) | Fournisseur Brain (B2) |
|---|---|---|---|
| Réveil | `SessionStart` (démarrage, reprise, **compaction**) | condensé de session écrit avant compaction (dev-kit #224) | contexte épisodique L0/L1 de la session et du projet, borné en tokens |
| Par prompt | `UserPromptSubmit` | `kb-search` lexical | rappel des souvenirs liés au prompt, après le KB, borné |
| Capture | `Stop`, `PreCompact` | condensé (décisions, questions, consignes) dans l'état de boucle | extraction par tour depuis le delta de transcript, derrière la porte anti-secrets |
| Usage | `PostToolUse` Read/Grep/Glob | journal `.usage.jsonl` du KB | compteurs de rappel et de renforcement de Brain |

## 3. Porte anti-secrets

Aucune capture par tour n'est activée tant que la porte n'est pas prouvée par test : refus de tout fragment ressemblant à une clé, un jeton, un mot de passe ou une variable d'environnement sensible (noms et motifs déclarés dans dev-kit), refus des contenus lus sous `.env*`, et journal de refus sans la valeur. La porte est côté cockpit, avant l'appel à Brain ; Brain n'a pas à la connaître. Le `gate.py` historique de Brain n'est pas réutilisé (cockpit §7).

## 4. Pont vers le KB, sans dépendance

Brain expose un **adaptateur d'export générique** : « exporter les souvenirs promus au niveau connaissance vers un dossier, avec un gabarit de frontmatter configurable ». Le cockpit le configure vers `kb/inbox/brain/` avec le gabarit de l'inbox du KB. Brain ne connaît ni le mot KB ni sa structure ; le KB ne sait pas que Brain existe et trie ce dépôt comme n'importe quel autre fichier d'inbox. Si le dossier manque, Brain tourne ; si Brain est éteint, le KB tourne. Le KB n'écrit jamais dans Brain ; ni le pilote ni la boucle ne cherchent dans Brain un fait qui devrait être au KB.

## 5. Paliers

| Palier | Contenu | Critère de sortie | Semaine visée |
|---|---|---|---|
| B0 · Il tourne | #13 corrigée, service en Docker sous son nom, gates verts, fumée des cinq outils (#43) | `docker compose ps` sain, 3 gates verts, fumée 5/5 sans secret | 6 octobre |
| B1 · Prises servies par scripts | dev-kit #224 et contrat de prise écrit | une session compactée retrouve une décision enregistrée ; un fournisseur se remplace sans toucher aux fiches | 6 octobre |
| B2 · Brain fournit les prises du pilote (**MVP**) | réveil et capture du pilote par Brain, porte anti-secrets, export vers l'inbox | après compaction, le pilote retrouve ses décisions depuis Brain ; la porte refuse une clé en test ; un souvenir promu arrive dans l'inbox | 13 octobre |
| B3 · Sessions enfants et première mesure | capture des reprises, causes de rejet et décisions des boucles | chaque reprise a une cause dans Brain ; le bilan cite un rappel qui a évité une erreur répétée ; `brain_version` renseigné (dev-kit #223) | 20 octobre, mesuré au bilan suivant |

Le pilote d'abord, en B2 : c'est sa mémoire qui a lâché le 2026-10-01 après compaction, et c'est le seul consommateur dont l'effet se juge sans bruit.

## 6. Gestes d'Arthur

Jamais faits par un agent, demandés au moment voulu : démarrer Docker Desktop ; poser la clé de l'extracteur dans l'environnement de Brain à la main ; décider en fin de B3 si Brain s'étend aux sessions de tous les projets.

## 7. Décisions figées

1. Version existante conservée ; aucune réécriture ; données d'avril intactes.
2. Frontière Brain/KB du cockpit §1 et §11 ; export générique à la place d'un pont qui connaît le KB.
3. Porte anti-secrets côté cockpit, prouvée avant toute capture par tour.
4. Ordre B0, B1, B2, B3 ; MVP = B2 ; pilote avant sessions enfants.
5. Mesure par la télémétrie de dev-kit (`brain_version` par tâche, #223) ; pas de métrique propre à Brain avant B3.
