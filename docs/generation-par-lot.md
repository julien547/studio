# Tous les plans du BAT et dossier client

La génération Linux des lots de test est désormais raccordée à la page.
Voir [le fonctionnement, les limites et le déploiement 0.3.0](generation-linux.md).

Choisir le dossier client, charger le BAT, puis générer tous les plans. La trame
est recherchée par PE/PI, A0–A4 et H/V dans ce seul dossier et ses sous-dossiers.
Une absence ou une ambiguïté est signalée ; aucun autre client n'est utilisé.
La collection DOEMO reste `/var/lib/doemo-studio/templates/doemo/`.

`plan-batch` reste une inspection générique des étiquettes sur toutes les pages.
Elle ne suffit pas à identifier complètement un VEI. L'API exécute ensuite
`inspect-generation`, qui vérifie les pastilles, tiges, pointes et symboles
contre les données natives. Le bouton s'active uniquement si ce contrôle réussit.

Le profil actuel génère tous les VEI d'un BAT Illustrator AI24 à une page.
Les BAT multipages restent inspectables et éditables, mais leur génération
native complète n'est pas encore prise en charge.

La délimitation des niveaux est **facultative**. Sans cette option, le dessin
complet est utilisé. Avec l'option, les PE utilisent les contours enregistrés
associés à leur VEI ; le PI conserve tous les niveaux à leurs positions relatives.
