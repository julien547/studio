# Référence Illustrator 1.0.14 — contrôle du 28 octobre 2026

La version 1.0.14 reçue devient la référence pour les prochains travaux Studio.
Elle reste un générateur exécuté dans Illustrator ; ses JSX ne remplacent pas
l'adaptation des transformations individuelles au moteur PDF serveur.

## Archive et contrôles exécutés

Archive : `DOEMO-Generateur-1.0.14 (1).zip`, 4 503 165 octets.
SHA-256 : `b5774672ee870e252a9b98117a271bf7febfc9ba6114a62d88318ac9350cb95b`.
Les **41 empreintes** du manifeste correspondent aux fichiers extraits.
L'archive comprend les six fichiers du moteur, les tests, la bibliothèque de
légende AI, un test natif synthétique et la documentation. Elle ne contient
aucune nouvelle sortie réelle AI/PDF ni rapport de génération 1.0.14.

Commandes exécutées dans le dossier extrait, avec Node 24.19.0 :

```sh
npm ci --cache /workspace/.cache/npm --ignore-scripts --no-audit --no-fund
npm test
npm run check
```

Résultats : **125 tests réussis**, zéro échec, et contrôle ES3 réussi pour les
sept sources JS/JSX. Les tests utilisent un DOM Illustrator simulé ; leurs
fichiers AI sont des JSON de test. Illustrator n'a pas été exécuté ici.

`docs/REFERENCE-STUDIO.md` dans ce ZIP décrit encore la livraison 1.0.13 et son
ancien commit. Ce document est historique, contrairement au README, à
`package.json` et aux sources portant 1.0.14. Aucun commit distant 1.0.14 n'est
attesté par ce fichier ; l'empreinte du ZIP identifie la livraison contrôlée.

## Différences vérifiées avec les six sources 1.0.13

| Partie | Changement |
| --- | --- |
| Rotation et contre-rotation | Calculs inchangés ; textes et symboles non directionnels conservent leur orientation autour de l'ancre transformée. Les symboles directionnels suivent le bâtiment. |
| Impression | `enableOutputPrinting` active l'impression des calques et ancêtres nécessaires au contenu visible conservé, uniquement dans les copies. Les éléments masqués, guides et tracés sans peinture sont exclus. |
| Contrôles | `outputPrinting` trace les changements autorisés ; `symbolInventory` distingue impression source/sortie et visibilité. |
| Adresse | `headerSlot` cherche un bandeau en haut de page et réserve l'adresse dessous ; repli en haut de ZONE si aucun bandeau n'est reconnu. |
| Légende | `legend.jsx` strictement identique à 1.0.13 ; reconstruction toujours présente côté Illustrator. |
| Chargeur et panneau | Versions actualisées. Point d'entrée `DOEMO-Generateur.jsx` inchangé. |

Les tests d'impression couvrent les neuf extincteurs EXT dans les copies, les
ancêtres non imprimables, les archives masquées, les guides et la conservation
du BAT. Leur succès ne prouve pas le rendu natif.

## Vérification indépendante sur le BAT fourni

La documentation reçue attribue les extincteurs absents de la sortie 1.0.13 au
calque EXT visible dans Illustrator mais non imprimable. Cette session ne
dispose pas de cette sortie ni de son rapport ; elle a inspecté à nouveau le
BAT original `CO26100364-1.ai` en lecture seule.

Studio lit désormais le drapeau d'impression du profil AI24 observé (`Lb`,
14 opérandes, quatrième opérande). `native_printable` est distinct de
`visible_in_default_pdf`. Un record non reconnu donne `null`. Il s'agit du
réglage propre du calque, pas d'une preuve de visibilité effective ou
d'impression de chaque objet et de ses ancêtres.

| Calque | Instances de symboles | Impression native | Visibilité PDF par défaut |
| --- | ---: | --- | --- |
| Pictos | 18 | activée | activée |
| EXT | 9 | désactivée | désactivée |

Cadre et Trous de percage sont également non imprimables et désactivés dans le
PDF. L'empreinte du BAT est inchangée. Aucun calque n'a été réactivé.
La suite Python Studio comporte **81 tests réussis**, dont six nouveaux cas
distinguant impression native, visibilité PDF et format inconnu, avec contrôle
de l'absence de modification de la source.

## Conséquence pour le serveur

`inspect-ai` améliore le diagnostic ; `compose-diagnostic` conserve toujours la
page BAT complète et ses états PDF. L'API `api/orientation.php`, ajoutée par
l'autre session, appelle ce moteur de diagnostic. La contre-rotation individuelle
des pictogrammes n'est pas encore appliquée aux vrais PDF.

La bibliothèque de légende ne remplace pas l'identification des objets du BAT.
Ni la reconstruction de légende ni la réactivation générale des calques non
imprimables ne sont transposées automatiquement dans Studio. Les exigences de
conservation et le [contrat d'export structuré](contrat-export-structure.md)
restent applicables.

Une sortie AI/PDF réelle 1.0.14 et son `rapport.json` permettront de contrôler
les neuf extincteurs, les textes et pictogrammes droits, les flèches
directionnelles, l'adresse et le VEI actif. Côté serveur, il manque encore la
liaison vérifiée entre chaque objet identifié et ses tracés PDF complets, ou un
export structuré équivalent.

Les [chemins de déploiement](deploiement-serveur.md) restent : venv
`/opt/doemo-studio/venv-pdf/`, trames `/var/lib/doemo-studio/templates/doemo/`,
module `https://studio.doemo.fr/app/orientation`. Aucun déploiement serveur n'a
été effectué par cette session.
