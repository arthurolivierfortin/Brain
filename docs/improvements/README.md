---
status: open
owner: core
created: 2026-04-16
updated: 2026-04-19
---

# Improvements backlog

Dettes connues, tranchées au moment de l'extraction de Money. Ordre = priorité descendante.

## When to extract to its own file

If an item grows past ~10 lines, needs its own ADR reference, or gets actively worked on → extract to `docs/improvements/<slug>.md` and leave a one-line pointer here. Keep this file scannable in one screen.

## P0 — Types dynamiques (vrai cerveau)

**Actuellement** : `memory.py::MemoryType`, `gate.py::_NOISE_TYPES`, `gate.py::_SIGNIFICANT_TYPES`, `store.py::_OPPOSITE_SENTIMENTS`, `store.py::_DECAY_CONSTANTS`, `memory.py::DECAY_HALF_LIFE` sont des enums/frozensets hardcodés hérités de Money (trading-biased).

**Cible** : apprentissage dynamique.
- Types émergent de l'usage (clustering des memories stockées)
- Decay half-lives calibrés par observation (quand un type n'est plus consulté → half-life raccourci)
- Noise vs significant déduit du gradient d'accès réel, pas d'une règle a priori
- Contradictions détectées par embedding + validation LLM, pas par paires de sentiments hardcodées

**Pourquoi** : un vrai cerveau ne connaît pas les catégories à l'avance, il les découvre. Hardcoder = biais du domaine source (trading) + impossible à dropper-in dans un autre contexte sans réécrire le gate.

**Quand** : phase d'amélioration, après benchmarks et drop-in installer.

**Blocant pour quoi** : rien en phase 1. Les règles trading-specific du gate sont dormantes (inactives sans metadata trading). À nettoyer avant marketing public.

## P1 — Bi-temporal facts (volé de Graphiti)

**Actuellement** : `memory.py` a un `created_at` + `last_accessed` + decay par type, mais pas de validity windows (valid_from / valid_to).

**Cible** : chaque fact a deux axes temporels — event time (quand le fait est vrai dans le monde) + ingestion time (quand Brain l'a appris). Permet "qu'est-ce qui était vrai le 2025-11-01 ?".

**Quand** : après benchmarks. LongMemEval catégorie temporal reasoning est là où Zep bat mem0 (+15pts).

## P2 — L0/L1/L2/L3 context layering

**Actuellement** : pas de couches, le client choisit quoi load.

**Cible** : pattern MemPalace — L0 identity always-on (~50 tokens), L1 preferences always-on (~120 tokens), L2 topic-triggered, L3 deep semantic search explicite. Wake-up cost visible.

**Status** : partiellement adressé par Phase 2b MVP (L0 + L1 hardcodés via tag=identity / tag=preference dans le hook `wake_up`). L2 topic-triggered et L3 deep-search restent à faire — voir README Phase 2b "Deferred post-MVP".

**Quand** : après dogfood Phase 2b MVP, quand on voit en pratique que L0/L1 seuls laissent des trous.

## P2 — Réactiver mypy strict

**Actuellement** : `pyproject.toml` relâche `strict = true` pour passer en phase 1. Money avait strict déclaré mais jamais appliqué en CI sur le module `brain`. Résultat : 82 erreurs en strict mode (annotations manquantes, génériques non paramétrés, union-attr sur `mcp.settings.transport_security`).

**Cible** : `strict = true` + 0 erreur. À faire module par module, pas big-bang.

**Quand** : après phase 1, avant publication du package. Sinon on accumule.

## P3 — 29-tool MCP surface

**Actuellement** : 5 outils (`brain_store`, `brain_search`, `brain_related`, `brain_forget`, `brain_stats`).

**Cible** : matcher la surface de MemPalace (wings/rooms/halls ou équivalent Brain) pour parité fonctionnelle.

**Quand** : post-benchmarks. Pas avant d'avoir mesuré que la structure contribue vraiment (cf. leçon MemPalace : ne pas expédier des features qui ne mesurent rien).
