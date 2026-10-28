# CAHIER DES CHARGES COMPLET — DOEMO STUDIO
## Générateur automatique de déclinaisons de plans de sécurité incendie
### Application web autonome — Production de PDF vectoriels

# 1. MISSION ET OBJECTIF

Tu es un développeur senior spécialisé en :

- Applications web professionnelles React et TypeScript.
- Backend Python ou Node.js.
- Traitement de fichiers PDF vectoriels.
- Géométrie 2D et matrices de transformation.
- Analyse de documents Illustrator.
- Automatisation graphique.
- Production de plans d'évacuation et d'intervention.
- Architecture logicielle modulaire.
- Sécurité et traitements asynchrones.

Tu dois développer une application web professionnelle appelée :

**DOEMO STUDIO — GÉNÉRATEUR DE PLANS**

Adresse officielle de l'application :

**https://studio.doemo.fr**

Cette adresse doit être utilisée dans toute la configuration du nouveau projet.

Le sous-domaine `plans.doemo.fr` est déjà utilisé par une autre application DOEMO et ne doit en aucun cas être modifié, écrasé ou utilisé pour héberger le nouveau générateur.

## Objectif principal

Créer une application entièrement accessible depuis un navigateur permettant de :

1. Importer un BAT de plan réalisé dans Adobe Illustrator.
2. Détecter les différents repères « VOUS ÊTES ICI ».
3. Identifier leur orientation.
4. Identifier leur type PE ou PI.
5. Identifier leur format H ou V.
6. Sélectionner automatiquement la bonne trame DOEMO.
7. Générer une déclinaison du plan pour chaque VEI.
8. Orienter la flèche du VEI traité vers le haut.
9. Conserver le dessin original sans aucune correction.
10. Conserver les textes et pictogrammes à l'endroit lorsque leur structure permet une transformation fidèle.
11. Centrer et adapter proportionnellement le dessin à la zone blanche de la trame.
12. Générer des PDF vectoriels de production.
13. Permettre le téléchargement individuel ou en ZIP.

L'application doit être utilisable par les salariés DOEMO sans installer Adobe Illustrator pour cette étape de génération.

**Le résultat attendu est une véritable application de production, pas une maquette ou un prototype fictif.**

---

# 2. CONTRAINTE D'ARCHITECTURE — FONCTIONNEMENT 100 % WEB

La génération doit être réalisée sur le serveur web.

Il ne doit pas être nécessaire de disposer :

- D'un ordinateur local laissé allumé.
- D'Adobe Illustrator Desktop sur le serveur.
- D'un poste Mac ou Windows faisant fonctionner les scripts en arrière-plan.
- De l'API Illustrator Cloud d'Adobe.

Le moteur de production doit être indépendant d'Illustrator.

Les salariés continuent de dessiner leurs plans avec leur logiciel habituel, mais les déclinaisons doivent être réalisées par DOEMO Studio.

## Format de sortie

**Le format final obligatoire est le PDF vectoriel.**

Ne pas développer d'export `.ai` pour cette version.

La génération ne doit pas nécessiter la reconstitution d'un fichier Illustrator natif.

L'application doit préserver les objets vectoriels du document d'entrée dans toute la mesure techniquement possible.

Il est interdit de transformer systématiquement le dessin en bitmap puis de le réexporter en PDF.

## Particularité importante

La rotation globale d'une page PDF vectorielle et la rotation individuelle de ses éléments sont deux opérations différentes.

La première peut être effectuée de manière fiable avec un moteur PDF.

La seconde nécessite de pouvoir identifier et isoler les objets concernés.

Tu dois évaluer explicitement cette limite et construire une solution techniquement honnête.

Ne prétends jamais qu'un PDF quelconque permet automatiquement de retrouver les groupes, symboles et calques natifs Illustrator.

---

# 3. FICHIERS FOURNIS

Je fournirai les scripts Illustrator existants, les trames et des exemples de BAT.

## Scripts existants

- `Generer-plans-complets.jsx`
- `Generer-plans-VEI.jsx`
- `Generer-legende.jsx`

Ces scripts constituent une référence importante pour comprendre les règles métier DOEMO.

Ils contiennent déjà une logique de :

