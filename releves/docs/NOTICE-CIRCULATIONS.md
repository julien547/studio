# Notice d’utilisation — vert des circulations

## Ce que cette version permet

Le module accepte la géométrie native d’un plan brut, propose des tracés à
qualifier, puis calcule des régions à partir des limites confirmées dans DOEMO
ou préparées dans Illustrator. Il propose leur catégorie à partir des textes et permet leur correction
dans DOEMO et prépare leur import sur un nouveau calque. Le connecteur enregistre
une **nouvelle copie AI native depuis Adobe Illustrator**, puis la rouvre pour
contrôler l’inventaire et les surfaces enregistrées.

**Statut : version de développement à recetter sur un poste Illustrator.** Les
tests locaux du calcul et de l’interface ne remplacent pas la première sauvegarde
native réelle. Aucun AI final n’a été produit ou rouvert par la session Linux.
Un fichier Illustrator brut, aux murs/portes non identifiés, n’est pas encore
traité de manière entièrement automatique. La qualification des limites et des
emprises peut maintenant se faire dans DOEMO, sans renommer les calques du AI.
Les propositions demandent une confirmation visuelle. Les masques et chemins
composés ambigus restent hors calcul, avec avertissement.

## 1. Installer les scripts sur le poste du dessinateur

Adobe Illustrator **2024 ou plus récent**, Windows ou macOS, est nécessaire.
Dans un même dossier, placer les cinq fichiers du dossier
[`releves/illustrator`](../illustrator/) :

1. `DOEMO-Exporter-Circulations.jsx`
2. `DOEMO-Importer-Circulations.jsx`
3. `circulations-native.js`
4. `circulations-core.js`
5. `doemo-core.js`

Conserver les fichiers téléchargés tels quels, en texte brut. Ne pas les recopier
dans TextEdit en texte enrichi : l’erreur `\rtf1` signifie que le fichier est RTF.
Lancer chaque JSX avec **Fichier → Scripts → Autre script…**. Les trois fichiers
`.js` sont des bibliothèques, pas des scripts à lancer seuls.

Le dossier peut être téléchargé avec le ZIP du dépôt GitHub, puis extrait.
Le déploiement de la page et du backend relève de la session serveur : voir
[INSTALLATION-CIRCULATIONS.md](INSTALLATION-CIRCULATIONS.md).

## 2. Choisir le mode de préparation

Garder le fichier d’origine intact. Enregistrer une **copie de préparation `.ai`**.
Les objets originaux y restent éditables : aucun aplatissement, aucune conversion
des textes, aucune rastérisation des murs.

**Plan brut :** enregistrer le AI, l’exporter directement avec le script puis
préparer les murs et les niveaux dans DOEMO (section 4). Il n’est plus nécessaire
de créer des calques `DOEMO:MUR` ou une emprise nommée pour pouvoir exporter.
Les repères Illustrator ordinaires sont ignorés ; les objets composés ou masqués
restent inventoriés mais exclus du calcul.

**Plan déjà préparé :** les noms d’objets ou de calques suivants restent reconnus :

| Nom | Rôle |
| --- | --- |
| `DOEMO:EMPRISE:RDC` | Contour polygonal fermé de l’emprise réelle du niveau RDC |
| `DOEMO:EMPRISE:R+1` | Contour fermé d’un autre niveau ; nom unique |
| `DOEMO:MUR` | Tracés architecturaux : murs et cloisons |
| `DOEMO:SEUIL` | Segment virtuel entre les deux jambages d’une porte |
| `DOEMO:PASSAGE` | Passage à laisser ouvert entre deux circulations |
| `DOEMO:OBSTACLE` | Contour fermé rempli d’un obstacle à soustraire |
| `DOEMO:VERT_EXISTANT` | Surfaces vertes existantes à conserver sans doublon |
| `DOEMO:FOND` | Facultatif : calque inférieur portant le fond blanc opaque |

