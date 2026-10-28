# Parcours du dessinateur

1. Ouvrir `/releves/` avec une session Studio de dessinateur ou d’administration.
   Créer un dossier. Importer les relevés PDF/JPG/PNG et le BAT `.ai` correspondant,
   enregistré avec compatibilité PDF. Les images EXIF sont remises dans leur repère
   de lecture ; les originaux restent inchangés. Un projet contient un BAT et plusieurs
   relevés/pages. Un changement de BAT nécessite un autre projet.
2. Choisir un relevé et une page, puis l’analyse locale ou multimodale configurée.
   Le filtre de couleur aide à examiner les marques, sans leur attribuer un équipement.
   Le clic dans la liste sélectionne le cadre source et affiche son extrait original.
   Vérifier le texte à partir de cet extrait ; une confidence élevée n’est pas une validation.
3. Dans **Légende**, délimiter la zone avec deux clics et lire ses indices. Saisir les
   associations réellement observées, puis les confirmer ligne par ligne. Les propositions
   qui en résultent ne concernent que cette page. Exporter un dictionnaire par client ou
   méthode et le reprendre explicitement sur un autre dossier ; les associations importées
   sont toutes remises à confirmer. Une légende à sept couleurs n’est jamais préchargée.
4. L’administrateur importe l’archive SAI et l’inventaire, recherche les ressources et
   approuve les pictogrammes après contrôle des aperçus. Les logos et autres ressources
   ne deviennent pas automatiquement des équipements. Le dessinateur choisit un UUID
   précis et confirme sa correspondance métier. Les propositions de correspondances
   utilisent les textes exacts, sans assimiler les capacités ou variantes différentes.
5. Créer les niveaux et indiquer pour chacun la page d’aperçu BAT et le numéro du plan
   de travail Illustrator. Plusieurs niveaux peuvent partager une page d’un BAT composé,
   mais chaque recalage est distinct. Confirmer cette association ; aucun transfert de
   niveau n’est déduit de la ressemblance des étages.
6. Ouvrir **Recalage**. Choisir au moins trois paires de points pour un modèle affine,
   quatre pour la perspective, répartis sur la zone du niveau. Cliquer d’abord dans le
   relevé puis dans le BAT. Ajouter au moins un point de contrôle indépendant, exclu du
   calcul. La proposition automatique doit être examinée et ne remplace pas ce contrôle.
   Calculer, enregistrer, superposer et régler la transparence. Vérifier le bâtiment et
   l’état architectural ; accepter seulement si l’erreur de calcul et de contrôle est
   inférieure au seuil affiché. Les erreurs sont en pixels de l’aperçu BAT.
7. Examiner chaque marque. Un clic à sa position réelle dans le relevé corrige son ancrage ;
   pour une flèche, choisir la pointe, jamais le centre du texte. Cliquer sur le BAT pour
   corriger manuellement la position finale. Régler le symbole, le niveau, la rotation
   horaire et la taille (plus grand côté visible avant rotation). Ajouter les équipements
   oubliés ; rejeter les fausses détections. Chaque changement remet le critère concerné
   à vérifier. Les cercles numérotés sont des repères de position, pas des pictogrammes inventés.
8. Cocher séparément les six critères puis confirmer le placement. Tous les autres
   candidats doivent être corrigés ou rejetés pour autoriser l’export natif. **Exporter
   la revue** conserve les éléments non terminés et permet leur reprise sur le même
   projet et les mêmes documents ; les versions concurrentes ne s’écrasent pas.
9. **Préparer Illustrator** télécharge un ZIP avec `placements.json`, les véritables
   ressources AI sélectionnées sous `library/`, `DOEMO-Pose-Pictogrammes.jsx` et
   `doemo-core.js`. Extraire le ZIP hors des dossiers publics.
10. Sur Illustrator 2024+, fermer le BAT et les ressources déjà ouverts pour préserver
    leur travail non enregistré. Exécuter le JSX via **Fichier > Scripts > Autre script**.
    Sélectionner le JSON, le BAT source (ou une sortie DOEMO antérieure), le dossier
    `library/` et un nouveau nom `.ai`. Aucun fichier existant ne sera écrasé.
11. Lire la comparaison avant application. Les modifications manuelles détectées font
    l’objet d’une confirmation spécifique ; un refus les conserve. Les anciens placements
    absents du nouveau relevé sont conservés et signalés, jamais supprimés automatiquement.
    Les pictogrammes non étiquetés DOEMO ne sont pas identifiables de manière fiable et
    nécessitent une recherche visuelle de doublons avant livraison.
12. Le script importe les groupes vectoriels natifs, les place par niveau et garde les
    UUID dans leurs notes. Il n’oblige pas un groupe à devenir un `SymbolItem`. Les
    contenus liés/raster ou non natifs sont refusés. Les ressources ne sont pas redessinées.
    La copie est enregistrée avec Illustrator, réouverte et contrôlée. Le rapport associé
    distingue la réouverture native et la conformité des placements, qui peut échouer
    si un déplacement manuel a été conservé. Les polices et l’apparence doivent encore
    être examinées visuellement sur le poste avant livraison.
13. Importer le rapport `.ai.placements.json` dans le dossier web. Les identifiants,
    le BAT et la révision doivent correspondre. Le rapport reste identifié comme fourni
    par le poste Illustrator ; le serveur n’affirme pas avoir lui-même exécuté Adobe.

Les fichiers `releve.pdf`, `plan.pdf` à deux pages et le relevé à légende colorée
`3(1).pdf` décrits dans le cahier des charges n’ont pas été joints sous ces noms.
Les essais actuels utilisent exclusivement les fichiers effectivement reçus.