- Détection des VEI.
- Reconnaissance des flèches.
- Identification des étiquettes PE/PI.
- Choix des formats H/V.
- Calcul des angles.
- Rotation des plans.
- Contre-rotation des textes et pictogrammes.
- Gestion des trames.
- Centrage des dessins.
- Ajustement à la zone blanche.
- Génération des déclinaisons.

Tu dois les analyser intégralement avant de développer le nouveau moteur.

**Il ne faut pas simplement exécuter ces scripts JSX sur le serveur.**

Ils servent à comprendre les traitements existants et à reproduire les règles métier dans un moteur PDF indépendant.

## Trames

Je fournirai notamment :

- `ERP - A3H.ait`
- `ERP - A3V.ait`
- Un ZIP du dossier complet `trames/`.

Préserver l'arborescence du dossier ZIP, notamment les éventuels sous-dossiers par client.

## BAT

Je fournirai notamment :

- `CO26100364-1.ai`

Il pourra être accompagné de sa version PDF vectorielle.

## Gestion des formats Illustrator

Un fichier `.ai` doit être accepté uniquement lorsqu'il possède une représentation PDF intégrée réellement exploitable.

Si cette représentation est absente, ne pas inventer une conversion.

Demander un export PDF vectoriel depuis Illustrator.

Les modèles `.ait` doivent être préparés en PDF vectoriel de référence lors d'une étape de configuration initiale.

**La conversion initiale des trames peut être réalisée depuis Illustrator, mais la production quotidienne doit ensuite être entièrement autonome.**

---

# 4. RÈGLE ABSOLUE — AUCUNE CORRECTION DU PLAN

**C'EST LA RÈGLE LA PLUS IMPORTANTE DU PROJET.**

Le logiciel DOEMO Studio n'est pas un outil de vectorisation, de reconstruction ou de correction de plans.

Le BAT fourni par le dessinateur constitue l'unique référence graphique.

Le logiciel doit produire des déclinaisons de présentation, et rien d'autre.

## Opérations strictement interdites

- Redessiner les murs.
- Corriger les murs.
- Modifier les cloisons.
- Supprimer ou ajouter des portes.
- Modifier les fenêtres.
- Simplifier les tracés.
- Modifier les raccordements.
- Modifier les angles architecturaux.
- Modifier les épaisseurs de traits.
- Modifier les couleurs.
- Corriger les dimensions.
- Déplacer individuellement les éléments du bâtiment.
- Déplacer individuellement les équipements incendie.
- Ajouter des pictogrammes.
- Supprimer des pictogrammes incendie.
- Changer le contenu d'un texte.
- Modifier les polices.
- Modifier les tailles de caractères indépendamment de la mise à l'échelle globale.
- Reconstruire les légendes.
- Modifier les logos.
- Réorganiser les niveaux.
- Repositionner les îlots du bâtiment.
- Corriger automatiquement les erreurs éventuelles du BAT.
- Modifier les fichiers sources.

## Transformations autorisées

Uniquement :

1. Rotation rigide globale du dessin concerné.
2. Translation globale.
3. Mise à l'échelle uniforme et proportionnelle.
4. Contre-rotation des textes et pictogrammes non directionnels identifiés sans ambiguïté.
5. Exclusion visuelle des autres repères VEI, uniquement dans la déclinaison produite.
6. Composition avec la trame de production correspondante.

Les proportions, positions relatives et caractéristiques graphiques doivent être conservées.

Si une opération ne peut pas être effectuée fidèlement, le logiciel doit le signaler au lieu de produire silencieusement un résultat incorrect.

---

# 5. FONCTIONNEMENT UTILISATEUR

L'utilisateur se connecte à :

https://studio.doemo.fr

Il doit pouvoir suivre ce processus :

1. Créer un nouveau projet.
2. Saisir la référence de commande.
3. Importer le BAT.
4. Visualiser son contenu.
5. Lancer l'analyse des repères VEI.
6. Contrôler les repères détectés.
7. Corriger manuellement une détection de VEI si nécessaire.
8. Associer chaque repère à son type PE ou PI.
9. Choisir ou confirmer son format H ou V.
10. Prévisualiser chaque déclinaison.
11. Vérifier la rotation et la mise en page.
12. Sélectionner les déclinaisons à produire.
13. Lancer la génération.
14. Télécharger les PDF individuels.
15. Télécharger tous les PDF dans un ZIP.
16. Consulter l'historique de production.

