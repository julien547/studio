# Qwen — mairie de Villeneuve-lès-Béziers

**12 propositions pour le groupe de test, à relire.** Site identifié sur le plan :
Place Michel Solans, 34420 Villeneuve-lès-Béziers, mairie/médiathèque, niveaux 0 à 3.

Les fichiers se trouvent déjà dans GitHub, branche `codex/ai-training-backend`,
dossier `entrainement`, commit source `11c28cb61681f2f5d6a26ab232f1b9c3b570d6a3` :

- `MAIRIE DE VLB GAUCHE.pdf` : 1 page, relevé partiel avec RDC et étages.
- `MAIRIE DE VLB PLAN DROITE.pdf` : 2 pages, relevé complémentaire et recouvrements.
- `MAIRIE DE VLB PLAN.jpg` : source supplémentaire conservée, non utilisée pour
  fabriquer des exemples supplémentaires du même contenu.
- `villeneuve.pdf` : plan mis au propre, référence CO26100272-1 du 28 octobre 2026,
  marqué SPÉCIMEN ; référence explicitement confirmée par Julien :
  « Oui, référence validée ». Les réponses proposées restent à relire.

Les relevés gauche et droite partagent de nombreuses zones. Tout le dossier,
y compris les reprises en JPEG et les niveaux, appartient à **un seul groupe**.
Le site peut constituer le troisième groupe après Animalis et Cotonnière.
Il ne prouve pas à lui seul la qualité d’un modèle en production.

## Contenu et portée

`revue.html` présente 12 détails : 3 VEI, 3 extincteurs portatifs, 2 commandes de
désenfumage, un déclencheur d’alarme incendie, un SSI, un ascenseur et un arrêt
d’urgence électrique. Les réponses sont proposées par lecture des relevés et
comparaison au plan mis au propre. Elles restent des brouillons à vérifier.

La légende ancienne décrit les triangles rouges comme des emplacements éventuels
d’extincteurs. Les trois propositions correspondantes s’appuient donc aussi sur
les extincteurs figurant dans `villeneuve.pdf`, pas seulement sur leur couleur.
Les équipements dessinés à proximité les uns des autres sont ciblés dans le texte
de la question ; aucune position n’est extraite du centre du recadrage.

Les réponses portent sur la désignation : `anchor=null`, `quantity=null`.
Aucun ancrage ni relevé architectural validé n’est produit par ces exemples.
Le choix du fichier de pictogramme SAI précis reste séparé.

`draft-examples.json` conserve chemin Git, commit, SHA-256 du PDF d’origine,
page, taille du rendu, rectangle de recadrage et champs API de chaque proposition.
`qwen-draft.jsonl` propose `split=test` ; `manifest.json` vérifie les fichiers du lot.
Les sources PDF/JPEG restent dans `entrainement/` à la racine du dépôt.

## Suite

Importer les détails PNG `images/villeneuve-*.png`
dans un unique projet mairie avec l’adresse réelle, puis créer les exemples en
brouillon avec `example_fields` et les identifiants de projet/document correspondants.
Voir la procédure d’import du [lot Animalis](../qwen-animalis-v1/README.md).
Relire les réponses et enregistrer l’autorisation du projet avant validation.

Créer ensuite le dataset des trois sites et contrôler son export. L’algorithme
actuel affecte les groupes selon un ordre déterministe : la réservation de
Villeneuve au test est proposée ici, pas imposée à l’API. Vérifier les lots obtenus.
Aucun recadrage ou duplicata d’un site ne doit passer dans plusieurs lots.

Reproduction locale avec les dépendances backend, depuis la racine du dépôt :

```sh
python releves/scripts/prepare-qwen-villeneuve.py
```

Le script refuse une source dont l’empreinte a changé. Il ne contacte aucun serveur,
ne lance aucun modèle et n’enregistre aucune validation humaine.
