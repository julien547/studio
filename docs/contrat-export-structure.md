# Contrat proposé pour un export de BAT structuré

Statut : proposition d'échange à implémenter et valider côté dessinateur. Aucun
paquet de ce format n'a encore été fourni ; ce document ne prétend pas que son
import est déjà implémenté. Le `.ai` réel donne déjà les noms et matrices des
symboles, mais pas encore une association complète validée aux tracés PDF.

## Objectif

Conserver les PDF vectoriels comme graphisme de référence et leur associer des
identités, rôles, matrices et ancres. Aucune reconstruction de pictogramme, de
texte ou de légende. La préparation peut être faite dans Illustrator lors de
l'export du BAT ; la génération quotidienne des déclinaisons reste côté serveur.

## Paquet attendu

- `manifest.json`, UTF-8, versionné ;
- `reference.pdf`, BAT complet de référence ;
- des fragments PDF vectoriels privés et immuables, un objet séparable ou un
  groupe indivisible par fragment ;
- les empreintes SHA-256 de chaque fichier et du BAT source.

Conserver l'ordre de dessin complet. Un seul fond architectural suivi de tous
les pictogrammes ne suffit pas si certains objets passent devant ou derrière
d'autres éléments. Le manifeste doit représenter une séquence ordonnée de
fragments, ou des groupes explicitement atomiques avec leurs enfants ordonnés.

Pour chaque page : dimensions, unités, MediaBox/CropBox et convention de
coordonnées explicites. Fournir la conversion du repère Illustrator vers le
repère PDF ; ne pas présumer qu'ajouter la hauteur de page suffit pour tout AI.

Pour chaque fragment :

- identifiant stable, fichier/page, empreinte, ordre de composition ;
- matrice affine de placement **dans le BAT de référence**, sans rotation de
  déclinaison ;
- rôle explicite : architecture, texte, symbole non directionnel, symbole
  directionnel, composant de VEI, légende ou présentation fixe ;
- ancre en coordonnées source et orientation de référence ;
- visibilité effective, calque et héritage de visibilité ;
- bornes géométriques et visibles, clips, groupes de transparence, mode de
  fusion et éventuelles dépendances à d'autres fragments ;
- comportement : suivre la rotation globale ou conserver l'orientation de
  référence autour de l'ancre transformée ;
- identité métier du symbole si elle existe, sans modifier sa bibliothèque.

Pour chaque VEI : identifiant, type PE/PI, papier, H/V, vecteur terminal de la
flèche, position, identifiants de **tous** ses composants (pastille, rappel,
pointe, texte/étiquette). Aucun composant ne doit être partagé avec le bâtiment
ou avec un autre VEI. La pastille peut être contre-pivotée ; sa flèche garde la
rotation qui la fait pointer vers le haut.

Le périmètre du dessin à transférer dans une trame doit être déclaré sans
découpage arbitraire de niveau. Les textes, logos et légendes d'origine doivent
être conservés ; aucun fragment ne doit disparaître sous prétexte de mise en
page. Toute distinction entre ancien habillage et dessin doit être contrôlée.

## Conditions de fidélité

Avant d'autoriser les déclinaisons, recomposer les fragments **sans transformation
de présentation** et comparer cette recomposition à `reference.pdf` : présence
des équipements, textes, couleurs, contours, ordre, visibilité, transparences et
clips. Vérifier aussi le nombre et les identités des objets, leurs placements et
les empreintes des ressources, puis faire valider visuellement le résultat.

Un drapeau `validated: true` envoyé dans le manifeste n'est pas une preuve. Les
preuves de validation et l'approbation doivent être enregistrées par Studio
pour l'empreinte exacte de ce paquet et de la version du moteur.

Les objets avec effets, masques ou interactions de fusion qui ne peuvent pas
être séparés fidèlement restent atomiques. Si ce groupe mélange un élément
directionnel et un élément à contre-pivoter, bloquer cette transformation et
demander une préparation explicite ; ne pas l'aplatir en image.

## Contre-rotation

Soit `G` la transformation uniforme globale et `a` l'ancre source. L'ancre
résultante est `a' = G(a)`. Pour un composant non directionnel, appliquer ensuite
une rotation de `−θ` autour de `a'`, où `θ` est la rotation globale. La matrice
intrinsèque du fragment reste conservée. Pour une flèche de cheminement, utiliser
uniquement `G`. Les positions relatives des ancres restent celles du plan tourné.

Un texte multiligne ou un symbole composé de plusieurs tracés doit avoir une
ancre commune vérifiée ; contre-pivoter chaque lettre ou tracé autour de son
propre centre déformerait l'objet. Après contre-rotation, recalculer les bornes
visibles et vérifier les débordements avant la mise à l'échelle finale.

## Demande à transmettre à la session Illustrator

Ajouter au nouveau moteur 1.0.13 une commande d'export de BAT structuré pour
Studio, distincte de la génération AI. Elle doit produire les fragments
vectoriels, leur manifeste et un BAT de référence, conserver les originaux,
leurs visibilités et leur légende, et exposer les identifiants complets des VEI,
symboles et textes. Elle doit signaler les objets non séparables et inclure un
essai de recomposition sans transformation. Fournir le paquet de test du
`CO26100364-1.ai` ainsi que le résultat de sa validation dans Illustrator.

La génération de légende de `legend.jsx`, le déplacement de blocs du moteur
1.0.13 et la réactivation des neuf extincteurs du calque `EXT` ne doivent pas
être utilisés pour modifier le BAT pendant cet export.
