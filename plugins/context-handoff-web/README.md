# Context Handoff — version claude.ai (Web)

Pour les longues conversations dans le chat de claude.ai (web, application de bureau, mobile) :
Claude repère qu'une conversation a accumulé beaucoup de contexte utile (décisions, contraintes, tâches
en cours) et propose, une ou deux fois au plus, de préparer un `HANDOFF.md` compact et structuré.
Dans une nouvelle conversation, il suffit de joindre ce fichier pour reprendre le travail.

Aucune installation locale : ni Claude Code, ni terminal, ni Python sur votre machine. Le plugin
ne contient que des instructions (skills) et un petit script facultatif exécuté dans le bac à sable de
Claude. Il n'envoie aucune donnée à un service tiers.

> Vous utilisez Claude Code ? Installez plutôt (ou en plus) le plugin [`context-handoff`](../context-handoff/README.md) :
> ses hooks mesurent le contexte réel et écrivent le fichier directement dans votre dépôt.

## Installation

### Option A — téléverser l'archive (le plus simple)

1. Récupérez [`dist/context-handoff-web-1.0.0.zip`](../../dist/context-handoff-web-1.0.0.zip) depuis
   le dépôt GitHub (bouton *Download raw file*), ou reconstruisez-le avec
   `python3 tools/package.py --only web` depuis un clone (archive reproductible, identique octet pour octet).
