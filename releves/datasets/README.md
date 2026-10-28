# Préparation des exemples Qwen

| Dossier | Source | Propositions | Affectation proposée | État |
| --- | --- | ---: | --- | --- |
| [Animalis](qwen-animalis-v1/README.md) | RELEVEDEUX.pdf et corrections du dessinateur | 11 | Entraînement | Recadrages/réponses à relire |
| [Cotonnière](qwen-cotonniere-v1/README.md) | 333333.pdf + CO26100349-1.pdf | 12 | Validation | Référence confirmée par Julien ; réponses à relire |
| [Villeneuve-lès-Béziers](qwen-villeneuve-v1/README.md) | Dossier GitHub `entrainement` ; mairie/médiathèque | 12 | Test | Référence confirmée par Julien ; réponses à relire |

**35 propositions, 3 groupes de sites, aucun dataset encore prêt pour la recette GPU.**
Les pages, niveaux et recadrages d’un site restent ensemble. Aucun exemple synthétique
ni validation humaine fictive ne remplace la revue des exemples. L’export actuel attribue
les groupes de façon déterministe : les affectations ci-dessus sont provisoires et
la composition réelle doit être vérifiée avant entraînement.

Chaque dossier contient une revue HTML, les images, la provenance et les réponses.
Les scripts de préparation sont locaux et n’accèdent ni à OVH ni à RunPod. L’import
par l’API existante, l’autorisation de réutilisation et la validation sont décrits
dans les README des lots. Les fichiers `qwen-draft.jsonl` ne sont pas des exports
d’entraînement validés. Aucune position de pose n’est enseignée par ces premières
propositions, qui portent sur les désignations et conventions métier.
