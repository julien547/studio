# Premier lot Qwen — Animalis

**11 exemples préparés, à relire. Ce dossier n’est pas un dataset prêt à lancer.**
Il contient un seul bâtiment : Animalis, 70 boulevard de Grenelle, Paris.
Les autres plans annoncés par Julien permettront de compléter validation et test.

## Ce qui est fourni

- `revue.html` : ouvrir dans un navigateur pour examiner les détails et les réponses.
- `releve-source.png` : rendu du relevé fourni `RELEVEDEUX.pdf`, sans redessin.
- `images/` : 11 recadrages PNG de ce relevé, sans retouche de contenu.
- `corrections.json` : corrections explicitement données dans la conversation et
  régions de la revue antérieure. Ces régions restent à vérifier visuellement.
- `draft-examples.json` : provenance, recadrage exact en pixels, empreinte du PDF
  d’origine, groupe bâtiment et champs pour l’API des exemples.
- `qwen-draft.jsonl` : conversations au format image/messages/split, toutes en train.
- `manifest.json` : empreintes SHA-256 de tous les fichiers du dossier.

Répartition : **5 VEI, 2 PCF, 2 exemples extincteurs, 1 exclusion et 1 indéterminé**.
Les réponses enseignent une désignation et une consigne, pas une implantation.
Tous les `anchor` sont nuls : aucune coordonnée non vérifiée ne devient une vérité
d’entraînement. Le cadre du recadrage ne représente pas le point de pose.

Les conventions spécifiques sont incluses dans la question : exclusion de la zone 5,
zone 15 laissée indéterminée, deux extincteurs confirmés près de la réserve et
désignations VEI propres à ce dossier. Le nombre de deux extincteurs vient de la
correction utilisateur du plan, pas d’un comptage inventé sur le seul extrait.
On ne généralise pas « PI = VEI » à tous les plans. Le choix « extincteur portatif
sans distinction » et la distinction PCF/extincteur sont conservés.

## Compléter avec les nouveaux plans

Prévoir, pour au moins **deux autres bâtiments indépendants**, le relevé annoté
d’origine et son plan corrigé/validé (PDF lisible, AI si disponible). Identifier
le bâtiment, ses niveaux et les corrections retenues. Deux niveaux, deux copies,
des recadrages ou des révisions du même bâtiment ne constituent pas deux groupes.

Tout Animalis reste en entraînement. Affecter un autre bâtiment à la validation et
un troisième au test ; si plusieurs documents appartiennent au même bâtiment,
les conserver ensemble. Ne pas renommer artificiellement un bâtiment pour faire
passer le contrôle. Trois groupes constituent un minimum technique de recette,
pas un volume suffisant pour démontrer la qualité du modèle en production.

## Import dans DOEMO — par la session qui gère le serveur

Cette préparation n’a effectué aucune écriture sur OVH ou RunPod.

1. Utiliser **un seul projet Animalis**, avec son adresse réelle, et vérifier son
   autorisation de réutilisation pour l’entraînement. La demande de préparation
   dans le chat n’a pas modifié le consentement enregistré dans l’application.
2. Importer chaque PNG `images/` comme document du même projet (role `survey`).
   Ils sont des sources détaillées ; ne pas utiliser les champs de l’exemple avec
   une autre image ou avec le plan complet. Garder les liens de provenance du pack.
3. Pour chaque élément de `draft-examples.json`, reprendre `example_fields`, ajouter
   `project_id` et l’ID du document PNG correspondant, puis créer via
   `POST /projects/training/examples` avec une session administrateur authentifiée.
   L’exemple doit rester **draft**. Le fichier brut n’est pas un import automatique
   de la page ; ne pas le déposer dans l’import des résultats IA.
4. Relire chaque image, convention et interprétation dans Entraînement → Qwen.
   Corriger ou rejeter les propositions avant validation. Aucune validation
   administrateur n’a été fabriquée par le script de préparation.
5. Ajouter les exemples des autres bâtiments, les valider, créer le dataset Qwen
   puis l’exporter depuis DOEMO. L’export produira `examples.json`, `qwen.jsonl` et
   les images avec la séparation par bâtiment/document. Vérifier la composition
   effective des trois lots avant toute recette GPU.

Ne pas renommer `qwen-draft.jsonl` pour contourner l’export : les lots validation/test
sont absents et aucun entraînement ne doit être lancé avec ce seul pack.
La recette reste décrite dans [ENTRAINEMENT-QWEN.md](../../docs/ENTRAINEMENT-QWEN.md).

## Reproduire localement

Depuis la racine du dépôt, avec Python et Pillow :

```sh
python releves/scripts/prepare-qwen-animalis.py
```

Le script lit seulement le relevé et les corrections locaux, régénère les détails,
les conversations et la revue, puis recalcule le manifeste. Il n’utilise aucune
API IA et ne modifie aucun service ni aucune base de données.
