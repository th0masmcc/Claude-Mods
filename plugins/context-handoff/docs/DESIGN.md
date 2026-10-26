# Conception — context-handoff

## 1. Mécanismes étudiés (Claude Code 2.1.310)

Vérifiés dans la documentation embarquée du binaire et par des exécutions réelles :

| Mécanisme | Ce qu'il offre réellement | Utilisation |
| --- | --- | --- |
| Hook `UserPromptSubmit` | Reçoit `session_id`, `transcript_path`, `cwd`, `prompt`. Sortie : `systemMessage` (affiché à l'utilisateur, 0 token) et `hookSpecificOutput.additionalContext` (injecté au modèle). S'exécute entre deux tours. | Point de détection principal et canal de proposition. |
| Hook `PreCompact` | `trigger` = `manual` \| `auto`, `custom_instructions`. Seul signal de compaction *imminente*. | Notice à l'utilisateur ; mémorise la compaction en cours. |
| Hook `PostCompact` | `trigger`, `compact_summary`. | Comptage fiable des compactions. |
| Hook `SessionStart` | `source` = `startup` \| `resume` \| `clear` \| `compact` ; `additionalContext`. | Rappel discret d'un handoff existant ; comptage de compaction ; nettoyage d'état. |
| Hook `Stop` | Peut forcer la poursuite (`decision: block`). | **Écarté** : relancerait un tour (coût, intrusion). |
| Hooks `prompt`/`agent` | Appellent un modèle ; limités aux événements d'outils. | **Écartés** : coût en tokens à chaque appel. |
| Barre d'état (`statusLine`) | Reçoit `context_window.used_percentage` et `context_window_size` exacts. | Pont **optionnel** (un seul emplacement, souvent déjà occupé). |
| Transcript JSONL | `message.usage` de chaque réponse, `compact_boundary` (`compactMetadata.preTokens`), appels d'outils. | Mesure du contexte et des signaux de complexité, lue de façon incrémentale. |
| Skill (`SKILL.md`) | Commande `/handoff` avec `$ARGUMENTS`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_SESSION_ID}` substitués ; seul le nom/description (~60 tokens) reste en contexte. | Interface utilisateur et procédures. |
| Plugin + marketplace | Regroupe hooks et skill, `${CLAUDE_PLUGIN_ROOT}`, installation en une commande. | Empaquetage. |
| « Mods » TypeScript (API `$`) | Interface riche (bandeaux, toasts) mais très récente. | **Écarté** pour la compatibilité avec les versions courantes. |

Aucun hook ne reçoit le pourcentage de contexte : c'est la principale limite, compensée par la lecture
de `message.usage` dans le transcript (exacte, un tour de retard) et le pont optionnel.

## 2. Architecture retenue

Plugin = **hooks de commande** (détection, 0 token) + **un skill** `/handoff` (actions, chargé à la
demande) + **un script Python stdlib** (tout le travail déterministe : mesures, Git, masquage des
secrets, validation, écriture atomique, comparaison).

Répartition du travail entre script et modèle :

- Le script fait ce qui est vérifiable sans intelligence : état Git, empreintes, métadonnées,
  masquage, contrôle de taille et de sections, sauvegardes, divergences.
- Le modèle ne fait que la synthèse, à partir de **son propre contexte** (il n'a pas besoin de relire
  la conversation : il l'a déjà). Pas de second agent, pas de modèle supplémentaire.

## 3. Signaux et décision

Lecture incrémentale du transcript : chaque appel ne lit que les octets ajoutés depuis le précédent
(décalage mémorisé ; lignes incomplètes laissées pour plus tard ; au-delà de 16 Mio non lus, seule la
fin est analysée et les compteurs sont marqués partiels). Mesure : ~70–100 ms par hook sur un
transcript de 1,5 Mio.

**Pression**

- `ratio` = (`input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens` de la dernière
  réponse principale, hors sous-agents) / fenêtre. Fenêtre : config > barre d'état > `[1m]` dans le
  modèle ou >200k observés ⇒ 1M > 200k.
- Compactions = max(compactions vues par les hooks, marqueurs `compact_boundary`) + compactions
  déduites (chute > 50 % sans marqueur). Les hooks `PostCompact` et `SessionStart:compact` sont
  dédoublonnés (fenêtre de 120 s).

**Valeur** (points, plafonnés) : demandes /5 (≤4), fichiers modifiés /3 (≤4), tâches /3 (≤3),
erreurs d'outils /4 (≤2), demandes exprimant décisions/contraintes (≤3), changements de sujet (≤2),
durée > 1 h / > 3 h (1/2), compactions ×2 (≤4), document existant obsolète (1).

**Règle** : compaction depuis le dernier handoff et valeur ≥ max(2, min−2) → « compaction » ;
ratio ≥ `urgent_threshold` et valeur ≥ max(2, min−2) → « urgent » ; ratio ≥ `threshold` et valeur ≥
`min_value_score` → « threshold ».

**Anti-harcèlement** (dans l'ordre) : désactivé / mode manuel ; `off` pour la session ; plafond de
propositions ; sourdine active sans changement significatif (+`rearm_delta` ou nouvelle compaction) ;
handoff récent sans changement significatif ; délai entre propositions ; croissance d'au moins
`rearm_delta/2` (ou compaction) depuis la dernière proposition ignorée. Les demandes commençant par
`/` ou mentionnant « handoff » ne déclenchent rien.

## 4. Coût en tokens

| Situation | Coût |
| --- | --- |
| Session normale | ~60 tokens (description du skill dans la liste des skills) |
| Proposition (`notify: assistant`) | ~120 tokens, au plus 3 fois par session ; 0 en `notify: system` |
| Rappel au démarrage / après compaction | ~40 tokens (désactivable) |
| `/handoff status`, `config`, `snooze` | ~540 (skill) + sortie du script |
| `/handoff create` | ~540 + ~1000 (procédure) + ~600–1000 (faits Git) + le document produit |
| `/handoff resume` | ~540 + ~500 (procédure) + vérification + lecture du document (≤ `max_tokens`) |

Pas de résumés empilés : la mise à jour réécrit l'état *actuel* (éléments obsolètes retirés), la
taille est plafonnée et la cible s'adapte à la complexité (600 + 150 × score).

## 5. Évolutions possibles

- Utiliser l'API « mods » (bandeau au-dessus du prompt, bouton « Créer le handoff ») quand elle sera
  stable et largement diffusée.
- Lire `compact_summary` (PostCompact) pour signaler précisément ce que le résumé a omis.
- Section « Done » archivée séparément quand le document approche de `max_tokens`.
- Seuils appris par projet (historique des refus/acceptations).
