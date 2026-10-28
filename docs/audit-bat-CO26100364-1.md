# Inspection du BAT réel CO26100364-1

Mise à jour après cet audit : deux trames PDF séparées et le moteur unifié 1.0.13 ont été reçus et inspectés. Voir le [rapport des trames](audit-trames-A3-V.md) et le [rapport actuel du moteur](audit-moteur-1.0.13.md). Les mentions d'attente des fichiers ci-dessous décrivent l'état lors de l'inspection initiale du BAT.

## Conclusion

Le BAT est exploitable comme document PDF : le fichier `.ai` contient une représentation PDF 1.6 lisible. Le bâtiment comporte des tracés vectoriels et trois repères « VOUS ÊTES ICI » sont visibles. La composition avec une trame et la fidélité des transformations individuelles ne sont pas encore démontrées.

Les trois scripts JSX métier ne sont pas disponibles. L'archive `trames 2.zip` a été jointe, mais son transfert est refusé par l'outil au-delà de 32 Mio ; son contenu, sa structure et ses formats n'ont donc pas été inspectés. Aucun export de trame n'a été inventé ni remplacé par un cadre reconstitué depuis le BAT.

## Documents et intégrité

| Fichier | Taille | SHA-256 |
| --- | --- | --- |
| `CO26100364-1.pdf` | 1 702 289 octets | `9e0d3f71a6efb0a8bb6de43ff717a7fd0c6393943227fbcc724dbac89bba7d39` |
| `CO26100364-1.ai` | 1 702 528 octets | `0292ec607eb32285f31824379c243cdd59312be489c70e4befdf3ef0fdb6ae8d` |

Les deux fichiers ont été ouverts sans modification. Leurs empreintes ont été contrôlées à nouveau après inspection. Les originaux restent hors du dépôt source.

Outils d'inspection présents dans l'environnement : pypdf 6.10.0 et PyMuPDF 1.26.6. PyMuPDF a uniquement servi à l'inspection et au rendu de diagnostic dans cette session ; cela ne constitue pas un choix de dépendance du produit. Son régime de licence AGPL/commercial doit être évalué avant toute éventuelle intégration. Aucune bibliothèque nouvelle n'a été installée.

## Contrôles exécutés

- Ouverture des deux fichiers avec pypdf en mode strict et avec PyMuPDF : réussie, une page chacun, sans chiffrement.
- Dimensions : 841,89 × 1190,55 points, soit environ 297 × 420 mm, A3 portrait. Rotation de page : 0°.
- Le contenu décodé du flux de dessin de page est identique entre AI et PDF. Cette comparaison ne signifie pas que tous les objets ou toutes les métadonnées des fichiers sont identiques.
- Rendu des deux documents à 108 dpi : empreintes des pixels identiques, avec le même moteur et la même configuration. Cela ne valide pas tous les moteurs de rendu ni la fidélité d'une future transformation.
- Inspection visuelle du rendu du PDF à 72 dpi : bâtiment, bandeau, légende, textes, trois VEI et filigrane « SPECIMEN » visibles.
- Aucun PDF de déclinaison n'a été généré. Aucune contre-rotation, suppression de VEI ou composition avec une trame n'a été testée.

Les rendus bitmap servent uniquement à l'audit visuel. Ils ne sont pas des fichiers de production ni une étape de rasterisation des sources.

## Structure observée

Le moteur d'inspection recense 342 enregistrements de dessin dans l'état de visibilité par défaut, une ressource image, cinq ressources de police avec les ressources imbriquées, et deux Form XObjects. Le nombre d'enregistrements de dessin n'est pas un nombre d'objets Illustrator ou d'objets métier.

Les tracés visibles se répartissent notamment entre `Fond de plan`, `Relevé`, `Pictos`, `Legende` et `Remplissage`. Une image CMJN de 2481 × 3508 pixels est placée dans la zone basse du document et appartient au calque `Scan`. Sa présence ne signifie pas que le bâtiment est une image ; le document est mixte et ses tracés doivent être préservés tels quels.

Seize groupes de contenu optionnel sont déclarés :

`Fond de plan`, `Cadre`, `Trous de percage`, `Specimen`, `Date et N° de Conception`, `Legende`, `Scan`, `Remplissage`, `MEUBLE`, `Relevé`, `Pictos`, `EXT`, `texte`, `Niveau`, `Adresse`, `PSI`.