Le rôle d’un calque est transmis à ses objets, sauf rôle plus précis donné à un
objet. Ne pas mettre textes, pictogrammes ou portes entières dans `DOEMO:MUR`.
Ne pas qualifier comme seuil un arc de débattement : le seuil est un segment
entre jambages. Le dessinateur doit vérifier ce segment.

Les contours de contrôle et les seuils ajoutés pour le calcul doivent être des
**repères non imprimants ou objets masqués**, conservés dans la copie de travail.
L’exporteur peut lire une emprise masquée et un seuil explicitement nommé masqué.
Le module ne crée pas de trait visible de seuil dans le calque vert.

Une emprise n’est pas le rectangle englobant du plan : elle suit le contour du
bâtiment. Chaque niveau doit tenir dans un plan de travail et posséder une
emprise distincte, sans chevauchement. Plusieurs niveaux peuvent partager un plan
de travail si leurs emprises ne se recouvrent pas. L’emprise de contrôle doit être
polygonale ; les courbes des murs sont subdivisées selon la tolérance choisie.

Si un grand fond blanc masque la future couche verte, le mettre dans un calque
`DOEMO:FOND`, sous toute l’architecture, dans cette copie de préparation. Le
connecteur place alors le vert au-dessus du fond et sous les autres calques.
Il refuse certains fonds opaques ambigus au lieu de livrer un vert invisible.

Enregistrer la copie `.ai` après préparation. Le script refuse les modifications
non enregistrées. Les liens d’images doivent être disponibles et les polices
résolues sur le poste.

## 3. Extraire la géométrie native

Dans Illustrator, ouvrir la copie de préparation et exécuter
`DOEMO-Exporter-Circulations.jsx`. Choisir un **nouveau** fichier JSON de sortie.

L’export comprend les plans de travail, les calques et objets, les poignées de
Bézier, les styles disponibles, les textes, les nuances et les empreintes de la
source. Les coordonnées sont celles du document Illustrator, en points,
avec l’axe Y dirigé vers le haut.

Le script n’enregistre pas de modification du plan. En l’absence d’emprise,
il exporte une source à préparer : aucune région n’est calculée tant qu’un
contour de niveau n’a pas été confirmé. Les textes sont ensuite affectés aux
régions par leur position.

## 4. Reconstruire dans DOEMO

Après installation du module, ouvrir **Circulations** depuis l’atelier ou accéder
à `/circulations/`. Choisir le projet puis importer le JSON extrait.

### Plan brut : préparer les murs et les niveaux

1. Choisir le **plan de travail** à examiner puis cliquer **Proposer les tracés à
   vérifier**. DOEMO repère des noms de calques architecturaux, des tracés sombres
   et allongés et des remplissages verts. Ce sont des indices, pas des rôles acquis.
2. Dans **Proposition à examiner**, choisir un tracé ; il apparaît en violet.
   Pour une sélection manuelle, utiliser **Sélectionner des tracés**, cliquer un
   trait et maintenir Majuscule pour en sélectionner plusieurs.
3. Choisir le **rôle confirmé** et cliquer **Confirmer le rôle des tracés**.
   Vérifier particulièrement les cotes, le mobilier et les symboles : leurs
   formes peuvent ressembler à des murs. Le vert d’une légende n’est pas une
   circulation existante.
4. Saisir le **nom du niveau**. Sélectionner un vrai contour fermé puis cliquer
   **Utiliser le contour sélectionné comme emprise**, ou **Tracer l’emprise réelle**
   et cliquer ses sommets. Confirmer le contour. Il doit rester dans le plan de
   travail et ne pas chevaucher un autre niveau. Pour remplacer une emprise,
   réutiliser exactement le même nom de niveau.
5. Pour séparer une pièce du couloir, choisir son niveau puis **Tracer un seuil
   entre jambages**. Cliquer les deux jambages et confirmer. À moins de 8 pixels
   d’un sommet natif, le clic s’y aimante pour éviter un petit interstice.
   Ne pas fermer un passage entre deux circulations. Aucun seuil n’est créé
   automatiquement et aucun trait de seuil n’est ajouté au AI final.
6. Utiliser **Revenir aux régions** pour contrôler les surfaces calculées.