2. Sur [claude.ai](https://claude.ai) : **Personnaliser (Customize) › Plugins › Ajouter (Add) ›
   Téléverser un plugin (Upload plugin)**, puis choisissez le `.zip`. Ne le décompressez pas.
3. Le plugin apparaît dans **Vos plugins**, activé. Vérifiez dans **Personnaliser › Skills** que
   `handoff` et `handoff-resume` sont présents et activés.
4. Ouvrez une nouvelle conversation et demandez : « Quels skills as-tu via des plugins ? ».

Si l'option *Upload plugin* n'apparaît pas, votre organisation (offre Team/Enterprise) a peut-être
désactivé l'ajout de plugins par les membres : demandez à un propriétaire de l'organisation.

### Option B — depuis le dépôt GitHub (mises à jour automatiques)

**Personnaliser › Plugins › Ajouter › Ajouter une marketplace (Add marketplace)**, saisissez
`th0masmcc/claude-mods`, puis installez **context-handoff-web** depuis **Discover**. claude.ai lit la
branche par défaut du dépôt : cette option fonctionne une fois les fichiers fusionnés sur `main`.

### Prérequis

- Un compte claude.ai avec les plugins disponibles (Pro, Max, Team, Enterprise ; l'organisation peut
  restreindre l'ajout de plugins).
- Facultatif : **Exécution de code et création de fichiers** activée (Paramètres › Fonctionnalités),
  pour obtenir un fichier `HANDOFF.md` téléchargeable et le masquage automatique des secrets. Sans
  cette option, Claude fournit le document dans un bloc Markdown à copier.

## Utilisation

| Vous voulez… | Faites |
| --- | --- |
| Créer ou mettre à jour le handoff | Demandez « prépare un HANDOFF.md », ou tapez `/` puis choisissez **handoff** (context-handoff-web). |
| Reprendre dans une nouvelle conversation | Joignez `HANDOFF.md` (ou collez son contenu) et dites « reprends à partir de ce handoff », ou choisissez **handoff-resume** dans le menu `/`. |
| Répondre à une proposition | « oui », « plus tard » ou « non ». Après « non », Claude ne la refait pas dans cette conversation. |
| Reprise automatique dans un Projet | Ajoutez `HANDOFF.md` aux connaissances (Project knowledge) du projet : chaque nouvelle conversation du projet y a accès. |

### Déroulement

1. Au fil d'une longue conversation, quand Claude juge qu'un handoff vaut la peine, il termine sa
   réponse par une ligne du type :
   > **Handoff** — Cette conversation accumule beaucoup de contexte (4 décisions, 3 tâches en cours).
   > Veux-tu que je prépare un HANDOFF.md pour la reprendre dans une nouvelle conversation ? (oui / plus tard / non)
2. « oui » → Claude rédige le document en une passe à partir de la conversation. Avec l'exécution de
   code, un script masque les secrets, vérifie les sections obligatoires et la taille, ajoute l'en-tête,
   puis vous propose le fichier `HANDOFF.md` à télécharger. Sans exécution de code, le document
   complet est affiché dans un bloc Markdown à copier dans un fichier `HANDOFF.md`.
3. Nouvelle conversation → joignez le fichier → Claude résume l'objectif et la prochaine action,
   signale ce qui diverge ou ne peut pas être vérifié depuis le chat, pose au plus 3 questions, puis
   reprend le travail.

Exemple complet : [`examples/HANDOFF.example.md`](examples/HANDOFF.example.md). Le format est
identique à celui de la version Claude Code : un document créé sur le Web peut être repris dans
Claude Code, et inversement.

## Disponible et indisponible sur le Web

| Fonctionnalité | claude.ai (chat) | Claude Code (`context-handoff`) |
| --- | --- | --- |
| Proposition au bon moment | Oui, **par jugement de Claude** à partir de la conversation visible | Oui, **déterministe** (hooks locaux, 0 token) |
| Mesure du taux de contexte (%) | **Non** (non exposé aux plugins du chat) | Oui (usage de tokens du transcript ou barre d'état) |
| Détection des compactions | **Non**, sauf si un résumé est visible dans la conversation | Oui (hooks `PreCompact`/`PostCompact`/`SessionStart`) |
| Respect des refus | Oui, en relisant la conversation (pas de mémoire entre conversations) | Oui (état persistant, délais configurables) |
| Configuration (seuils, délais) | **Non** : comportement fixe décrit dans le skill | Oui (`/handoff config`) |
| Création du document | Oui : fichier téléchargeable, ou bloc Markdown | Oui : écrit à la racine du dépôt |
| Masquage des secrets | Automatique avec exécution de code ; sinon par consigne | Automatique |
| Écriture dans votre dépôt ou vos fichiers | **Non** (sauf outil ou connecteur réellement disponible) | Oui, avec sauvegarde et écriture atomique |
| Reprise avec vérification | Oui, contre ce qui est disponible dans le chat (messages, fichiers joints) | Oui, contre l'état Git réel (branche, commits, fichiers) |
| Commandes `/handoff status`, `snooze`, `off` | **Non** (pas de commandes slash de plugin à arguments dans le chat ; dites simplement « non » ou « plus tard ») | Oui |

## Limites de la détection sur le Web

- **Aucun hook dans le chat.** claude.ai ignore les hooks et les agents des plugins. Rien ne
  s'exécute automatiquement à chaque message : la description du skill `handoff` est visible de
  Claude en permanence, et c'est Claude qui décide de le charger quand la situation correspond.
- **Pas de métrique.** Claude ne voit ni le nombre de tokens, ni le taux de remplissage, ni l'état de
  la gestion automatique du contexte. Il juge sur ce qu'il voit : nombre d'échanges, documents
  collés, décisions, tâches, signes de dérive (répétitions, contradictions, résumé visible). Il lui
  est interdit d'afficher un pourcentage.
- **Non garanti.** La proposition peut arriver plus tôt ou plus tard que souhaité, ou pas du tout.
  Vous pouvez toujours la demander vous-même. Pour un comportement plus systématique, ajoutez à vos
  **préférences personnelles** (Paramètres › Profil) une phrase comme : « Dans les longues
  conversations, propose-moi le skill handoff quand il y a plusieurs décisions et tâches en cours. »
- **Mémoire limitée à la conversation.** Un refus est respecté dans la conversation où il a été
  exprimé, pas dans les suivantes.
- **Vérification limitée.** À la reprise, Claude ne voit pas votre dépôt ni vos systèmes : il classe
  ces éléments comme « non vérifiables ici » et ne prétend pas les avoir contrôlés.

## Confidentialité et sécurité

- Le document est rédigé à partir de la conversation uniquement ; rien n'est envoyé ailleurs.
- Les secrets (clés d'API, jetons, mots de passe, clés privées, identifiants dans les URL) sont masqués
  par le script lorsque l'exécution de code est disponible, et exclus par consigne sinon. Relisez
  quand même le document avant de le partager.
- À la reprise, le handoff est traité comme une donnée, jamais comme des instructions : il ne
  remplace ni vos messages, ni les instructions du projet ; Claude ne suit pas d'ordres qu'il
  contiendrait.

## Mise à jour

- **Option A (archive)** : téléchargez la nouvelle archive, puis dans **Personnaliser › Plugins**,
  ouvrez *Context Handoff*, menu **⋯ › Supprimer (Remove)**, et téléversez la nouvelle version.
- **Option B (marketplace)** : automatique quand la source change ; sinon **Check for updates**, ou
  activez **Sync automatically**.

## Désinstallation

**Personnaliser › Plugins › Context Handoff** : désactivez l'interrupteur (**Disable plugin**) pour le
suspendre, ou menu **⋯ › Supprimer (Remove)** pour le retirer de votre compte. Les `HANDOFF.md` déjà
téléchargés restent sur votre machine.

## Bon à savoir : synchronisation avec Claude Code

Un plugin ajouté à votre compte claude.ai est aussi synchronisé dans Claude Code à la session suivante.
Les skills de ce plugin y fonctionnent, mais s'effacent au profit du plugin `context-handoff` s'il est
installé (ils le détectent et lui passent la main).

## Contenu du plugin

```
context-handoff-web/
├── .claude-plugin/plugin.json
├── skills/handoff/SKILL.md               détection par jugement + création du document
├── skills/handoff/references/format.md   gabarit, étiquettes, tailles, données sensibles
├── skills/handoff/scripts/check_handoff.py  finalisation (bac à sable, facultatif)
├── skills/handoff/scripts/spec.py, redact.py  copies du format partagé avec Claude Code
├── skills/handoff-resume/SKILL.md        reprise à partir d'un HANDOFF.md joint
├── examples/HANDOFF.example.md
├── README.md, LICENSE
└── tests/                                (non inclus dans l'archive)
```