Les groupes `Cadre`, `Trous de percage` et `EXT` sont désactivés dans la configuration PDF par défaut. Les futurs traitements devront préserver et expliciter cette visibilité ; ils ne doivent pas réactiver des objets cachés par inadvertance.

Les blocs de contenu marqué ne sont pas tous autonomes : des états graphiques `q/Q` et des délimitations de texte dépassent certaines limites de calque. Extraire uniquement les opérateurs entre `BDC` et `EMC` n'est donc pas une méthode suffisante pour recomposer fidèlement le document.

Le Form XObject `Fm0`, associé au filigrane, utilise un groupe de transparence. Il doit rester inchangé tant qu'aucune règle métier explicite n'autorise une autre présentation. La présence du mot « SPECIMEN » interdit de considérer ce BAT d'essai comme une production validée.

## Repères VEI

Trois repères sont visibles et trois étiquettes sont extractibles : deux `PEV` et une `PIV`. Leur interprétation comme PE/V et PI/V est cohérente avec le cahier des charges mais doit être confirmée par les scripts et les conventions DOEMO.

Le Form XObject `Fm1` est invoqué trois fois dans le calque `Pictos`. Il représente la pastille vectorielle « VOUS ÊTES ICI ». Son texte est constitué de tracés : il ne contient ni opérateur texte ni ressource de police. Il ne doit pas être reconstruit par OCR.

Les traits de rappel, les pointes de flèche et les étiquettes PE/PI sont distincts de cette pastille. Le calque `Pictos` contient également les pictogrammes incendie et les flèches de cheminement. Masquer tout ce calque supprimerait donc des éléments qui doivent rester présents.

Les deux repères de gauche ont visuellement une pointe orientée à gauche ; le repère du bas a une pointe orientée vers le bas. Les lignes de rappel sont coudées : **la direction entre le centre de la pastille et la pointe n'est pas la direction de la flèche**. La détection doit examiner la pointe et son segment terminal.

Des tracés bleus distincts correspondant aux trois lignes de rappel ont été observés. Cela suggère une possibilité d'association géométrique, mais ne démontre pas encore la séparation sûre de l'ensemble pastille + rappel + pointe + étiquette. Aucune association par simple proximité n'a été validée.

## Textes et pictogrammes

Les étiquettes `PEV` et `PIV` ainsi qu'une partie de la légende s'extraient correctement. D'autres textes visibles se traduisent par des caractères de contrôle lors de l'extraction.

Les quatre polices référencées directement sur la page sont incorporées, mais n'ont pas de table `ToUnicode`. La police SourceSansVariable-Roman comporte un encodage personnalisé avec des noms de glyphes `gid...`. Une défaillance d'extraction Unicode n'est donc pas une absence du texte dans le rendu et ne justifie aucune réécriture.

La conservation des polices incorporées et des opérateurs peut permettre un rendu fidèle, mais l'identification sémantique automatique et les limites exactes des objets demandent une analyse supplémentaire. La rotation compensatrice des textes et des symboles n'est pas validée.

La page regroupe déjà le bâtiment, la légende, le bandeau, les coordonnées du site, le niveau et le filigrane. La limite du « dessin concerné » à transférer dans une autre trame doit être établie à partir des règles métier ; faire tourner toute la page déplacerait aussi les éléments de présentation.

## Décisions et suite

1. Recevoir et lire les trois scripts JSX avant de développer le moteur.
2. Fournir au moins une vraie trame PDF vectorielle. Pour le catalogue complet, répartir les trames en archives indépendantes inférieures à 32 Mo en conservant les chemins relatifs ; aucun volume d'une archive multipartie ne pourra être inspecté isolément.
3. Identifier la zone `ZONE_PLAN`, les marges et les éléments du BAT à conserver dans le dessin, sans suppression arbitraire du contenu graphique.
4. Vérifier la séparabilité des trois repères et des objets nécessitant une contre-rotation, en tenant compte des états graphiques, des ressources partagées et des calques désactivés.
5. Réaliser la première composition réelle et les contrôles de transformation, de contenu et de rendu avant de déclarer une déclinaison conforme.

**État final : audit du BAT avancé ; preuve de génération sur trame réelle en attente ; conformité de production non établie.**