Les propositions de contours viennent uniquement de boucles vectorielles
fermées existantes. Le contour d’une pièce ou du cartouche peut en faire partie :
confirmer l’emprise du bâtiment, jamais son simple rectangle englobant. Si le bon
contour n’existe pas, le tracer. Les chemins composés/masqués exclus doivent être
préparés dans Illustrator ; les qualifier comme murs depuis cette page est refusé.

Les limites et seuils créés dans DOEMO sont des données de calcul. Les coordonnées
et empreintes du AI source restent inchangées. **Annuler / Rétablir** fonctionne
aussi pour cette préparation. Modifier les limites après une correction humaine
demande confirmation : les régions sont recalculées et doivent être revues ;
les versions précédentes restent conservées dans l’historique.

### Règles du calcul

Dans « Règles de reconstruction », régler :

- les inclusions particulières : halls, escaliers, paliers, sas, extérieur dans
  l’emprise explicitement désignée ; elles sont désactivées par défaut ;
- la tolérance de subdivision des courbes, en points du document ;
- le seuil de confiance des propositions.

Le calcul forme les régions, retire les murs et obstacles et soustrait le vert
existant. Les frontières de seuil séparent le couloir des locaux voisins.
Les chemins `DOEMO:PASSAGE` ne ferment pas les régions. Les écarts entre traits
sont signalés ; la tolérance n’autorise pas une fermeture arbitraire.

Les bureaux, réserves, cuisines, sanitaires et locaux techniques sont exclus par
leurs libellés. Un hall n’est proposé comme circulation que si son inclusion est
activée. Une région contenant « Couloir » et « Bureau » reste indéterminée : il
faut vérifier ses séparations. Une zone accessible par une porte n’est pas, pour
cette seule raison, une circulation.

Les propositions fiables apparaissent en vert pâle, mais **toutes les surfaces
exportées nécessitent une validation du dessinateur** dans cette version.
Les couleurs de revue sont indicatives ; la nuance finale se règle séparément.

## 5. Corriger et valider

Cliquer à l’intérieur d’une région pour la sélectionner. Maintenir Majuscule pour
sélectionner plusieurs régions.

- **Ceci est une circulation** : valide la surface pour l’export.
- **Ceci n’est pas une circulation** : conserve une exclusion explicite.
- **Retirer du vert** : marque la zone rejetée, sans effacer la preuve de correction.
- **Fusionner la sélection** : réunit les surfaces du même niveau ; revalidation requise.
- **Déplacer les sommets** : déplacer les points violets puis appliquer le contour.
- **Ajouter une zone / Remplacer le contour** : sélectionner une région du niveau,
  tracer les sommets puis appliquer ; les murs, l’emprise et les autres régions
  restent contrôlés.
- **Ajouter un évidement** : tracer le contour à retirer ; le résultat est un vrai trou.
- **Séparer par une ligne** : tracer une ligne qui traverse la région puis appliquer.
- **Annuler / Rétablir** : restaure une révision du même document, en conservant l’historique.

Une correction de géométrie remet la nouvelle surface à l’état « proposée ».
Une surface hors emprise, sur un mur/obstacle ou superposée à une autre région est
refusée. Une zone rejetée n’est jamais réacceptée par l’import de libellés IA.
Les modifications sont enregistrées avec contrôle de version ; si un autre
dessinateur a modifié le document, recharger avant de poursuivre.

## 6. Choisir le vert

Vérifier les nuances déjà présentes dans Illustrator. Reprendre en priorité la
nuance de circulation de référence identifiée par le dessinateur. Sinon, saisir
la couleur de la charte du projet.

Dans « Nuance de sortie » :

- saisir les trois composantes RVB (0–255) ou les quatre composantes CMJN (0–100)
  selon le mode du document ;
- pour un ton direct, cocher l’option et renseigner le nom exact d’une nuance
  existant dans Illustrator ;
- définir l’opacité puis cliquer **Valider la nuance**.

