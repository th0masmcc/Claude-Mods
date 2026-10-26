# context-handoff — plugin Claude Code

Détecte les sessions Claude Code longues ou devenues complexes, propose au bon moment de sauvegarder
leur état opérationnel dans un `HANDOFF.md` compact et vérifié, puis permet de reprendre le travail
dans une nouvelle session avec `/handoff resume`.

- **Détection locale, sans appel au modèle** : des hooks lisent les compteurs que Claude Code écrit déjà
  (usage de tokens de la dernière réponse, compactions, outils utilisés). Aucun serveur, aucune
  dépendance : Python 3.8+ (bibliothèque standard).
- **Non intrusif** : la proposition n'arrive qu'entre deux tours (jamais pendant une commande), au
  plus 3 fois par session, avec délai de grâce, et un refus est respecté.
- **Consentement** : le document n'est jamais généré sans demande explicite.
- **Fiable** : faits vérifiés, décisions, hypothèses et inconnues sont étiquetés ; la reprise compare
  le document à l'état réel du dépôt (branche, commits, fichiers modifiés, chemins cités).
- **Sûr** : secrets masqués avant écriture, fichiers `.env`/clés jamais lus, aucun commit/push,
  écriture atomique avec sauvegarde de la version précédente hors du dépôt.

## Sommaire