Prévoir la possibilité de reprendre un projet précédemment enregistré.

---

# 6. RECONNAISSANCE DES REPÈRES « VOUS ÊTES ICI »

Le BAT peut comporter plusieurs repères.

Chaque repère peut comprendre :

- Une flèche.
- Une pastille.
- Un symbole.
- Un texte.
- Un numéro.
- Une indication PE ou PI.
- Une indication H ou V.

## Formats à reconnaître

Prévoir notamment :

- PE H
- PE V
- PE.H
- PE.V
- PI H
- PI V
- PI.H
- PI.V
- PE1 H
- PE2 V
- PI1 H
- PI2 V

Prévoir les variantes avec espaces, points, tirets et différences de casse.

## Méthodes de détection

Utiliser, selon les données disponibles :

1. Les textes PDF extractibles.
2. Les tracés vectoriels.
3. Les associations spatiales.
4. Les conventions détectées dans les scripts Illustrator existants.
5. Les métadonnées complémentaires si disponibles.

Il faut distinguer précisément :

- Le repère « VOUS ÊTES ICI ».
- Les flèches directionnelles d'évacuation.
- Les autres flèches techniques.
- Les pictogrammes incendie.

Ne jamais considérer qu'une flèche quelconque est automatiquement un VEI.

## Validation humaine

Afficher les repères détectés sur le plan.

L'utilisateur doit pouvoir :

- Sélectionner un repère.
- Corriger sa position.
- Indiquer la direction de la pointe.
- Corriger son type PE ou PI.
- Corriger son format H ou V.
- Lui donner un identifiant.
- Exclure un repère de la génération.

Ces corrections concernent les paramètres de génération et ne doivent pas modifier le BAT original.

---

# 7. CALCUL DES ROTATIONS

Pour chaque VEI, calculer l'orientation du vecteur de sa flèche.

La flèche doit pointer vers le haut dans la déclinaison générée.

Calculer l'angle de rotation à partir de sa direction réelle.

Gérer :

- Haut : 0°.
- Droite : rotation adaptée pour atteindre le haut.
- Bas : 180°.
- Gauche : rotation adaptée pour atteindre le haut.
- Toutes les orientations intermédiaires.

Les calculs doivent utiliser une convention géométrique cohérente.

Attention aux différences de systèmes de coordonnées entre l'interface navigateur, les bibliothèques PDF et les documents Illustrator.

## Rotation globale

Appliquer une transformation rigide à l'ensemble du dessin concerné.

Le plan doit tourner comme un seul ensemble.

Ne jamais faire pivoter indépendamment :

- Un mur.
- Une pièce.
- Une porte.
- Un escalier.
- Un groupe architectural.
- Un îlot supposé appartenir au même niveau.

Lorsque plusieurs niveaux sont présents, conserver leur disposition relative d'origine.

Ne pas les réorganiser pour optimiser artificiellement l'espace.

## Vérification de rotation

Après transformation, vérifier mathématiquement l'orientation finale du vecteur VEI.

Prévoir également un contrôle visuel dans l'interface.

L'objectif est que la pointe soit systématiquement orientée vers le haut.

---

# 8. TRAITEMENT DES TEXTES

Après rotation du plan, certains textes risquent de se retrouver couchés ou à l'envers.

Le logiciel doit conserver leur lecture normale lorsque le PDF permet de les identifier sans risque.

## Comportement attendu

- Identifier les objets texte.
- Préserver leur contenu.
- Préserver les polices et styles.
- Préserver les attributs graphiques.
- Appliquer la rotation compensatrice autour du centre ou du point d'ancrage correctement transformé.
- Conserver la position correspondante sur le plan après rotation.
- Ne pas modifier le texte original.
- Ne pas déplacer artificiellement le texte vers une nouvelle zone.

## Textes complexes

Prévoir les cas suivants :

- Texte horizontal.
- Texte vertical.
- Texte déjà orienté dans le BAT.
- Texte composé de plusieurs objets.
- Texte vectorisé.
- Texte intégré à un groupe graphique.
- Texte avec transformation matricielle existante.

Ne pas appliquer aveuglément une même rotation à tous les textes.

Conserver leur orientation de référence lorsque cela respecte la règle de lisibilité.

