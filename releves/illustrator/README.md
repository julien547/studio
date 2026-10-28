# Scripts Illustrator

Exécution sur Adobe Illustrator **2024+**, sur le poste du dessinateur. Ces fichiers
ne sont pas des services OVH. Les tests JavaScript simulent le DOM Adobe.

- `DOEMO-Pose-Pictogrammes.jsx` et `doemo-core.js` : connecteur générique du paquet d’export
  préparé par le backend ; consulter le contrat d’échange et contrôler chaque pose.
- `DOEMO-VEI-selection.jsx` : extraction depuis une sélection préparée dans Illustrator.
- `DOEMO-VEI-autonome.jsx`, `DOEMO-Extraire-VEI.jsx` : variantes historiques d’extraction ;
  cette dernière attend aussi `selection-VEI.json`, le cœur JS et la source native.
- `DOEMO-Fond-Releve.jsx` : **modèle source** avec marqueur
  `__DOEMO_REGISTERED_PNG_BASE64__`. Il nécessite une préparation avec le PNG recalé ;
  télécharger ce fichier seul ne fournit pas le relevé intégré.
- `DOEMO-Animalis-Pictogrammes.jsx`, `DOEMO-Animalis-Complements.jsx` : scripts spécifiques
  au dossier Animalis, positions et dimensions prédéfinies, ressources AI à fournir
  à côté du script. Ce ne sont pas des placeurs universels.
- `DOEMO-Corriger-Deux-PCF.jsx` : variante historique utilisant `PCF-verifie.pdf`.
- `DOEMO-PCF-Direct.jsx` : variante directe utilisant `PCF-traces.txt` ; le correctif
  du dossier `planv4.ai` a été accepté par l’utilisateur. Cela ne valide pas tous
  les autres scripts ni le connecteur générique.

Les dépendances privées (AI/PDF, traces, PNG recalé) ne sont pas intégrées au code
source. Préparer le paquet correspondant au dossier et suivre les contrôles du
script avant exécution. Ne pas relancer tous les scripts sur le même document :
plusieurs sont des variantes successives. Enregistrer le JSX en **texte brut UTF-8**,
pas en RTF, et travailler sur une nouvelle copie AI.
