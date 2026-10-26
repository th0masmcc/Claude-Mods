# Conception — version claude.ai (Web)

## Ce que la documentation officielle permet (vérifié le 26/10/2026)

Sources : [Plugin feature support across platforms](https://claude.com/docs/plugins/platform-support),
[Plugin structure and testing](https://claude.com/docs/plugins/build),
[Plugins](https://claude.com/docs/plugins/overview), [Create custom skills](https://claude.com/docs/skills/how-to).

| Élément | Chat claude.ai | Conséquence pour ce plugin |
| --- | --- | --- |
| Skills `skills/<nom>/SKILL.md` | Chargés ; Claude les active selon leur `description`, ou l'utilisateur les choisit dans le menu `/` | Tout passe par deux skills |
| Commandes `commands/*.md` | Chargées comme skills (pas de `/commande arguments`) | Pas de commandes : inutile |
| Hooks, agents | **Ignorés** | Aucune détection automatique possible ; pas de fausse automatisation |
| Scripts d'un skill | Exécutés dans le bac à sable d'exécution de code ; le dossier du skill y est copié | Script facultatif, autonome dans le dossier du skill |
| `bin/` à la racine | Empêche l'installation | Absent |
| Upload | `.zip` ou `.plugin`, un seul `.claude-plugin/plugin.json` à la racine ou dans un dossier unique ; ≤ 5 000 fichiers, ≤ 200 Mo | Archive `context-handoff-web/…` vérifiée par `tools/package.py` |
| Synchronisation | Un plugin du compte est synchronisé dans Claude Code | Les skills Web cèdent la main au plugin Claude Code s'il est présent |

## Stratégie de détection

Sans hook ni métrique, le seul mécanisme permanent est la **description du skill**, que Claude voit à
chaque tour. Elle énonce donc les critères d'une proposition (volume et valeur, signes de dérive) et
le format de la ligne de proposition. Le corps du skill, chargé à la demande, détaille les règles
(volume ET valeur, plafonds, réaction aux refus).

Constat des essais : avec une première description centrée sur la demande explicite, Claude n'a
jamais chargé le skill de lui-même en 17 échanges riches en décisions. Après réécriture pour énoncer
d'abord l'usage proactif, la proposition est arrivée au 18ᵉ échange. Ce comportement reste un
jugement du modèle, non garanti ; pour un comportement plus régulier, l'utilisateur peut ajouter une
consigne à ses préférences personnelles (lues dans chaque conversation).

La mémoire des refus est la conversation elle-même : la ligne de proposition commence par
`**Handoff** —`, ce qui permet à Claude de retrouver ses propositions et les réponses.

## Partage avec la version Claude Code

- `spec.py` (format, en-tête, sections, étiquettes, validation) et `redact.py` (masquage) sont
  canoniques dans `plugins/context-handoff/…/handofflib/` et copiés par `tools/sync_shared.py` ;
  un test échoue si les copies divergent.
- `references/format.md` reprend le gabarit de `create.md` ; un test vérifie que chaque titre du
  gabarit correspond à une section connue du validateur et que l'en-tête d'exemple est exactement
  celui que génère `spec.build_header`.
- Les documents sont interchangeables : `source: claude-web` ou `source: claude-code` dans
  l'en-tête ; testé dans les deux sens.

## Coût

Description du skill `handoff` : ~190 tokens visibles en permanence (+ ~70 pour `handoff-resume`).
Chargement à la création : SKILL.md (~1 400 tokens) + format.md (~800) + le document. Pas d'appel
de modèle supplémentaire ni d'agent ; le script est facultatif et local au bac à sable.
