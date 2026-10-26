# Tests — version claude.ai (Web)

Date : 26/10/2026. Environnement : Linux, Python 3.11–3.13, Claude Code 2.1.310 (pour `claude plugin
validate` et les essais comportementaux).

## 1. Tests automatisés

```bash
python3 -m unittest discover -s plugins/context-handoff-web/tests -v
```

**22 tests réussis** :

| Domaine | Ce qui est vérifié |
| --- | --- |
| Manifeste | `name` valide et stable, `displayName`, `version`, `description`, `license` ; `.claude-plugin/` ne contient que `plugin.json` |
| Composants | Aucun `bin/`, `hooks/`, `agents/`, `.mcp.json`, `commands/` (inutiles ou bloquants dans le chat) |
| Skills | Nom = dossier, `[a-z0-9-]{1,64}`, description de 1 à 1 024 caractères, < 500 lignes, uniquement `name`/`description` dans l'en-tête ; fichiers référencés présents |
| Honnêteté | Les skills interdisent d'afficher un pourcentage et ne prétendent pas qu'un hook s'exécute |
| Format partagé | Copies `spec.py`/`redact.py` identiques à la version Claude Code ; gabarit ↔ validateur ; en-tête d'exemple = en-tête généré |
| Marketplace | Les deux plugins listés, versions cohérentes avec les manifestes |
| Archive Web | Un seul dossier racine, un seul `plugin.json`, pas de tests ni de caches, archive reproductible, copie versionnée dans `dist/` identique à une reconstruction ; le vérificateur rejette les archives invalides |
| Archive Claude Code | Contient la marketplace et les deux plugins |
| Script de finalisation | Exécuté depuis une copie isolée du dossier du skill (comme dans le bac à sable) : écriture avec en-tête, repli sur le dossier courant hors claude.ai, idempotence, refus si sections manquantes ou trop long, masquage des secrets, erreur d'écriture signalée |
| Compatibilité croisée | Un document Web est accepté par `handoff.py write/verify` (Claude Code) ; l'exemple Claude Code et l'exemple Web passent la validation |

Les 39 tests de la version Claude Code passent toujours (38 réussis, 1 ignoré en root, réussi en
utilisateur non privilégié).

`claude plugin validate plugins/context-handoff-web` : **Validation passed** (seul avertissement : pas
d'icône, utile uniquement pour une publication dans l'annuaire).

## 2. Essais comportementaux avec un vrai modèle

claude.ai n'est pas accessible depuis l'environnement de développement. Les skills ont été chargés
seuls avec `claude -p --plugin-dir plugins/context-handoff-web` (Sonnet), où ils se chargent de la même
façon que dans le chat ; c'est une approximation, pas une validation sur claude.ai.

| Scénario | Résultat |
| --- | --- |
| Conversation courte (1 question) | Aucune proposition. |
| Longue conversation (migration de newsletter, 17 échanges, ~8 décisions) avec la 1ʳᵉ description | **Aucune proposition, skill jamais chargé.** Description réécrite en conséquence. |
| Même conversation, 18ᵉ échange, nouvelle description | Proposition d'une ligne en fin de réponse, après avoir répondu complètement. |
| Refus (« Non merci ») puis 2 échanges | Refus acquitté ; aucune nouvelle proposition. |
| « Finalement oui, prépare le HANDOFF.md » | Skill chargé, `format.md` lu, document de ~1 300 tokens : 8 `[DECIDED]`, 6 `[UNKNOWN]`, 2 `[ASSUMED]`, valide pour le validateur partagé, aucun secret. |
| Création avec exécution de script autorisée et clé d'API fictive dans la demande | `check_handoff.py` exécuté (`status: written`), clé non recopiée, explication donnée à l'utilisateur. |
| Nouvelle conversation, handoff collé + « l'IT a déjà validé le DNS » | `handoff-resume` chargé ; objectif et prochaine action résumés ; divergence détectée et plan ajusté ; vérification côté fournisseur signalée comme non faite ; 3 questions. |

## 3. Vérifications qui demandent une intervention humaine sur claude.ai

1. **Customize › Plugins › Add › Upload plugin** avec `dist/context-handoff-web-1.0.0.zip` : le plugin
   s'installe sans erreur et apparaît dans *Vos plugins*.
2. **Customize › Skills** : `handoff` et `handoff-resume` présents et activés.
3. Nouvelle conversation : « Quels skills as-tu via des plugins ? » → les deux skills cités.
4. Menu `/` dans la zone de saisie → `handoff` (context-handoff-web) sélectionnable.
5. Avec *Exécution de code et création de fichiers* activée : « prépare un HANDOFF.md » → un fichier
   `HANDOFF.md` téléchargeable est proposé (chemin `/mnt/user-data/outputs/`, non vérifiable ici).
6. Sans exécution de code : le document arrive dans un bloc Markdown.
7. Nouvelle conversation, fichier joint : la reprise suit les étapes de `handoff-resume`.
8. Une longue conversation réelle : la proposition apparaît une fois, pas à chaque message.
