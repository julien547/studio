# Un BAT, tous ses VEI, trames du client

Fonctionnement confirmé par Julien le 28 octobre 2026 : choisir le **dossier de
trames client** sur la page Orientation, analyser le BAT complet, puis produire
un plan distinct par VEI. Chaque sortie ne garde qu'un seul VEI visible, sa
flèche vers le haut ; les textes et pictogrammes de lecture sont redressés.
Les autres VEI sont masqués dans cette sortie uniquement. Le BAT reste intact.

## Sélection automatique des trames

Le choix utilisateur porte sur le dossier client, par exemple `doemo`, `SAI`
ou `Client École`, sous `/var/lib/doemo-studio/templates/`. Les noms suivent
les règles de la page Réglages, y compris majuscules, espaces et accents.

Dans cette collection et ses sous-dossiers autorisés, associer chaque repère
au fichier `TYPE-FORMAT-ORIENTATION.pdf`, sans distinction de casse :

| Étiquette | Trame attendue |
| --- | --- |
| PEV | PE-A3-V.pdf |
| PIV | PI-A3-V.pdf |
| PE1-H-A4 | PE-A4-H.pdf |

A3 est le format par défaut de la convention d'étiquette existante. Aucun
repli vers un autre dossier client, vers une autre orientation ou vers PE à la
place de PI. Une trame absente, plusieurs fichiers correspondants ou un PDF au
mauvais format restent signalés sur la ligne concernée. Les deux `PEV` d'un
BAT sont deux occurrences distinctes, pas une entrée à dédupliquer.

## Ce qui fonctionne actuellement

```sh
/opt/doemo-studio/venv-pdf/bin/doemo-pdf plan-batch /chemin/prive/BAT.ai --client doemo
```

La commande prépare **toutes les étiquettes candidates de toutes les pages**,
associe les trames automatiquement, vérifie leur format de page et retourne un
rapport JSON. Elle ne crée aucun PDF. Elle ignore la corbeille, les dossiers
cachés et les liens symboliques. Elle respecte la profondeur de l'administration
des trames : quatre composants en comptant collection et fichier.

Sur le BAT `CO26100364-1.ai` fourni, le contrôle trouve trois étiquettes : une
PIV et deux PEV. Les trois associations aux trames de test réussissent. L'ordre
est celui de l'extraction PDF ; les identifiants du préparateur ne sont pas encore
les numéros VEI natifs du rapport Illustrator.

Le résultat porte `status: planning_only`, `production_ready: false`,
`detection_complete: false`. Le nombre de sorties définitif reste `null` :
les étiquettes ne prouvent pas encore l'association pastille/flèche/composants,
et des étiquettes vectorisées peuvent échapper à l'extraction. Les zones de
placement et le contenu métier des trames ne sont pas validés par leurs seuls
noms ou dimensions. Le rendu et le ZIP final restent à implémenter.

## API et page Orientation

`POST /api/orientation.php?action=plan`, après upload et authentification :

```json
{"job":"identifiant-retourne-par-upload","collection":"Client École"}
```

La réponse contient `batch.variants`, les associations et les défauts. Aucun
choix de page unique, de direction manuelle ou de trame unique n'est demandé.
`capabilities` annonce la portée `all_vei` et l'action `plan`. L'action `compose`
reste bloquée tant que le rendu métier n'est pas implémenté.

La page React est dans `julien547/doemo-app`, branche `feat/studio-host`, fichier
`studio-host/Orientation.jsx`. Elle affiche le sélecteur **Dossier de trames
client**, propose l'actualisation après ajout de dossiers dans Réglages,
analyse automatiquement après upload/changement de client et liste toutes les
occurrences. Un changement de client retire immédiatement l'ancien tableau et
annule sa requête en cours. Le bouton « Générer tous les plans » reste désactivé,
avec l'état réel du moteur affiché.

## Mise à jour pour l'autre session

1. Mettre à jour `julien547/studio` sur `main`, réinstaller `./engine` dans
   `/opt/doemo-studio/venv-pdf/`, et publier `api/orientation.php`.
2. Mettre à jour `julien547/doemo-app` sur `feat/studio-host`, installer les
   dépendances du verrou npm, puis lancer `npx vite build -c vite.studio.config.js`.
3. Publier le contenu de `dist-studio/` dans `/var/www/studio/app/` en suivant
   les sauvegardes et permissions du [guide](deploiement-serveur.md).
4. Vérifier `/app/orientation` avec deux dossiers clients, dont l'un manque
   d'une trame PI : aucune substitution DOEMO ne doit apparaître.

La mise à jour du moteur/API doit précéder celle de la page. Le frontend doit
recevoir les dossiers réels du serveur, pas une liste codée en dur. Les
fichiers BAT et rapports réels ne sont pas inclus dans les dépôts.

## Vérifications de cette livraison

- 93 tests Python réussis, dont tous les repères sur plusieurs pages, les
  occurrences répétées, les trames absentes/ambiguës/invalides, les dossiers
  clients isolés, les noms accentués et les liens symboliques ;
- 8 scénarios HTTP PHP réussis, dont le refus de génération et le contrôle du
  travail demandé pour la préparation du lot ;
- build Vite et lint du composant Orientation réussis ;
- 2 tests Chromium du parcours avec API simulée : toutes les occurrences,
  choix/changement de dossier client et trame manquante sans substitution ;
- inspection réelle du BAT fourni : trois candidats et trois associations de
  trame, sans modification de la source.

Ces tests ne constituent pas un déploiement ni une validation de génération
PDF. Le parcours complet doit encore être vérifié sur le serveur après mise à jour.