Aucune nuance finale n’est validée par défaut. Le mode colorimétrique de la source
n’est pas changé. L’aperçu navigateur n’est pas une épreuve contractuelle CMJN/ton
direct : contrôler la copie finale dans Illustrator.

## 7. Enregistrer le nouveau fichier Illustrator

Cliquer **Préparer la copie Illustrator** : DOEMO télécharge
`circulations-validees.json`. C’est un fichier d’échange, pas le livrable AI.

Dans Illustrator :

1. Fermer la copie source après l’avoir enregistrée ; éviter un document ouvert
   avec des modifications non enregistrées.
2. Exécuter `DOEMO-Importer-Circulations.jsx`.
3. Choisir le JSON validé puis **le même AI source** utilisé pour l’extraction.
4. Choisir un nouveau nom, par exemple `MON_PLAN_CIRCULATIONS_VERT.ai`.

Le connecteur vérifie l’empreinte de la source, crée le calque
**DOEMO — VERT CIRCULATIONS**, ajoute des chemins composés fermés sans contour,
avec des évidements vectoriels, puis utilise `saveAs()` et
`IllustratorSaveOptions`. Il rouvre la copie et produit un rapport
`MON_PLAN_CIRCULATIONS_VERT.ai.circulations.json` après les contrôles.

Les surfaces restent modifiables individuellement et sont nommées par niveau.
Le fichier source n’est pas écrasé. Une relance exige une nouvelle copie de sortie.
Si un calque DOEMO existe, seuls ses objets identifiés et non modifiés peuvent être
remplacés. Une retouche manuelle ou un sous-calque non géré bloque l’import plutôt
que d’être supprimé silencieusement. Revalider ces changements avant régénération.

Si la réouverture échoue ou si l’inventaire diffère, la copie éventuellement créée
ne doit pas être livrée. Le fichier d’origine reste conservé.

## 8. Contrôle final obligatoire

Sur le vrai AI rouvert, vérifier chaque niveau : limites des murs, ouvertures,
pièces exclues, absence de débordement extérieur et de doublon, trous autour des
obstacles, lisibilité des textes et symboles, nuance, opacité et éditabilité des
surfaces. Comparer la copie au fichier de préparation.

Le rapport natif atteste les contrôles du connecteur lorsqu’il a réellement été
exécuté ; il ne prouve ni la conformité réglementaire ni l’absence de toute erreur
de reconnaissance. La première recette réelle reste à réaliser sur le poste Adobe.

## 9. Réutiliser les corrections pour apprendre

Après autorisation de réutilisation du projet par un administrateur, cliquer
**Conserver pour l’apprentissage**. Les acceptations et exclusions sont conservées
avec géométrie, source, niveau, catégorie, auteur, date et version.

Dans **Entraînement IA → Corrections des circulations**, l’administrateur peut
exporter la correction vectorielle ou créer un **exemple Qwen en brouillon**.
Le même AI doit avoir été importé comme relevé du projet pour associer son image.
Relire et valider ensuite l’exemple avant de constituer un dataset.

Aucune correction individuelle n’entraîne ou ne remplace un modèle en production.

## 10. Aide IA et limites actuelles

Le moteur utilise d’abord les textes vectoriels. Il peut importer les libellés
d’une analyse Qwen/PaddleOCR **déjà terminée sur exactement le même fichier** via
son identifiant. Ces libellés proposent une catégorie aux régions indéterminées ;
ils ne fournissent aucun nouveau contour et ne valident aucune surface.

Cette livraison ne lance pas encore automatiquement une analyse ciblée de chaque
région ambiguë. Elle n’utilise pas RTMDet COCO pour classer les espaces et ne
prétend pas disposer d’un modèle architectural spécialisé validé. Les chemins
composés/masqués ambigus sont inventoriés mais ne sont pas reconstruits
automatiquement. Il faut les préparer et vérifier leurs contours dans la copie.

L’analyse entièrement automatique d’un AI quelconque, la gestion exhaustive des
objets Illustrator complexes et la recette native sur vos fichiers restent des
conditions à remplir avant de qualifier le module pour la production quotidienne.
