# Reprise sur RELEVEDEUX et CO26100239-1 — 28 octobre 2026

Le relevé précédent `2.pdf` montrait principalement des emplacements de plans.
À la demande de l’utilisateur, l’essai a été repris avec ses nouveaux documents.
Parmi `releve.pdf` et `RELEVEDEUX.pdf`, le second a été choisi : sa légende décrit
les extincteurs H₂O/CO₂ et les repères de plans. Il présente le RDC et le R‑1 du
magasin Animalis, 70 boulevard de Grenelle, Paris.

Le nouveau `CO26100239-1.ai` et son PDF représentent ce même site et ces niveaux.
Le BAT comporte une page portrait de 841,89 × 1190,55 pt et des données natives
Illustrator. L’identité de site ne valide pas à elle seule l’état architectural.
Le relevé comporte une page paysage de 1190,40 × 841,44 pt ; les deux niveaux
doivent être recalés séparément sur la page BAT.

## Reconnaissance et contrôle visuel

OpenAI est désormais configuré et des appels réels `gpt-4.1` ont été effectués.
Le premier passage sur la page entière a produit trois propositions non
exploitables pour la pose. Deux analyses de zones, avec la page entière comme
contexte, ont ensuite produit cinq propositions chacune. Leurs positions et
lectures restent insuffisantes ; elles ne sont pas présentées comme validées.

Une revue visuelle assistée distincte relève **16 zones à contrôler**, avec
extraits, observations et origine explicite `assistant_visual_review`.
Ce ne sont ni 16 équipements automatiquement reconnus ni 16 placements validés.
Lors de cette première revue, les six critères de validation restaient tous à faux. Les réponses IA originales
sont conservées à part pour comparaison, sans écraser les projets antérieurs.

La légende porte les quantités manuscrites 6 H₂O et 2 CO₂, et une note annonce
1 PI et 3 PE. Ces chiffres sont des totaux écrits, pas un comptage terrain établi.
Un symbole CO₂ imprimé près du local électrique du RDC est accompagné d’une
correction manuscrite H₂O. Les mentions EP6 et plusieurs positions de plans
nécessitent également un contrôle ; aucune capacité n’a été déduite automatiquement.

L’utilisateur a ensuite confirmé sa règle métier : **tous les extincteurs utilisent
« Extincteur Portatif », sans distinction**. Les huit zones candidates d’extincteurs
de la revue utilisent désormais l’UUID `6fac994a-56a3-4228-b2f5-ba5bc64c5541`.
Le choix graphique et les correspondances sont confirmés ; les autres critères
restent à contrôler. Les observations H₂O/CO₂/EP6 sont conservées. La différence
CO₂/H₂O en zone 9 ne bloque plus le choix du symbole.

L’utilisateur a ensuite corrigé les zones 4, 6, 7, 11 et 12 en **VEI**, demandé
de ne rien poser en zone 5 et laissé la zone 15 indéterminée. La zone 4 porte PE,
pas CO₂. Il reste ainsi six zones candidates d’extincteurs, cinq désignations VEI,
une zone rejetée et les autres observations à contrôler. L’ancrage de la fausse
lecture CO₂ en zone 4 a été annulé, sans déplacer arbitrairement le repère.

La ressource « Porte Coupe Feu » reste proposée. L’utilisateur confirme que le
VEI est absent de SAI et a ensuite fourni le symbole isolé dans `Sans titre.ai`.
Cette ressource supplémentaire est conservée à part de l’archive SAI originale.
La zone 15 n’est plus affirmée
comme une boucle à induction. Voir les [règles de pictogrammes](regles-pictogrammes.md).

## Recalage et correctifs

Les premières correspondances SIFT regroupaient plusieurs détails source sur le
même point cible. Le moteur élimine désormais ces doublons physiques et refuse
les correspondances colinéaires ou trop concentrées. Après correction, les deux
tentatives automatiques réelles sont refusées comme non fiables.

Deux recalages manuels préparatoires ont ensuite été mesurés sur des points
indépendants : 12,40 px RMS au RDC et 8,75 px au R‑1, pour un seuil de 5 px sur
l’aperçu de 1698 × 2400 px. Ils restent refusés. Les très faibles résidus sur les
quatre points utilisés pour ajuster l’homographie ne constituent pas une validation.

Les réponses OpenAI utilisent maintenant un schéma JSON strict, notamment pour
empêcher les ancrages retournés sous forme de listes. Un ancrage dont la nature
est inconnue est conservé comme absent. L’analyse multimodale accepte une zone
normalisée facultative via le worker ; ses coordonnées sont reconverties dans la
page originale après arrondi du découpage aux pixels. La seconde image sert de
contexte de légende, pas de repère de coordonnées.

## Résultat conservé

Le dossier privé est `/workspace/studio-releves-audit/nouveaux-releves/` :
`Animalis-revue.html` présente les extraits et le BAT, `projet-revue.json` conserve
la revue complète et `dictionnaire-propose.json` les correspondances non approuvées.
Un projet privé de test `audit-local` conserve aussi les deux originaux en SQLite.
Aucun document client n’est ajouté au dépôt source.

Les **37 tests backend** passent, dont les nouveaux contrôles de conversion des
coordonnées de zones, d’ancrage inconnu et de correspondances répétées. L’export
de placement du dossier réel est bien bloqué tant que la revue reste non approuvée.
Aucun fichier AI final n’a été généré, aucun essai Adobe natif n’a été réalisé,
et rien n’a été publié ou déployé.

## Aperçu avec relevé en arrière-plan

Le dossier privé `apercu-pictogrammes/` contient désormais un PDF de contrôle,
son image et une vue HTML interactive. Le relevé est découpé par niveau, recalé
au format du BAT et dessiné **derrière le plan vectoriel et les pictogrammes**,
avec une opacité initiale de 45 %. Le HTML permet d’ajuster cette opacité.
Le PDF séparé `Releve-fond-format-Illustrator.pdf` fournit le fond seul au même
format de page. Aucun mur n’a été redessiné.

Sept pictogrammes sont proposés : trois extincteurs génériques et quatre VEI
issus des ressources réelles. Le VEI s’ancre sur son petit point de repérage.
Les positions 1, 3, 4 et 8 restent absentes ; les autres zones indéterminées
restent signalées. Les tailles et orientations ne sont pas validées.

Cet aperçu utilise un ajustement expérimental du recalage : erreurs de contrôle
de 8,75 px au RDC et 6,32 px au R‑1, toujours au-dessus du seuil de 5 px.
Il ne remplace pas les recalages du projet et n’autorise pas l’export final.
Les corrections de position du HTML s’exportent dans un JSON distinct, avec
`validated: false`, sans écriture dans le projet. Le contrôle navigateur vérifie
l’ordre des couches, l’opacité, les sept symboles et l’export d’une correction.
Les deux PDF gardent une page de 841,89 × 1190,55 pt.
