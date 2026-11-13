# claude-mods

Plugins pour Claude. Le projet principal, **Context Handoff**, aide à reprendre une longue
conversation ou session de travail sans perte de contexte grâce à un `HANDOFF.md` compact et vérifié.
Il existe en deux versions qui partagent le même format de document :

| | [`context-handoff-web`](plugins/context-handoff-web/README.md) | [`context-handoff`](plugins/context-handoff/README.md) |
| --- | --- | --- |
| Pour | **claude.ai** : chat web, application de bureau, mobile (et Cowork) | **Claude Code** : terminal, IDE, onglet Code |
| Installation | [Télécharger `context-handoff-web.zip`](https://github.com/th0masmcc/Claude-Mods/releases/latest/download/context-handoff-web.zip), puis Customize › Plugins › Add › **Upload plugin** ; ou Add marketplace `th0masmcc/claude-mods` | `/plugin marketplace add th0masmcc/claude-mods` puis `/plugin install context-handoff@claude-mods` |
| Prérequis | Aucun (exécution de code facultative) | `python3` |
| Détection | Jugement de Claude, guidé par le skill (pas de métrique accessible dans le chat) | Hooks locaux déterministes : taux de contexte, compactions, activité |
| Document | Fichier à télécharger, ou bloc Markdown à copier | Écrit à la racine du dépôt, avec sauvegarde |
| Reprise | Joindre `HANDOFF.md` à une nouvelle conversation | `/handoff resume`, avec comparaison à l'état Git |

Un document créé dans l'une des versions se reprend dans l'autre.

## Arborescence

```
.claude-plugin/marketplace.json     marketplace « claude-mods » (les deux plugins)
plugins/context-handoff-web/        version claude.ai : skills handoff et handoff-resume
plugins/context-handoff/            version Claude Code : hooks, skill /handoff, script Python
dist/context-handoff-web-1.1.0.zip  archive prête à téléverser sur claude.ai (reproductible)
.github/workflows/release.yml       publie les archives en Releases GitHub à chaque changement
tools/package.py                    construit et vérifie les archives
tools/sync_shared.py                recopie le format partagé (spec.py, redact.py) vers la version Web
```

## Développement

```bash
python3 -m unittest discover -s plugins/context-handoff/tests -v       # Claude Code (39 tests)
python3 -m unittest discover -s plugins/context-handoff-web/tests -v   # Web, format partagé, archives (22 tests)
claude plugin validate plugins/context-handoff-web                     # manifestes
python3 tools/package.py                                               # dist/*.zip
```

Après une modification de `plugins/context-handoff/skills/handoff/scripts/handofflib/spec.py` ou
`redact.py`, lancez `python3 tools/sync_shared.py`. Après toute modification du plugin Web, relancez
`python3 tools/package.py --only web` et commitez l'archive : un test vérifie qu'elle est à jour.

## Publication

À chaque push sur `main` (ou sur la branche de travail) qui modifie un plugin ou une archive, le
workflow `release` relance les tests, reconstruit les archives, vérifie que `dist/` est à jour et
publie les Releases `context-handoff-web-v<version>` (marquée *latest*) et
`context-handoff-code-v<version>`. Il peut aussi être lancé à la main (onglet Actions › release ›
Run workflow). Pour une nouvelle version, augmentez `version` dans le `plugin.json` concerné et dans
`.claude-plugin/marketplace.json`, puis reconstruisez l'archive.
