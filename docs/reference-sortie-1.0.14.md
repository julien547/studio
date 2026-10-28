# Sortie Illustrator 1.0.14 reçue

Julien a fourni `CO26100364-1-VEI-02-PE-A3-V.pdf` et `rapport.json` le 28 octobre
2026 comme référence, en précisant que **l'emplacement du logo client reste à
corriger dans l'autre session**. Ne pas traiter ce placement comme une cible
définitive. Cette session n'a pas modifié le logo ni ces fichiers.

Empreintes des fichiers reçus :

- PDF : `17bbc1c06e09ee7963be30c5351def0b5999fae8cae8cb5aedd4ee6ceb6d895d` ;
- rapport : `e668c36524e8fcf816f7e23aadb1a83d45e3b07d56c77f4b546e1da7e00a026f`.

## Rapport fourni

Le JSON annonce la version 1.0.14, le statut `complete`,
`sourceUnchanged: true`, trois résultats `ai-saved` et une durée totale de
192 534 ms. Ces valeurs sont celles du rapport, pas d'une exécution native
réalisée dans cette session.

| VEI du rapport | Trame | Rotation | Échelle |
| --- | --- | ---: | ---: |
| 1 | PE-A3-V | −90° | 72,7528 % |
| 2 | PE-A3-V | −90° | 72,7528 % |
| 3 | PI-A3-V | 180° | 58,2966 % |

Pour chaque sortie, le rapport compte 27 symboles visibles dans la source,
25 conservés visibles et imprimables, les deux autres pastilles VEI masquées,
aucune visibilité inattendue et aucun symbole hors page. Les neuf extincteurs
EXT y sont visibles et imprimables. `outputPrinting` consigne l'activation
d'impression de EXT dans les copies. Onze lignes de légende sont rapportées.

## PDF VEI-02 examiné

Le PDF a été ouvert et rendu : une page A3 portrait, un seul bandeau évacuation,
une seule pastille VEI visible, la pointe de sa flèche vers le haut, les textes
de lecture droits, les équipements visibles, le niveau sous le bâtiment, la
légende au-dessous et les consignes de la trame en bas. Le logo apparaît tourné
sur la gauche, conformément au défaut signalé par Julien.

Cette vue fournit enfin une référence visuelle réelle distincte du diagnostic
incorrect. Elle ne démontre pas une superposition géométrique complète avec le
BAT, ni le rendu des sorties VEI-01 et VEI-03 qui n'ont pas été jointes. Le rapport
nomme des fichiers AI ; il ne contient pas d'empreinte attestant que le PDF joint
est exactement leur export. Le lien est fourni par l'utilisateur et le nom du
fichier, pas par une vérification cryptographique du rapport.

## Utilisation dans Studio

Ce résultat confirme le parcours attendu : **tous les VEI du BAT donnent chacun
une sortie, avec trame automatique et un seul VEI orienté**. Le dossier client
est choisi une seule fois dans l'application. Le moteur serveur doit reproduire
ce comportement ; sa préparation de lot ne constitue pas encore le rendu.

Les corrections du logo sont poursuivies dans l'autre session. Une nouvelle
version et sa sortie pourront remplacer cette référence sans changer le choix
du dossier client ni la règle d'un plan par VEI.
