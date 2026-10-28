# Inspection des trames PE et PI A3 verticales

Mise à jour : le moteur unifié 1.0.13 a été reçu après cette inspection. Les
premiers essais de composition vectorielle sont décrits dans le
[rapport actuel](audit-moteur-1.0.13.md) ; ils restent non conformes pour production.

## Résultat

`PI-A3-V.pdf` et `PE-A3-V.pdf` sont lisibles avec pypdf 6.10.0 et PyMuPDF 1.26.6. Chacune contient une page A3 verticale de 841,89 × 1190,55 points, sans rotation de page, sans chiffrement et sans annotation. Les aperçus ont été examinés visuellement.

Les éléments fixes sont vectoriels : bandeau rouge d'intervention pour PI, bandeau vert d'évacuation et consignes inférieures pour PE. Aucune ressource image n'a été recensée par le moteur d'inspection. Leurs textes et tracés ne doivent pas être reconstitués.

Les fichiers peuvent servir à l'essai technique. Ils ne sont pas approuvés pour la production : ils comportent un filigrane `SPECIMEN` et une référence de commande antérieure. Aucun contenu de ces fichiers n'a été modifié.

## Intégrité des sources

| Fichier | Taille en octets | SHA-256 |
| --- | --- | --- |
| `PI-A3-V.pdf` | 502 355 | `6869fd21df0ccb2eb3492319e8f5bd91b7870a143d669d21c9e59f491dc324dd` |
| `PE-A3-V.pdf` | 722 294 | `cea18b01dc11e9cd3cf5e328e6fa952fa3b51be036dc10e44a49ffb905e66537` |

Les empreintes ont été revérifiées après inspection. Les originaux et les aperçus de diagnostic sont conservés hors du dépôt source.

## Zones candidates pour ZONE_PLAN

Un grand rectangle blanc sans remplissage, de contour blanc de 1 point, est présent dans chaque trame. Il appartient au calque de date/conception. Il pourrait servir de délimitation de zone utile, mais n'est pas identifié explicitement comme `ZONE_PLAN` dans les éléments examinés.

Les coordonnées suivantes sont relevées dans le PDF, en points, avec origine en bas à gauche et Y croissant vers le haut. Les valeurs affichées sont arrondies ; le relevé détaillé est conservé dans le catalogue d'inspection.

| Trame | x min | y min | x max | y max | Dimensions approximatives |
| --- | --- | --- | --- | --- | --- |
| PI-A3-V | 28,578 | 126,004 | 813,775 | 974,702 | 277 × 299,402 mm |
| PE-A3-V | 28,346 | 194,299 | 813,543 | 979,496 | 277 × 277 mm |

Pour l'interface navigateur avec origine en haut à gauche, les limites correspondantes sont :

- PI : `(28,578 ; 215,848 ; 813,775 ; 1064,546)`.
- PE : `(28,346 ; 211,054 ; 813,543 ; 996,251)`.

Le rectangle PE se termine avant le bloc inférieur des consignes. La présence de ces rectangles donne une piste précise pour la configuration, sans prouver que les scripts les utilisent. Les marges de production ne sont pas encore connues. Le catalogue conserve donc `zone_plan: null`, des zones candidates non confirmées et `active_for_production: false`.

## Ressources à préserver

| Propriété observée | PI | PE |
| --- | --- | --- |
| Groupes de contenu optionnel | 15 | 14 |
| Enregistrements de dessin dans la visibilité par défaut | 62 | 844 |
| Ressources image recensées | 0 | 0 |
| Ressources de police recensées | 2 | 2 |
| Form XObjects recensés | 1 | 2 |
| Calques désactivés par défaut | Cadre, Trous de percage, EXT | Cadre, Trous de percage |

Les Form XObjects examinés comportent des groupes de transparence. Le futur moteur doit conserver ces ressources et la visibilité des calques. Une simple fusion des opérateurs de pages ne suffit pas à démontrer que les références de calques et leurs paramètres de visibilité sont correctement transférés.

La trame PI porte une référence datée du 10 juillet 2026 ; la PE porte une référence datée du 20 décembre 2024. Elles sont conservées pour le test. Leur remplacement éventuel relève d'une règle métier à définir, et ne doit pas être effectué silencieusement sur les références originales.

## Préparation du premier test

Les pièces PDF nécessaires sont désormais disponibles : un BAT réel, une trame PI/V et une trame PE/V. Le catalogue est un relevé d'inspection, pas une configuration de production activée.

Le BAT contient deux étiquettes `PEV` et une `PIV`. La correspondance présumée est donc deux déclinaisons sur PE-A3-V et une sur PI-A3-V, sous réserve des conventions confirmées dans les scripts. Les trois repères devront être associés à leurs pastilles, lignes de rappel, pointes et étiquettes.

Le cahier des charges impose la lecture intégrale des trois scripts JSX avant le développement du moteur. Ils restent manquants. Ils doivent notamment préciser le dessin à extraire du BAT déjà composé, la recherche de zone utile et le traitement des éléments de présentation. Insérer toute la page du BAT dans une trame créerait des bandeaux et informations en double ; cela ne constituerait pas le test métier demandé.

**Contrôles réalisés :** lecture des deux PDF, dimensions, ressources, calques, rendu visuel, rectangles candidats et intégrité des originaux.

**Contrôles non réalisés :** composition BAT/trame, rotation des VEI, exclusion des autres VEI, contre-rotation, validation de marges et conformité d'un PDF généré. Aucun PDF de production n'est annoncé à ce stade.
