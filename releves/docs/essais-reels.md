# Essais sur les fichiers fournis — 28 octobre 2026

Ces essais concernent les fichiers effectivement reçus et l’archive déposée sur GitHub.
Aucun relevé client, BAT ou placement privé n’est ajouté au dépôt source.

## Bibliothèque SAI — test C

Les deux parties GitHub représentent 178 207 556 octets, réunies dans l’ordre `aa`, `ab`.
SHA-256 de l’archive réunie : `01f8702f33094659c3cb95e94f9a42a9a6b1cc6f344d2724a651c5c50fef2fde`.
L’import du manifeste DCX et de l’inventaire retrouve **290 ressources : 228 graphiques,
52 couleurs, 9 styles de caractères et 1 texte**. Les 290 identifiants, noms/types et
leurs groupes ont été comparés. **227 composants AI** ont été vérifiés et leurs **227
aperçus** rendus depuis leurs vraies ressources. Un graphique n’a pas de composant AI.
Aucune ressource n’est automatiquement approuvée comme pictogramme métier.

Le catalogue de métadonnées est fourni dans `releves/resources/sai-catalogue.json`.
Il décrit cet audit, ne remplace pas la réimportation des fichiers AI et ne constitue
pas une liste de correspondances métier approuvées. Les UUID et variantes restent distincts.

## Relevé réel — tests A/B adaptés

`2.pdf` est un PDF **scanné de cinq pages**, dimensions 1190,88 × 841,68 pt par page.
Le fichier `CO24060047-1.pdf` est **une seule page**, pas le `plan.pdf` à deux pages décrit.
Le BAT `CO24060047-1-HD.ai` est bien fourni ; son aperçu PDF comporte une page de
2383,94 × 1683,78 pt. Le BAT contient des données Illustrator natives. Cela ne dispense
pas d’un test dans Illustrator.

L’inspection visuelle des scans montre des annotations rouges de type **PE** et **PI**,
avec flèches. La page RDC porte notamment les mentions « 2 PI = Plan Intervention » et
« 12 PE = Plan Evacuation ». Ce sont des indications d’emplacements de plans, **pas des
extincteurs ou déclencheurs à inventer**. La page 5 est une photographie orientée de côté,
avec des pictogrammes déjà imprimés ; elle produit beaucoup de candidats parasites.
Les pages de niveaux portent un cartouche d’octobre 2025, le BAT porte une mise à jour
2024. Le même site/bâtiment est suggéré, mais l’identité de l’état architectural et
le recalage des différents niveaux **ne sont pas validés**.

L’essai automatique SIFT/RANSAC entre la page 1 du relevé et le BAT complet a
retourné **« Alignement automatique non fiable »**. Aucun alignement ni placement
n’a été accepté à sa place. Des points manuels répartis et un contrôle indépendant
restent nécessaires avant tout transfert de coordonnées.

Le mode local combine les pixels colorés, les composantes connexes, les formes et les
indices OCR. La première exécution contient les résultats suivants :

| Page | Zones candidates | Zones rouges | Équipements confirmés |
| --- | ---: | ---: | ---: |
| 1 | 87 | 15 | 0 |
| 2 | 107 | 12 | 0 |
| 3 | 82 | 23 | 0 |
| 4 | 101 | 51 | 0 |
| 5 | 246 | 61 | 0 |

**623 zones candidates au total ; zéro équipement confirmé et zéro placement natif
autorisé.** Il ne s’agit pas de 623 équipements reconnus. Les couleurs des numéros,
des portes, des végétaux et des pictogrammes imprimés produisent des faux positifs.
Les mots manuscrits ne sont pas lus de façon fiable par cet OCR ; aucune capacité
ou catégorie d’équipement n’est inventée. La revue JSON garde les boîtes et ancrages
inconnus, les sources/pages et les statuts à vérifier. L’export Illustrator reste bloqué.
Le moteur local seul n’est donc **pas validé pour une reconnaissance de production**.

Le fichier privé de revue réel est `/workspace/studio-releves-audit/revue-reelle.json`.
Le dossier est stocké en SQLite et peut être ouvert par son propriétaire de test
`audit-local`. Cet acteur est synthétique et ne remplace aucun compte Studio réel.
Aucun emplacement préfabriqué n’a été présenté comme un résultat de reconnaissance.

## IA et légende colorée — test D

L’utilisateur a choisi OpenAI ; ses exigences de clé, modèle et destination HTTPS
ont été enregistrées dans le nouveau brouillon. Aucune clé n’a été fournie, aucun appel
multimodal réel n’a été exécuté. Le fichier `3(1).pdf` à légende colorée n’a pas été
reçu ; le dictionnaire à sept couleurs décrit dans la demande n’est pas utilisé par défaut.
Ces deux validations restent à effectuer avec les prérequis correspondants.

## Illustrator — test E

Le script `DOEMO-Pose-Pictogrammes.jsx` et son cœur ES3 sont fournis pour Illustrator
2024+. Les tests automatisés du cœur vérifient SHA-256, le parsing strict sans `eval`,
le repère Illustrator, les chemins et la comparaison des placements existants. Ils
ne simulent pas une réussite du moteur Adobe. Aucun Illustrator sous licence n’est
exécutable dans ce cloud : import des groupes, sauvegarde AI native et réouverture
**non exécutés**. Aucun AI final n’a été fabriqué en renommant un PDF.

L’essai natif nécessitera un relevé avec ses équipements confirmés, des pictogrammes
SAI approuvés, un recalage accepté et un poste Illustrator sous licence. Les zones
PE/PI de ces scans ne constituent pas cette vérité terrain d’équipements incendie.

## Validation logicielle locale

- 30 tests du nouveau backend réussis, y compris isolation des projets, révisions,
  archives malveillantes, recalage, garde d’export, refus d’un PDF renommé AI et
  fidélité des octets du bundle vectoriel.
- 6 contrôles du cœur Illustrator et 3 contrôles du frontend réussis ; les deux
  fichiers Illustrator passent aussi l’analyse syntaxique ECMAScript 3.
- Compilation TypeScript/Vite réussie ; syntaxe des points d’entrée PHP vérifiée.
- Parcours Chromium sur le dossier réel : page, images, sélection d’annotations,
  extraits et catalogue vérifiés sans erreur JavaScript. Les captures sont dans
  `/workspace/studio-releves-audit/`, hors du dépôt source.
- 123 tests du moteur PDF existant réussis après récupération de la mise à jour
  déjà présente sur `main` ; son code n’est pas modifié par ce module.

Ces contrôles vérifient les fonctions développées, pas une réussite de reconnaissance
manuscrite de production ni une exécution d’Illustrator dans le cloud.
