# Tests et validation

Environnement : Linux, Claude Code 2.1.310, Python 3.11 / 3.12 / 3.13, Git 2.x — 26/10/2026.

## 1. Suite automatisée

```bash
cd plugins/context-handoff && python3 -m unittest discover -s tests -v
```

Résultat : **39 tests, 38 réussis, 1 ignoré en root** (`test_permission_denied` : root ignore les
droits ; exécuté séparément en utilisateur `nobody` → réussi). Identique sous Python 3.11, 3.12 et 3.13.
Les tests passent par le vrai point d'entrée (`handoff.py hook` en sous-processus, JSON sur stdin),
avec des transcripts JSONL synthétiques au format observé dans Claude Code 2.1.310, des dépôts Git
temporaires et une horloge figée.

| Scénario de la spécification | Test(s) |
| --- | --- |
| Session courte : aucune proposition | `test_short_session_no_proposal` |
| Session longue, beaucoup de contexte pertinent | `test_long_rich_session_proposes_once` (proposition unique, coût < 160 tokens) |
| Session longue mais simple | `test_long_but_simple_session_left_alone` (90 % de contexte, rien proposé) |
| Compaction détectable | `test_detectable_compaction` (PreCompact + PostCompact + SessionStart + `compact_boundary` comptés une seule fois) |
| Compaction non détectable | `test_undetectable_compaction_inferred_from_token_drop` |
| Refus de l'utilisateur | `test_refusal_respected_until_significant_change`, `test_snooze_expiry_alone_does_not_renag`, `test_snooze_blocks_within_delay`, `test_off_for_session_then_back_on`, `test_other_session_unaffected_by_session_off`, `test_max_proposals_per_session` |
| Document existant | `test_create_then_idempotent_then_update_with_backup`, `test_existing_document_must_be_read_before_replacement`, `test_backups_are_rotated` |
| Document obsolète | `test_obsolete_document_detected` (branche, commits, âge) |
| Git avec modifications non commitées | `test_git_repo_with_uncommitted_changes` (rien n'est commité ni indexé) |
| Projet sans Git | `test_project_without_git` |
| Informations incertaines ou contradictoires | `test_uncertain_or_contradictory_information_reported` (chemins absents, écarts, étiquettes) |
| Secrets potentiels | `test_secrets_are_redacted`, `test_gather_never_reads_sensitive_files` |
| Reprise dans une nouvelle session | `test_resume_in_new_session` |
| Erreurs d'écriture, permissions | `test_permission_denied`, `test_unwritable_location_reports_io_error`, `test_unsafe_targets_refused` |
| Robustesse des hooks | `test_hook_survives_garbage`, `test_incremental_scan_handles_partial_lines`, `test_sidechain_and_meta_records_ignored` |
| Mesures de remplacement | `test_no_usage_data_falls_back_to_estimate`, `test_statusline_bridge_gives_exact_window` |
| Interface / configuration | `test_slash_command_prompt_is_never_interrupted`, `test_system_notify_mode_costs_no_model_tokens`, `test_disabled_and_manual_mode`, `test_config_layers_and_validation`, `test_configured_location`, `test_session_start_quiet_and_disabled`, `test_french_headings_accepted`, `test_validation_refuses_incomplete_or_oversized`, `test_verify_without_document`, `test_shipped_example_is_valid` |

## 2. Essais réels avec Claude Code 2.1.310

Exécutés avec `claude -p … --plugin-dir plugins/context-handoff --output-format stream-json`
(événements `hook_started`/`hook_response` observés) :

| Essai | Résultat observé |
| --- | --- |
| Chargement du plugin, hooks `SessionStart` et `UserPromptSubmit` | Déclenchés à chaque tour, sortie vide quand rien n'est à signaler. |
| Proposition (seuils abaissés pour l'essai) | `additionalContext` injecté ; le modèle (Haiku) a terminé sa réponse par « Want me to save the session state to HANDOFF.md? Run `/handoff create` to do it. » |
| `/handoff status` | `$ARGUMENTS`, `${CLAUDE_SKILL_DIR}` et `${CLAUDE_SESSION_ID}` correctement substitués ; script appelé ; état affiché. |
| `/handoff create` après une vraie petite tâche (Sonnet) | `gather` → rédaction → `write` via heredoc ; document de ~285 tokens, étiqueté (`[VERIFIED]`, `[DECIDED]`, `[UNKNOWN]`), métadonnées correctes, rien de commité. |
| `/handoff resume` dans une autre session | `verify` puis lecture ; divergences rapportées (fichier non suivi nouveau, fichier prévu absent jugé normal) ; question posée avant d'agir sur un point bloquant (pytest absent). |
| Rappel au démarrage d'une nouvelle session | `additionalContext` + `systemMessage` émis ; le modèle confirme avoir reçu le rappel sans lire le fichier. |
| `/compact` (manuel) | `SessionStart:compact` capté, compaction comptée une fois, rappel « the conversation was just compacted » injecté. |
| Installation depuis l'archive ZIP | `claude plugin marketplace add <dossier>` + `claude plugin install` → `enabled` ; `uninstall` et `marketplace remove` réussis. |
| `claude plugin validate` | Plugin et marketplace valides (seul avertissement : pas d'icône). |
| Latence du hook | 70–110 ms sur le transcript réel de 1,5 Mio de cette session de développement. |

## 3. Non testé / limites de la validation

- **Compaction automatique réelle** (fenêtre réellement saturée) : non provoquée ; le chemin `PreCompact`
  `trigger=auto` est couvert par les tests automatisés, la compaction manuelle par l'essai réel.
- **Affichage de `systemMessage` dans l'interface interactive (TUI / application)** : vérifié dans le
  flux d'événements, pas visuellement.
- **macOS, Windows/WSL, Python 3.8–3.10** : non exécutés ici ; le workflow `.github/workflows/test.yml`
  couvre Ubuntu et macOS avec Python 3.8 et 3.12 à chaque push.
- **Pont de barre d'état** : testé par entrée JSON simulée (schéma documenté dans le binaire), pas
  dans une barre d'état réelle.
- Dans le conteneur de test, `claude -p` réutilisait l'identifiant de session parent ; le rappel de
  démarrage a donc été vérifié avec `--session-id` explicite.