## Cas non compatibles

Si un texte est converti en tracés indissociables, ne pas tenter de le reconstruire par OCR puis réécriture.

Signaler une limite de traitement et demander une source structurée si nécessaire.

---

# 9. TRAITEMENT DES PICTOGRAMMES

Le logiciel doit distinguer les pictogrammes non directionnels et les éléments directionnels.

## Pictogrammes non directionnels

Exemples :

- Extincteur.
- Déclencheur manuel.
- RIA.
- Équipements incendie.
- Équipements techniques.
- Certains pictogrammes de risques.

Lorsqu'ils sont isolables sans perte, les contre-pivoter pour conserver leur orientation de lecture.

## Pictogrammes directionnels

Exemples :

- Flèches d'évacuation.
- Indicateurs de cheminement.
- Signaux indiquant une direction physique.

Ces éléments doivent suivre la rotation du bâtiment afin de conserver leur signification fonctionnelle.

## Classification

Prévoir une table de configuration permettant d'associer à chaque type de symbole :

- Son identifiant.
- Son nom.
- Sa catégorie.
- Son comportement à la rotation.
- Son point d'ancrage.

La bibliothèque des symboles ne doit pas être modifiée.

## Limite technique essentielle

Dans un PDF ordinaire, les pictogrammes peuvent être constitués de tracés anonymes, de Form XObjects, d'images ou de contenus fusionnés.

Le logiciel doit analyser leur séparabilité avant toute transformation individuelle.

Aucune suppression et aucune reconstitution approximative ne sont autorisées.

Si l'exigence de contre-rotation ne peut pas être satisfaite sans altération, bloquer la déclinaison avancée et proposer un diagnostic précis.

Ne pas faire passer un résultat dégradé pour un plan conforme.

---

# 10. GESTION DES TRAMES DOEMO

L'application doit utiliser les vraies trames fournies.

Les modèles peuvent différer selon :

- Type de plan.
- Format.
- Orientation.
- Client.
- Établissement.
- Collection de trames.

## Types

- PE : plan d'évacuation.
- PI : plan d'intervention.

## Orientations

- H : horizontal.
- V : vertical.

## Formats

Prévoir une architecture extensible :

- A3.
- A2.
- A1.
- Autres formats configurables.

## Organisation

Pouvoir importer un ZIP contenant les trames, avec leurs sous-dossiers.

Préserver l'organisation existante.

Créer un catalogue interne :

- Nom de la trame.
- Type PE/PI.
- Format papier.
- Orientation H/V.
- Client éventuel.
- Version.
- Date d'importation.
- PDF vectoriel correspondant.
- Zone utile du plan.

Le logiciel doit sélectionner automatiquement la trame adaptée au VEI.

L'utilisateur doit pouvoir vérifier ou remplacer cette sélection.

Ne pas modifier la trame de référence.

---

# 11. ZONE BLANCHE ET CENTRAGE

Les trames DOEMO possèdent une zone blanche destinée à recevoir le dessin du bâtiment.

Cette zone ne correspond pas nécessairement au plan de travail entier.

## Définition

Prévoir une zone configurable nommée :

`ZONE_PLAN`

Elle doit pouvoir être définie par quatre coordonnées ou par sélection visuelle dans l'interface d'administration.

Privilégier une zone explicitement configurée plutôt qu'une estimation automatique.

## Centrage

Pour chaque déclinaison :

1. Déterminer les limites géométriques du dessin concerné.
2. Calculer les limites après rotation.
3. Comparer les dimensions avec la zone utile.
4. Déterminer le facteur d'échelle uniforme.
5. Appliquer ce facteur à l'ensemble du dessin.
6. Positionner le centre du dessin sur le centre de la zone utile.
7. Vérifier les marges.

## Mise à l'échelle

Le facteur doit être identique horizontalement et verticalement.

Ne jamais déformer le bâtiment.

Prévoir deux modes configurables :

- Ajuster au maximum dans la zone.
- Réduire uniquement si le dessin dépasse.

La mise à l'échelle ne doit pas modifier les proportions relatives des objets.

Le pourcentage appliqué doit être enregistré dans le rapport de génération.

## Zones protégées

Ne jamais empiéter sur :

