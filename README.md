# claude-mods

Marketplace de plugins pour [Claude Code](https://code.claude.com).

| Plugin | Description |
| --- | --- |
| [`context-handoff`](plugins/context-handoff/README.md) | Détecte les sessions longues ou complexes (taux de contexte, compactions, activité) et propose de sauvegarder un `HANDOFF.md` compact et vérifié ; `/handoff resume` reprend le travail dans une nouvelle session. |

## Installation

Dans une session Claude Code :

```
/plugin marketplace add th0masmcc/claude-mods
/plugin install context-handoff@claude-mods
```

Ou depuis un terminal : `claude plugin marketplace add th0masmcc/claude-mods && claude plugin install context-handoff@claude-mods`.

Documentation complète, configuration, limites et désinstallation : [plugins/context-handoff/README.md](plugins/context-handoff/README.md).

## Développement

```bash
python3 -m unittest discover -s plugins/context-handoff/tests -v   # tests
claude plugin validate plugins/context-handoff                     # manifeste
python3 tools/package.py                                           # archive ZIP dans dist/
```
