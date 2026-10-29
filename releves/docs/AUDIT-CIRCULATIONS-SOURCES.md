# Audit initial des véritables fichiers Illustrator DOEMO

Audit réalisé en lecture seule sur les AI déjà fournis dans cette conversation.
Les fichiers d’origine n’ont pas été modifiés. L’analyse locale porte sur leur
aperçu PDF vectoriel ; Adobe Illustrator n’est pas disponible dans cet environnement.

| Source réelle | Taille du PDF embarqué (pt) | Tracés vectoriels | Images référencées | Candidats de teinte verte |
| --- | --- | ---: | ---: | ---: |
| CO24060047-1-HD.ai | 2383,94 × 1683,78 | 3012 | 1 | 46 |
| CO26100239-1.ai | 841,89 × 1190,55 | 217 | 2 | 21 |

Les candidats de teinte verte sont **des objets à examiner**, pas un nombre de
circulations reconnues : ils peuvent inclure des éléments de légende ou des symboles.
Le fichier CIRAD `CO24060047-1-HD.ai` comporte visiblement du vert existant sur
plusieurs niveaux et convient au contrôle des doublons. Animalis ne permet pas
de déduire que toute surface de vente est une circulation.

Le texte PDF contient des libellés exploitables, mais aussi des encodages partiels.
Les groupes, masques, calques, modes CMJN/tons directs et données privées AI ne
peuvent pas être attestés par cet aperçu. Leur extraction est confiée au script
`DOEMO-Exporter-Circulations.jsx` sur le poste Adobe.

Le script d’audit produit `audit.json`, `page-1-original.png` et `page-1-audit.png`.
Cette dernière image ajoute des cadres bleus de diagnostic aux objets existants ;
ce n’est pas un résultat de reconnaissance ni un avant/après de production.
Les artefacts de cette session sont disponibles dans le dossier de téléchargement
`audit-circulations` du chat. Ils ne sont pas ajoutés à GitHub avec les originaux.

**Premier résultat natif AI : non produit dans cet environnement.** Restent à
exécuter sur Adobe : extraction native, revue du vrai plan, génération, saveAs,
réouverture et vérification d’éditabilité. Les scripts sont fournis pour cette
recette ; aucune réussite Adobe n’est déclarée sur la base des seuls tests locaux.