- Bandeaux.
- Consignes.
- Cartouches.
- Logos.
- Zones de légende.
- Informations de production.

Les éléments fixes doivent rester exactement à leur position d'origine dans la trame.

---

# 12. GESTION DES AUTRES VEI

Chaque déclinaison doit afficher uniquement son repère actif « VOUS ÊTES ICI ».

Les autres VEI ne doivent pas apparaître dans le PDF final.

Cependant, il est interdit de modifier les autres éléments du plan.

Ne jamais utiliser une suppression basée uniquement sur une zone rectangulaire si celle-ci peut effacer :

- Un mur.
- Une porte.
- Un pictogramme.
- Un texte.
- Un équipement technique.

La méthode doit reposer sur des repères identifiables et isolables.

## Cas de repères indissociables

Si un VEI est fusionné avec le fond de plan et ne peut pas être masqué sans détérioration, le logiciel doit le signaler.

Prévoir éventuellement un contrat de préparation du BAT avec :

- Un PDF du fond architectural.
- Une couche ou un document des repères VEI.
- Un manifeste JSON indiquant leur position et leur direction.

Ce mécanisme peut être généré par un outil d'export côté dessinateur, mais ne doit pas nécessiter Illustrator sur le serveur.

Le logiciel ne doit jamais corriger arbitrairement le BAT pour compenser une mauvaise structuration.

---

# 13. PLANS PE ET PI

Conserver les conventions métier DOEMO.

## Plans d'évacuation — PE

Un PE est associé à un emplacement « VOUS ÊTES ICI ».

Selon l'organisation du BAT, il peut correspondre à un niveau particulier.

Le module doit conserver la géométrie du niveau.

Si plusieurs niveaux sont présents dans la même source, leur sélection doit être fondée sur une identification fiable ou une indication explicite de l'utilisateur.

Ne pas couper arbitrairement le dessin.

## Plans d'intervention — PI

Un PI peut contenir plusieurs niveaux.

Le module doit préserver les niveaux présents et leur organisation, conformément au BAT.

Il ne doit pas réorganiser les niveaux ni les éléments pour améliorer la mise en page.

## Règle de contenu

Aucune différence PE/PI ne doit provoquer automatiquement la suppression de pictogrammes, la modification des légendes ou la correction des éléments du BAT.

Le type PE/PI sert à choisir la bonne trame et les règles de présentation autorisées.

---

# 14. MOTEUR PDF SERVEUR

Développer un moteur de traitement PDF vectoriel performant et fiable.

Évaluer les bibliothèques appropriées :

- pikepdf.
- pypdf.
- qpdf.
- PDF.js pour les prévisualisations.
- Bibliothèques de composition PDF vectorielle.
- Autres bibliothèques compatibles si nécessaire.

Choisir les composants en fonction des capacités réelles et de leurs licences.

## Fonctions techniques

Le moteur doit savoir :

- Lire les pages PDF.
- Identifier les dimensions.
- Vérifier le caractère vectoriel.
- Extraire les informations textuelles disponibles.
- Examiner les ressources graphiques.
- Appliquer des matrices de transformation.
- Réaliser des rotations à angle quelconque.
- Positionner un contenu sur une autre page.
- Mettre à l'échelle uniformément.
- Composer les trames.
- Préserver les objets vectoriels.
- Générer un fichier PDF par déclinaison.

## Préservation graphique

Conserver autant que possible :

- Les tracés.
- Les courbes.
- Les couleurs.
- Les contours.
- Les transparences.
- Les images intégrées.
- Les polices incorporées.
- Les ressources vectorielles.

Éviter tout aplatissement ou rasterisation.

Si certaines transparences ou fonctions PDF ne peuvent pas être conservées à l'identique, le rapport doit le signaler.

## Performance

Prévoir des traitements asynchrones.

Les fichiers peuvent être volumineux.

Ne pas bloquer le navigateur pendant la génération.

---

# 15. APPLICATION WEB ET INTERFACE

Développer une interface React professionnelle, moderne et responsive.

Adresse :

https://studio.doemo.fr

Le design doit être cohérent avec l'identité DOEMO.

## Tableau de bord

Afficher :

- Projets récents.
- BAT importés.
- Générations terminées.
- Générations en cours.
- Erreurs.
- Historique.

## Page d'import

Prévoir :

