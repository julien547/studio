# Import des axes PDF natifs — livraison 0.3.7

Un mur dessiné par un trait plein dans le PDF ne doit pas nécessiter une seconde
ligne pour être récupéré. L’import conserve maintenant ce trait sur son propre axe,
sous forme d’une proposition éditable. L’export reste un trait noir ouvert, sans
remplissage. Une ouverture interrompt le trait.

## Comportement

- Chaque segment droit admissible d’un tracé ouvert fournit un axe. Les sous-tracés
  séparés restent séparés ; ni les coupures ni les extrémités ne sont raccordées.
- Un rectangle allongé simple, rempli ou dessiné par son contour, fournit sa seule
  médiane. Ses quatre bords ne deviennent pas quatre murs.
- Deux traits indépendants, même proches, ne sont plus appariés automatiquement
  comme les faces d’un mur. Le panneau **Doubles axes possibles** permet au
  dessinateur de choisir la correction ou de confirmer deux murs distincts.
- La peinture répétée d’un axe exactement identique est regroupée, avec toutes
  ses provenances. Aucun moyennage ni raccordement entre axes voisins.
- Pour un trait natif, l’épaisseur physique reste inconnue. La largeur graphique
  source est conservée dans les preuves ; elle ne devient pas une dimension du
  bâtiment. Pour un rectangle, la largeur observée reste en unités du document.
- Tous les axes commencent en attente, avec une confiance sémantique de zéro.
  Leur présence ne prouve pas qu’il s’agit de murs. L’échelle reste non validée.

Les coordonnées tiennent compte de la matrice du tracé, du recadrage et de la
rotation PDF. L’orientation du document original est préservée. Les nouveaux
imports utilisent ce comportement ; les projets et corrections déjà enregistrés
ne sont pas recalculés.

## Limites visibles dans l’éditeur

Le volet **Import à contrôler** affiche les avertissements du niveau courant.
Le plan original et les tracés bruts restent disponibles dans le projet JSON.

L’extraction native accepte les peintures opaques sombres et presque neutres
(canaux RGB inférieurs à 180, écart inférieur à 30), et les segments d’au moins
12 unités du document. Les rectangles doivent être simples, orthogonaux, au
moins quatre fois plus longs que larges, avec une largeur au plus égale à 24
unités. Ces seuils sont géométriques et ne représentent aucune mesure métrique.

Les pointillés, courbes, formes complexes ou composées, remplissages comportant
des trous, peintures colorées ou transparentes et chemins découpés ne fournissent
pas d’axe natif automatique. Les Form XObjects sont également différés : leurs
matrices sont récupérées, mais le découpage par leur boîte et les effets de groupe
ne sont pas suffisamment interprétés pour reconstruire un mur directement.
Certains PDF de CAO peuvent donc produire peu ou pas d’axes : les murs manquants
doivent être redessinés ou traités dans une future prise en charge de ces formes.

Une page purement vectorielle ne repasse pas par l’analyse des pixels pour
contourner ces exclusions. La récupération native n’analyse pas encore toutes
les occultations par des objets peints ensuite, masques ou modes de fusion :
**vérifier chaque proposition sur le plan rendu avant de l’approuver**.

Une page mêlant images et axes natifs utilise les deux sources, avec la méthode
`mixed` dans le JSON. L’analyse raster porte sur la page rendue entière : elle
peut produire des doublons, des annotations ou des candidats issus de chemins
exclus de l’extraction native. Aucun de ces candidats n’est approuvé. Contrôler
les doubles axes, les passages et les objets manquants avant export.
Une page uniquement scannée conserve le traitement raster expérimental précédent.

## Installation et recette

Suivre [INSTALLATION-CONNEXION-IA.md](../../INSTALLATION-CONNEXION-IA.md) pour
actualiser le service OVH et `redessin/editor.js` depuis le même commit de
`feat/redessin-ovh-tests`. Un worker RunPod 0.3.4 déjà installé reste compatible.
Préserver le menu, l’iframe, l’absence de bandeau et les règles Apache de
[l’avertissement de production actuel](https://github.com/julien547/studio/blob/main/AVERTISSEMENT-MODIFICATIONS-STUDIO.md).

Dans un environnement de recette avec les dépendances `test,service` et Node.js
22 ou supérieur :

```bash
python3 reconstruction/ovh/build_web.py
python -m pytest reconstruction/tests -q
```

Le [test navigateur publié](../tests/browser/median-openings.cjs) s’exécute avec
Playwright selon les instructions du [README](../README.md#vérification).
Il contrôle notamment les avertissements visibles, l’export d’un axe noir
interrompu aux ouvertures et l’absence de bandeau dans l’éditeur intégré.

Après installation, créer des projets de recette distincts :

1. Importer un PDF contenant un seul trait noir plein : un axe proposé, épaisseur
   inconnue, aucune validation automatique. Vérifier sa position sur la référence.
2. Importer deux morceaux colinéaires séparés : conserver la coupure ; aucun
   trait ne doit relier les morceaux dans le SVG validé après revue.
3. Importer deux lignes parallèles : contrôler la paire, puis choisir une médiane
   seulement si elles représentent réellement les deux faces du même mur.
4. Importer un rectangle long plein : une seule médiane, puis vérifier que la
   forme correspond effectivement à un mur et non à un équipement.
5. Vérifier qu’un PDF découpé ou complexe signale les limites de récupération.
   Comparer les murs manquants avec la référence avant toute validation.
6. Réouvrir un ancien projet corrigé : sa géométrie et ses validations restent
   celles du projet enregistré.

Les 168 tests Python passent localement, dont 24 nouveaux cas sur des PDF générés.
Le parcours navigateur synthétique passe. La page 1 du scan de référence garde
les 381 propositions antérieures, sans changement géométrique et sans approbation.
Ce résultat ne mesure pas leur précision architecturale. Aucun PDF client,
poids de modèle ou secret n’est inclus dans le dépôt.

Cette livraison ne vérifie pas les GPU RunPod ni Adobe Illustrator. Le raccordement
réel des trois IA, leurs inférences et la qualification du modèle spécialisé
restent à effectuer avec les accès des sessions responsables.
