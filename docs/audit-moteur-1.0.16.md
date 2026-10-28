# Référence Illustrator 1.0.16

Archive reçue : `DOEMO-Generateur-1.0.16 (1).zip` (4 512 510 octets).
SHA-256 : `2ebe6dc98253d4731cbbd26b8e5e4f66d6e65fc3fb529627f77664af9865a6bf`.
Les 43 empreintes du manifeste correspondent aux fichiers livrés. Les 137 tests
fournis ont été exécutés avec succès, ainsi que le contrôle ES3. Il s'agit de
tests Node/DOM simulé, pas d'une nouvelle exécution Illustrator dans cette session.

Changements vérifiés depuis 1.0.14 :

- distinction entre panneaux de sortie/évacuation (lecture droite) et véritables
  flèches directionnelles (rotation avec le bâtiment) ; ne plus classer tout
  symbole contenant « sortie » comme directionnel ;
- masquage des codes PEV/PIV/PEH/PIH, y compris celui du VEI actif, avec maintien
  de la pastille et de son trait ;
- logo séparé du dessin, masque et proportions conservés, placement droit en
  bas à droite ; sur PE, centrage sous la colonne Prévention ;
- utilisation plus complète de la zone utile pour PI ;
- préparation/réutilisation de la légende en mémoire et contrôles natifs consolidés.

## Trois sorties natives et rapport reçus

Le rapport fourni annonce `version: 1.0.16`, `complete`, trois résultats
`ai-saved`, `sourceUnchanged: true` et 111 113 ms au total. Les PE restent à
−90°, échelle 72,7528 %. Le PI est à 180°, échelle 75,5377 %.
Ces valeurs viennent du rapport livré, pas d'une génération locale.

Les représentations PDF embarquées dans les trois AI ont été ouvertes et rendues.
Les vues PE-02 et PI montrent le logo droit en bas à droite, une seule pastille
visible et les codes VEI absents de l'extraction de texte. Les panneaux de sortie
sont droits. Ces observations ne remplacent pas une comparaison géométrique
exhaustive de tous les équipements avec le BAT original.

Empreintes des AI :

- VEI-01 PE : `355e831f8035ccbace6762dcf30a80e449c09d6c3d2fb992c8f449ac0aa70962` ;
- VEI-02 PE : `428a7a3cf317e22acd8be30e0b1f080034fcc872369428c9c57d0bcb841a4ec4` ;
- VEI-03 PI : `a2eed8140368d0ffb599b70f86ddce6f82d9f73b9850e3d9e282fb606d123e24`.

## Lot PDF de référence

Un ZIP privé `DOEMO-reference-1.0.16-3-PDF.zip` contient les trois PDF extraits de
ces sorties AI. Les données privées de réédition Illustrator sont retirées,
sans rasterisation. Les empreintes des ressources graphiques sont conservées
et les trois rendus sont identiques aux AI à 144 dpi. Les AI restent inchangés.

**Ce lot vient des sorties Illustrator fournies, pas du moteur serveur depuis
le BAT.** Il ne doit pas être présenté comme preuve que la génération autonome
de Studio est terminée. Les fichiers clients et ce ZIP restent hors Git.

Les trois PDF exportés et fournis ensuite par Julien sont les références
de comparaison. Chacun contient une page A3 portrait avec des tracés vectoriels.
À 144 dpi, les deux PE ont exactement les mêmes pixels que les représentations
PDF des AI. Pour le PI, 269 pixels sur 4 011 288 diffèrent, dans la zone du mot
« BUREAU » (repère de rendu depuis le haut : x 563–584,5 pt, y 415–419,5 pt).
Le texte extrait est identique dans les trois cas. Le PI n'est donc pas déclaré
strictement identique ; l'origine de cette différence n'est pas déterminée.

Empreintes des PDF fournis :

- VEI-01 PE : `7771c6a3ca7e4200e4101066ac4137e947eb9a6f9e6094846cb97dc7611a9c48` ;
- VEI-02 PE : `a374c6210ce4e337b3687475f8a179f65d881143627ae13c3ba84fe2e025e122` ;
- VEI-03 PI : `b2484c41b645f54171f09831c5e317d900ca4f5df80b24f35e8ad6f857142a08`.

La 1.0.16 ne contient pas encore l'export structuré décrit dans
`contrat-export-structure.md`. Les JSX nécessitent le DOM Illustrator. Pour
générer le lot sur le serveur sans masquer des murs ni tourner les mauvais
objets, il manque encore une association vérifiée entre chaque composant
identifié et ses tracés PDF complets. La demande de choix entre export structuré
et poursuite de l'analyse des PDF actuels reste ouverte auprès de Julien.