- Référence de commande.
- Nom de projet.
- Dépôt du BAT.
- Contrôle du format.
- Diagnostic vectoriel.
- Aperçu du document.

## Page de vérification

Afficher :

- Plan source.
- Liste des VEI.
- Position des repères.
- Sens des flèches.
- Type PE/PI.
- Orientation H/V.
- Trame choisie.

L'utilisateur doit pouvoir corriger les paramètres de génération sans toucher au plan.

## Page de prévisualisation

Permettre :

- Zoom.
- Déplacement.
- Comparaison source / déclinaison.
- Affichage de la trame.
- Affichage de la zone blanche.
- Vérification des débordements.
- Visualisation des rotations.

## Page de génération

Afficher une progression réelle :

- Fichier en analyse.
- Repères identifiés.
- Trames attribuées.
- Déclinaisons en cours.
- Contrôles réalisés.
- Documents disponibles.

Ne pas simuler artificiellement l'avancement.

## Page des résultats

Pour chaque fichier :

- Nom du PDF.
- Référence de commande.
- Repère VEI.
- Type PE/PI.
- Format H/V.
- Angle de rotation.
- Facteur d'échelle.
- Statut de validation.
- Aperçu.
- Téléchargement.

Prévoir le téléchargement global ZIP.

---

# 16. EXEMPLE DE GÉNÉRATION AVEC CINQ VEI

Créer un jeu de test comprenant :

| VEI | Type | Format | Sens initial |
|---|---|---|---|
| VEI-001 | PE | V | Droite |
| VEI-002 | PE | H | Bas |
| VEI-003 | PE | V | Haut |
| VEI-004 | PI | H | Gauche |
| VEI-005 | PI | V | Diagonale |

Ces données sont fictives et servent uniquement aux tests.

## Résultat attendu

Cinq fichiers :

- `PE1-V.pdf`
- `PE2-H.pdf`
- `PE3-V.pdf`
- `PI1-H.pdf`
- `PI2-V.pdf`

Chaque fichier doit :

- Utiliser la trame correcte.
- Avoir son VEI orienté vers le haut.
- Conserver son plan sans correction.
- Être correctement centré.
- Présenter des proportions inchangées.
- Préserver les contenus vectoriels.
- Être prêt pour une validation de production.

Ne pas utiliser ce jeu fictif comme preuve de fonctionnement sur les vrais BAT DOEMO.

---

# 17. INTÉGRATION À L'ÉCOSYSTÈME DOEMO

L'application doit être indépendante de l'hébergement existant de `plans.doemo.fr`.

Elle dispose de son propre environnement :

- Frontend.
- Backend.
- Base de données.
- Stockage.
- Gestion des utilisateurs.
- Moteur PDF.
- File de traitements.

Ne pas modifier les applications DOEMO existantes sans instruction explicite.

## Connexion future

Prévoir une architecture permettant une future connexion avec les commandes DOEMO.

Exemples :

- Récupération d'une référence de commande.
- Import d'un BAT déjà stocké.
- Association des PDF générés à une commande.
- Consultation des résultats depuis l'outil principal.
- Authentification commune si une méthode sécurisée est disponible.

Ne pas présumer que les API existantes permettent déjà ces opérations.

Si le dépôt `julien547/doemo-app` est accessible, il peut être étudié comme référence technique et fonctionnelle, mais le nouveau service doit rester distinct tant qu'une intégration n'est pas validée.

---

# 18. SÉCURITÉ ET GESTION DES UTILISATEURS

Prévoir :

- Authentification sécurisée.
- Gestion des rôles.
- Contrôle des accès.
- Isolation des documents.
- Stockage privé.
- Liens de téléchargement sécurisés.
- Limitation des tailles de fichiers.
- Vérification des documents uploadés.
- Protection contre les PDF malveillants.
- Protection contre la traversée de répertoires dans les ZIP.
- Journalisation.
- Limitation des traitements simultanés.
- Politique de conservation des fichiers.
- Suppression contrôlée des anciens projets.

Les documents des clients ne doivent pas être accessibles publiquement.

Les utilisateurs ne doivent pas pouvoir consulter les fichiers des autres clients ou équipes sans autorisation.

Les fichiers originaux doivent être conservés et protégés contre tout écrasement.

---

# 19. ADMINISTRATION DES TRAMES