1. [Installation](#installation)
2. [Utilisation](#utilisation)
3. [Fonctionnement de la détection](#fonctionnement-de-la-détection)
4. [Configuration](#configuration)
5. [Limites techniques](#limites-techniques)
6. [Sécurité et fichiers](#sécurité-et-fichiers)
7. [Tests](#tests)
8. [Désinstallation](#désinstallation)
9. [Empaquetage ZIP](#empaquetage-zip)
10. [Arborescence](#arborescence)

Conception détaillée et choix d'architecture : [`docs/DESIGN.md`](docs/DESIGN.md).
Résultats des tests : [`docs/TESTING.md`](docs/TESTING.md).
Exemple de document : [`examples/HANDOFF.example.md`](examples/HANDOFF.example.md).

## Installation

Prérequis : Claude Code 2.x (testé avec 2.1.310), `python3` dans le `PATH` (macOS, Linux, WSL ou
Git Bash sous Windows). Sans `python3`, les hooks se désactivent silencieusement.

**Depuis GitHub (recommandé)**, dans une session Claude Code :

```
/plugin marketplace add th0masmcc/claude-mods
/plugin install context-handoff@claude-mods
```

ou depuis un terminal :

```bash
claude plugin marketplace add th0masmcc/claude-mods
claude plugin install context-handoff@claude-mods
```

Choisissez la portée *user* pour l'activer dans tous vos projets. Redémarrez la session (ou
`/reload-plugins`) pour charger les hooks.

**Depuis un dossier local ou une archive ZIP** (après extraction) :

```bash
claude plugin marketplace add /chemin/vers/claude-mods      # dossier contenant .claude-plugin/marketplace.json
claude plugin install context-handoff@claude-mods
# ou, pour un essai ponctuel sans installation :
claude --plugin-dir /chemin/vers/claude-mods/plugins/context-handoff
```

Vérification : `/handoff status` doit afficher l'état de la détection.

Les commandes `/handoff` exécutent le script `handoff.py` via l'outil Bash : Claude Code demande
l'autorisation au premier appel (choisissez « ne plus demander » pour cette commande si vous le
souhaitez). Les hooks, eux, ne demandent rien.

## Utilisation

| Commande | Effet |
| --- | --- |
| `/handoff` | Analyse la session (contexte, activité, document existant) et demande s'il faut créer le handoff. |
| `/handoff create` | Génère ou met à jour `HANDOFF.md` (le fait de taper la commande vaut consentement). |
| `/handoff resume` | Lit le document, le compare au dépôt réel, signale les divergences, puis reprend à la prochaine action. |
| `/handoff status` | Affiche les signaux de détection, la décision et la raison d'une éventuelle mise en sourdine. |
| `/handoff config` | Affiche les paramètres ; `/handoff config set threshold 0.7`, `/handoff config unset threshold`. |
| `/handoff snooze [min]` | Met les propositions en sourdine (défaut : 120 min, ou jusqu'à un changement significatif). |
| `/handoff off` / `on` | Coupe / réactive les propositions pour la session en cours. |

Le nom complet de la commande est `/context-handoff:handoff` ; `/handoff` fonctionne tant qu'aucune
autre commande ne porte ce nom.

### Déroulement typique

1. La session grossit. Quand les signaux le justifient, Claude termine sa réponse par une phrase du
   type : « Cette session contient beaucoup de contexte et plusieurs décisions importantes. Souhaites-tu
   sauvegarder l'état dans HANDOFF.md avec /handoff create ? »
2. Vous répondez « oui » (ou tapez `/handoff create`) → le document est écrit à la racine du projet.
   Vous répondez « non » → Claude exécute `snooze` et la proposition ne revient pas avant le délai
   configuré, sauf changement significatif (contexte +15 points, ou compaction).
3. Dans une nouvelle session, un rappel discret (≈40 tokens) indique qu'un `HANDOFF.md` existe ;
   `/handoff resume` reprend le travail.

En mode `notify: system`, la proposition s'affiche uniquement comme notice d'interface (coût : zéro
token) au lieu d'être formulée par Claude.

### Contenu du document

Objectif, état d'avancement, décisions (avec raisons et alternatives rejetées), contraintes, état
technique (branche, commit, fichiers non commités, environnement), problèmes rencontrés, prochaine
action, plan de continuation avec critères de validation, points d'attention, références. Les sections
vides sont omises, sauf *Objectif* et *Prochaine action* (obligatoires). Chaque affirmation dont la
certitude compte est étiquetée `[VERIFIED]`, `[DECIDED]`, `[ASSUMED]` ou `[UNKNOWN]`.

Un en-tête de métadonnées (date, session, branche, commit, nombre de fichiers modifiés) est ajouté par
le script — pas par le modèle — et sert à détecter l'obsolescence lors de la reprise.

## Fonctionnement de la détection

Deux axes, combinés (détails : [`docs/DESIGN.md`](docs/DESIGN.md)) :

- **Pression** — taux de remplissage du contexte = tokens d'entrée de la dernière réponse
  (`input + cache_read + cache_creation`, lus dans le transcript) / taille de fenêtre ; compactions
  (hooks `PreCompact`/`PostCompact`/`SessionStart:compact`, enregistrement `compact_boundary` du
  transcript, ou chute brutale des tokens).
- **Valeur** — ce qui serait perdu : nombre de demandes, fichiers modifiés, tâches (TodoWrite /
  TaskCreate), erreurs d'outils, formulations de décisions/contraintes (« must », « jamais »,
  « plutôt »…), changements de sujet, durée, compactions, document existant obsolète.

Règle par défaut : proposer si *compaction depuis le dernier handoff* et valeur ≥ 2 ; ou contexte ≥ 80 %
et valeur ≥ 2 ; ou contexte ≥ 60 % et valeur ≥ 4. Une longue session de simple lecture (beaucoup de
tokens, peu de valeur) n'est pas interrompue ; une session courte et dense non plus (pas de pression).

## Configuration

Ordre de priorité : valeurs par défaut < `~/.claude/context-handoff/config.json` (portée *user*) <
`<projet>/.claude/context-handoff.json` (portée *project*) < variables d'environnement `HANDOFF_<CLÉ>`.
Les variables peuvent être posées nativement dans le bloc `"env"` d'un `settings.json` de Claude Code,
par ex. `"env": {"HANDOFF_ENABLED": "false"}`.

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `enabled` | `true` | Interrupteur général (détection et propositions). |
| `mode` | `auto` | `auto` : propositions automatiques ; `manual` : seulement les commandes `/handoff`. |
| `notify` | `assistant` | `assistant` : Claude pose la question en fin de réponse (~120 tokens) ; `system` : notice d'interface (0 token) ; `both`. |
| `threshold` | `0.60` | Taux de contexte à partir duquel une proposition est possible. |
| `urgent_threshold` | `0.80` | Taux à partir duquel une valeur plus faible suffit. |
| `min_value_score` | `4` | Score de complexité minimal (l'urgence et la compaction exigent `max(2, min-2)`). |
| `context_window` | `auto` | Taille de fenêtre en tokens, ou `auto` (voir limites). |
| `cooldown_minutes` | `20` | Délai minimal entre deux propositions. |
| `max_proposals_per_session` | `3` | Nombre maximal de propositions par session. |
| `decline_snooze_minutes` | `120` | Silence après un refus / `snooze`. |
| `rearm_delta` | `0.15` | Croissance du contexte considérée comme « changement significatif ». |
| `max_tokens` | `2000` | Taille maximale du document (le script refuse au-delà). La cible réelle s'adapte à la complexité : 600 + 150 × score. |
| `path` | `HANDOFF.md` | Emplacement, relatif à la racine du projet (racine Git si détectée) ou absolu. |
| `verbosity` | `normal` | `quiet` : notices minimales, pas d'annonce au démarrage ; `verbose` : chemins internes dans `status`. |
| `session_start_hint` | `true` | Signaler au modèle (≈40 tokens) qu'un handoff existe au démarrage / après compaction. |
| `stale_hours` | `72` | Âge au-delà duquel le document est signalé obsolète. |
| `backups` | `5` | Versions précédentes conservées dans `~/.claude/context-handoff/backups/`. |

### Pont optionnel avec la barre d'état (mesure exacte)

Les hooks ne reçoivent pas le pourcentage de contexte ; la barre d'état (`statusLine`) si. Pour une
mesure exacte (y compris la vraie taille de fenêtre, ex. 1M), utilisez le script comme barre d'état,
ou appelez-le depuis la vôtre :

```json
{ "statusLine": { "type": "command",
  "command": "python3 ~/.claude/plugins/<chemin>/context-handoff/skills/handoff/scripts/handoff.py statusline" } }
```

Il affiche `ctx 63%` (`--quiet` pour n'afficher rien et seulement enregistrer). Si vous avez déjà une
barre d'état : `input=$(cat); echo "$input" | python3 …/handoff.py statusline --quiet; echo "$input" | votre-script`.

## Limites techniques

- **Pas d'API de taux de contexte pour les hooks.** Claude Code n'expose le pourcentage qu'à la barre
  d'état. Le plugin lit donc l'usage de tokens de la dernière réponse dans le transcript JSONL : la
  valeur est exacte mais a un tour de retard, et la **taille de fenêtre** est déduite (200k par
  défaut ; 1M si le modèle porte `[1m]` ou si plus de 200k tokens ont été observés). Fixez
  `context_window` ou activez le pont de barre d'état si votre fenêtre diffère.
- **Compaction imminente** : seul `PreCompact` la signale, au moment où elle commence ; il n'est pas
  possible de l'anticiper autrement que par le taux de contexte. La notice affichée à ce moment invite
  à créer le handoff *après* la compaction (aucune génération automatique).
- **Compaction non observable** (hooks absents, ancienne version) : déduite d'une chute de plus de 50 %
  des tokens sans marqueur ; signalée comme telle dans `status`.
- **Sans données d'usage** (format de transcript différent) : estimation à partir du volume de texte
  (≈ 4 caractères/token), indiquée `ratio source: estimate`.
- **Pas de vraie boîte de dialogue** : un hook ne peut pas ouvrir de dialogue interactif. La proposition
  passe par une phrase de Claude ou une notice d'interface ; la réponse de l'utilisateur fait office de
  confirmation.
- **Changements de sujet et décisions** : heuristiques lexicales (mots-clés FR/EN, recouvrement de
  vocabulaire stocké sous forme de hachages). Ils ne font que pondérer le score, jamais déclencher seuls.
- **Session ignorée** : la session qui a écrit le handoff ne reçoit pas le rappel de démarrage.
- **Format du transcript** non documenté officiellement : en cas d'évolution, les signaux se dégradent
  (estimation) sans casser la session ; le hook sort toujours avec le code 0.
- **Windows natif** sans `python3` : non pris en charge (utiliser WSL ou installer Python).

## Sécurité et fichiers

- Le `HANDOFF.md` est écrit à la racine du dépôt Git (ou du projet), ou à `path`. Le script refuse
  d'écrire dans `.git/`, sur autre chose qu'un `.md`, ou sur un fichier modifié depuis sa lecture
  (contrôle par empreinte : un document existant doit être relu et fusionné avant d'être remplacé).
- Écriture atomique (fichier temporaire puis renommage) ; version précédente sauvegardée dans
  `~/.claude/context-handoff/backups/<projet>/` (hors dépôt) ; contenu identique → fichier non réécrit.
- Masquage automatique avant écriture : clés privées, jetons GitHub/GitLab/Slack/Anthropic/OpenAI/
  Stripe/Google, clés AWS, JWT, identifiants dans les URL, affectations `password=`/`token=`/
  `api_key=`… Les fichiers sensibles (`.env`, `*.pem`, `id_rsa`…) sont listés sans être lus.
- Aucun commit, push, ni modification de `.gitignore`. Le choix de versionner le document vous revient.
- L'historique de conversation n'est pas copié : l'état local ne contient que des compteurs, des
  chemins de fichiers modifiés et des hachages de mots (supprimés après 30 jours).
- Le document est présenté au modèle comme matériau de référence, **jamais comme des instructions** ;
  la reprise donne priorité au dépôt réel, à l'utilisateur et aux règles du projet.

## Tests

```bash
cd plugins/context-handoff
python3 -m unittest discover -s tests -v
```

39 tests unitaires et d'intégration (scénarios de la spécification, exécutés via le vrai point
d'entrée des hooks, en sous-processus) + essais réels avec Claude Code 2.1.310 : voir
[`docs/TESTING.md`](docs/TESTING.md).

## Désinstallation

```bash
claude plugin uninstall context-handoff@claude-mods
claude plugin marketplace remove claude-mods   # optionnel
rm -rf ~/.claude/context-handoff                # état local, configuration et sauvegardes (optionnel)
```

Supprimez aussi, le cas échéant, `<projet>/.claude/context-handoff.json`, les variables `HANDOFF_*`
de vos `settings.json`, la `statusLine` du pont, et les `HANDOFF.md` que vous ne souhaitez pas garder.

## Empaquetage ZIP

```bash
python3 tools/package.py            # depuis la racine du dépôt → dist/context-handoff-1.0.0.zip
```

L'archive contient la marketplace et le plugin (sans caches) ; elle s'installe comme un dossier local
(voir [Installation](#installation)).

## Arborescence

```
.claude-plugin/marketplace.json          marketplace « claude-mods »
plugins/context-handoff/
├── .claude-plugin/plugin.json           manifeste du plugin
├── hooks/hooks.json                     UserPromptSubmit, PreCompact, PostCompact, SessionStart
├── skills/handoff/
│   ├── SKILL.md                         commande /handoff (aiguillage, ~540 tokens à l'appel)
│   ├── create.md                        procédure de génération (chargée seulement pour create)
│   ├── resume.md                        procédure de reprise (chargée seulement pour resume)
│   └── scripts/
│       ├── handoff.py                   CLI : hook, status, config, snooze, gather, write, verify, statusline
│       └── handofflib/                  config, state, transcript, detect, gitinfo, redact, document, hooks
├── tests/                               unittest (stdlib)
├── docs/DESIGN.md, docs/TESTING.md
└── examples/HANDOFF.example.md
tools/package.py                         création de l'archive ZIP
```