Développer un espace administrateur permettant :

- L'import d'un ZIP de trames.
- Le classement par client.
- Le classement PE/PI.
- Le classement H/V.
- Le classement par format.
- La visualisation des trames.
- La définition de la zone utile.
- La définition des marges.
- La configuration des dimensions.
- L'activation ou la désactivation des trames.
- Le suivi des versions.

Prévoir une validation avant qu'une nouvelle trame devienne utilisable en production.

Ne jamais modifier automatiquement les trames originales.

---

# 20. RAPPORT DE PRODUCTION ET CONTRÔLES QUALITÉ

Chaque génération doit produire un rapport.

Il doit préciser :

- Fichier source.
- Empreinte du fichier source.
- Référence du projet.
- Nombre de VEI détectés.
- Nombre de déclinaisons demandées.
- Nombre de déclinaisons générées.
- Type de chaque plan.
- Trame utilisée.
- Angle de rotation.
- Mise à l'échelle.
- Contrôles effectués.
- Anomalies.
- Statut final.

## Vérifications obligatoires

Contrôler :

1. L'intégrité du PDF produit.
2. Les dimensions de page.
3. La sélection de la trame.
4. La présence du plan.
5. Le respect de la zone blanche.
6. L'orientation du VEI.
7. Le nombre de VEI actifs.
8. L'absence de déformation.
9. La conservation des tracés.
10. L'absence de modification du contenu architectural.
11. L'absence de pictogrammes supprimés.
12. La fidélité des couleurs et contours.
13. La présence des textes.
14. La lisibilité des éléments contre-pivotés.
15. L'absence de rasterisation inattendue.
16. L'absence de modification des fichiers sources.

En cas d'anomalie critique, marquer le résultat comme non conforme.

Ne pas déclarer automatiquement un PDF prêt pour la production si les contrôles ont échoué.

---

# 21. ÉTUDE DE FAISABILITÉ OBLIGATOIRE

Avant de construire toute l'interface, développer une preuve de fonctionnement sur un vrai BAT.

## Test initial

Utiliser le fichier réel fourni et une trame DOEMO.

Démontrer :

1. Que le BAT peut être exploité en PDF vectoriel.
2. Qu'un repère VEI peut être détecté ou déclaré manuellement.
3. Que sa flèche peut être correctement orientée vers le haut.
4. Que le plan peut être inséré dans la trame.
5. Que le dessin peut être centré et redimensionné proportionnellement.
6. Que le résultat reste vectoriel.
7. Que le BAT original reste inchangé.

## Test de difficulté avancée

Vérifier si les éléments suivants peuvent être isolés :

- Textes.
- Pictogrammes.
- Flèches directionnelles.
- Différents VEI.

Si oui, développer les contre-rotations et les masquages.

Si non, définir précisément le format de données complémentaire nécessaire.

## Point bloquant

Ne pas développer une interface qui promet une contre-rotation parfaite des symboles sur n'importe quel PDF avant d'en avoir démontré la faisabilité.

Pour un PDF insuffisamment structuré, proposer un export initial structuré depuis Illustrator, sans dépendance à Illustrator sur le serveur.

Ce contrat d'export doit permettre d'associer une représentation vectorielle à des identifiants d'objets, des transformations et des rôles métiers.

Documenter le format.

---

# 22. PHASES DE DÉVELOPPEMENT

## Phase 1 — Audit technique

- Examiner les scripts JSX fournis.
- Examiner le BAT réel.
- Examiner les trames.
- Vérifier leur compatibilité PDF.
- Choisir les bibliothèques.
- Vérifier les licences.
- Identifier les difficultés de segmentation des objets.

Livrable : diagnostic de faisabilité.

## Phase 2 — Premier moteur PDF

- Lecture du BAT.
- Sélection d'un VEI.
- Calcul de rotation.
- Application de transformation.
- Insertion dans une trame.
- Ajustement proportionnel.
- Production d'un premier PDF vectoriel.

Livrable : PDF réel testable.

## Phase 3 — Fonctions avancées

- Détection de plusieurs VEI.
- Gestion PE/PI.
- Gestion H/V.
- Gestion de plusieurs trames.
- Contre-rotation des objets compatibles.
- Masquage des autres VEI.
- Validation des limites du PDF.
- Rapport de contrôle.

Livrable : moteur de déclinaison complet.

## Phase 4 — Interface web

- Tableau de bord.
- Import BAT.
- Visualisation.
- Sélection des VEI.
- Configuration H/V.
- Prévisualisation.
- Génération.
- Téléchargements.

Livrable : application web utilisable.

## Phase 5 — Production

- Authentification.
- Stockage.
- Files de traitements.
- Historique.
- Administration des trames.
- Journaux.
- Tests.
- Documentation de déploiement.

Livrable : version prête pour validation en environnement de préproduction.

---

# 23. DÉPLOIEMENT SUR STUDIO.DOEMO.FR

Préparer une architecture de déploiement complète.

L'application sera accessible depuis :

**https://studio.doemo.fr**

Prévoir :

- Configuration DNS.
- Certificat SSL/TLS.
- HTTPS.
- Reverse proxy.
- Configuration des variables d'environnement.
- Backend de traitement.
- Stockage privé des fichiers.
- Base de données.
- Gestion des processus.
- Sauvegardes.
- Journaux.
- Supervision.
- Procédure de mise à jour.

Ne pas modifier le DNS ou le serveur existant sans validation.

Ne pas écraser les applications déjà en place.

Prévoir un déploiement reproductible avec Docker si cela correspond à l'environnement disponible.

Ne pas supposer qu'un serveur possède déjà les ressources nécessaires.

Documenter les besoins CPU, RAM, disque et les limites des traitements simultanés.

---

# 24. TESTS OBLIGATOIRES

Développer des tests automatisés et des tests de validation visuelle.

Tester notamment :

- Un VEI.
- Cinq VEI.
- Plusieurs orientations.
- Angles obliques.
- Trames horizontales.
- Trames verticales.
- Plusieurs formats de papier.
- Plans volumineux.
- Plans multipages.
- Textes conservés.
- Symboles conservés.
- Flèches directionnelles.
- VEI superposés à d'autres éléments.
- PDF comportant des objets non séparables.
- PDF avec transparence.
- PDF avec masques.
- PDF avec texte vectorisé.
- Mauvaises trames.
- Fichiers corrompus.
- Reprise après échec.

Créer des comparaisons visuelles avant/après.

Toute différence de contenu non autorisée doit être considérée comme une anomalie.

Tester les transformations inverses pour vérifier la conservation de la géométrie lorsque cela est applicable.

---

# 25. LIVRABLES ATTENDUS

À la fin du développement, fournir :

1. Le code source complet de DOEMO Studio.
2. Le frontend React.
3. Le backend.
4. Le moteur PDF.
5. Le système de détection des VEI.
6. Les fonctions de rotation.
7. Les fonctions de contre-rotation compatibles.
8. Le gestionnaire de trames.
9. La prévisualisation.
10. La génération PDF.
11. Le téléchargement ZIP.
12. La gestion des projets.
13. Le système d'authentification.
14. Les tests.
15. Le rapport de faisabilité.
16. Les rapports de contrôle.
17. Les instructions d'installation.
18. Les instructions de déploiement.
19. Le guide utilisateur.
20. Les limites techniques documentées.

Prévoir un projet organisé, modulaire et maintenable.

Ne pas fournir uniquement un code HTML de démonstration.

Ne pas annoncer un résultat fonctionnel lorsque les tests n'ont pas été exécutés.

---

# 26. INSTRUCTIONS FINALES À CODEX

Commence par analyser tous les fichiers fournis.

Étudie attentivement les scripts Illustrator existants pour comprendre les règles métier DOEMO.

Ne cherche pas à reconstruire ou améliorer les plans.

Développe uniquement les fonctions nécessaires à leur déclinaison.

**Priorités absolues :**

1. Fidélité totale du plan architectural.
2. Aucun changement des contenus graphiques.
3. Rotation exacte des VEI.
4. Respect des textes et pictogrammes.
5. Utilisation des trames DOEMO.
6. Centrage dans la zone blanche.
7. Conservation du vectoriel.
8. Génération d'un PDF distinct par VEI.
9. Fonctionnement entièrement en ligne.
10. Hébergement exclusif sur `studio.doemo.fr`.

Commence par une démonstration technique réelle sur un BAT et une trame.

Si les fichiers PDF