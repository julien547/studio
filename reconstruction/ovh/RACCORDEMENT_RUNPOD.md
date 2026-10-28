# Raccorder réellement les trois IA à l’éditeur OVH

Transmission à la session qui déploie OVH et à celle qui prépare l’image RunPod.
Livraison 0.3.6, branche `feat/redessin-ovh-tests`, [PR Studio 1](https://github.com/julien547/studio/pull/1).
Commencer par [INSTALLATION-CONNEXION-IA.md](../../INSTALLATION-CONNEXION-IA.md) :
configuration OVH, clés, lancement automatique RunPod et préservation du menu actuel.
**Le raccordement réel n’a pas été exécuté depuis cette session.** Les chemins
d’environnements restaurés sont ceux confirmés par le propriétaire. Les valeurs
d’exemple ne sont pas des coordonnées de connexion opérationnelles.

## Résultat à obtenir

Depuis `https://studio.doemo.fr/redessin/`, « Vérifier la connexion aux IA » doit
confirmer les trois moteurs, puis « Analyser la page avec les trois IA » doit
produire les réponses de PaddleOCR, Qwen et RTMDet pour **la page 1 de `2(2).pdf`**.
La présence d’une URL, une réponse HTTP 200 ou le succès des tests locaux ne
suffisent pas. Le contrôle de disponibilité ne transmet aucun plan et ne lance
aucune inférence ; le test sur la page est une action distincte.

| Emplacement | Composants |
| --- | --- |
| OVH, sans GPU | Application PHP, service `doemo-redessin`, projets privés, clé de signature privée, client HTTP signé |
| RunPod RTX A6000 | Worker Python, trois adaptateurs exécutés dans les trois venvs existants, clé de vérification publique |
| Volume RunPod `/workspace/doemo-studio` | Modèles, configuration locale et résultats persistants ; aucun venv installé sur FUSE |

## 1. Service sur RunPod

Suivre [TEST_DEPLOIEMENT.md](../runpod/TEST_DEPLOIEMENT.md) dans l’image privée
versionnée préparée par la session infrastructure. Conserver les environnements
`/opt/doemo-qwen-venv`, `/opt/doemo-ocr-venv`, `/opt/doemo-rtmdet-venv`.
Vérifier leurs fichiers et les sauvegardes avant toute réparation. Ce paquet ne
réinstalle aucun moteur et ne contient aucun poids.

Le worker attend une configuration locale `models.json` avec les chemins réellement
observés du modèle Qwen, des modèles détection/reconnaissance PaddleOCR et de la
configuration/checkpoint RTMDet. L’exemple du dépôt contient des champs à renseigner.
Ne pas remplacer une configuration existante par cet exemple.

Faire lancer automatiquement `runpod/serve_test.py` par le superviseur de l’image,
avec son environnement léger séparé et les variables décrites dans la procédure.
Conserver **un seul processus worker** pour sérialiser l’utilisation du GPU.
Les inférences de démarrage sont séquentielles et peuvent prendre plusieurs minutes.
Un processus présent ou CUDA disponible ne prouve pas leur réussite.

Si un service IA existe déjà, vérifier ses routes et son contrat avant de le
réutiliser. Le client de cette livraison attend `/health`, `/models` et
`POST /infer/{uuid}` avec le contrat de `ai_service/worker.py`. Un autre format
requiert un adaptateur explicite ; ne pas diriger ce client vers une API différente
et ne pas lancer un deuxième worker concurrent pour contourner le problème.

## 2. Transport et authentification OVH–RunPod

La session infrastructure fournit soit un tunnel privé permanent, exposé en boucle
locale sur OVH vers `127.0.0.1:8009` sur RunPod, soit une URL HTTPS privée compatible.
Le tunnel ou le proxy doit supporter une inférence pouvant durer 2 800 secondes.
Ne pas utiliser l’ancienne adresse IP ni l’ancien identifiant du Pod présents dans
les captures : le contrôleur existant doit retrouver le Pod courant après migration.
Le module de redessin ne démarre, n’arrête et ne migre aucun Pod.

Utiliser une paire de signature **Ed25519 PEM**, distincte de la clé SSH : la clé
privée PKCS8 reste sur OVH, seule la clé publique est copiée sur RunPod. Réutiliser
la paire de service existante si elle convient. Ne jamais copier une clé privée
dans GitHub, l’image, le navigateur ou le compte rendu. La commande de contrôle
ci-dessous utilise la configuration du service OVH ; elle n’affiche aucune clé.

Sur OVH, renseigner `/etc/doemo-redessin/service.env` avec l’URL réelle du tunnel
ou du service HTTPS et le chemin réel du fichier de signature :

```text
DOEMO_RUNPOD_URL=http://127.0.0.1:PORT_REEL_DU_TUNNEL
DOEMO_OVH_PRIVATE_KEY=/etc/doemo-redessin/worker-signing-private.pem
```

Le port ci-dessus est à remplacer. Faire lire la clé uniquement par le compte de
service autorisé ; le processus `doemo-redessin` doit pouvoir traverser son dossier.
Après vérification de l’absence de tâches actives ou interrompues, redémarrer le
service du redessin pour charger cette configuration. Ne pas redémarrer le GPU.
Le contrôleur d’inactivité de l’autre session doit tenir compte du worker actif et
des résultats non sauvegardés avant toute décision d’arrêt.

## 3. Vérifier le service actif depuis OVH

Après installation de la version 0.3.6 selon [DEPLOIEMENT_OVH.md](DEPLOIEMENT_OVH.md) :

```bash
sudo -u doemo-redessin /opt/doemo-redessin/venv/bin/python \
  /opt/doemo-redessin/current/ovh/check-connection.py
```

La commande interroge le socket privé du service effectivement démarré. Le code
de sortie 0 signifie `state: ready`, `can_analyze: true` et un test de démarrage
confirmé pour chaque moteur. Le code 1 signale un raccordement non prêt ; le code 2
signale un problème de contrôle du service OVH. Aucun test n’installe de modèle.

| État retourné | Vérification à faire |
| --- | --- |
| `not_configured` | Les deux paramètres ne sont pas chargés dans le service OVH |
| `key_unavailable` | Chemin et droits de lecture du fichier de signature OVH |
| `unavailable` | Pod courant, tunnel/proxy privé et service worker |
| `authentication_failed` | Correspondance clé privée/publique et horloges système |
| `invalid_configuration_or_contract` | Format de clé, identité du worker, trois modèles et versions sans placeholders |
| `starting` | Attendre ou examiner les tests de démarrage des moteurs dans les journaux privés |
| `not_ready` | Erreur de démarrage ou résultat persistant à réconcilier |
| `busy` | Travail en cours ou worker en cours de mise à l’arrêt |
| `ready` | Lancer la recette sur le plan ; la qualité architecturale reste à contrôler |

Depuis 0.3.4, chaque entrée de `engines` contient aussi `startup_state` et un
`error_code` éventuel. Les détails techniques restent dans les journaux privés :

| Code du moteur | Contrôle ciblé |
| --- | --- |
| `gpu_unavailable` | Vérifier le GPU du Pod courant et `nvidia-smi` ; aucune conclusion sur la présence des venvs |
| `timeout` | L’inférence a dépassé 900 secondes ; examiner les journaux et l’utilisation du GPU |
| `invalid_output` | Réponse absente, incomplète ou incompatible avec le contrat ; vérifier l’adaptateur et les versions locales |
| `inference_failed` | Échec du processus du moteur ; examiner `/workspace/doemo-studio/exports/engine-logs/` |

Un échec n’empêche pas le contrôle des deux autres moteurs. Il ne lance aucune
réinstallation ni nouvel essai en boucle. Le bouton d’analyse reste bloqué tant
que les trois moteurs n’ont pas réussi. Pendant les contrôles, le worker refuse
`/drain` et retourne `stop_safe: false` au contrôleur d’arrêt existant.

Une réponse Qwen doit couvrir chaque zone demandée, une fois, en utilisant
`unknown`/`uncertain: true` si nécessaire. Une liste OCR ou RTMDet vide est valide
si aucun texte ou objet n’est trouvé, mais une liste manquante ou des coordonnées
hors image sont refusées. Ces contrôles ne mesurent pas la précision des modèles.

## 4. Recette réelle indispensable

1. Vérifier que l’accès au worker sans signature est refusé.
2. Se connecter à Studio avec le rôle dessinateur et ouvrir le projet de la page 1.
3. Cliquer « Vérifier la connexion aux IA », puis « Analyser la page avec les trois IA ».
4. Attendre l’état terminé et contrôler les observations reçues, les versions et
   les trois résultats dans la tâche privée. Conserver son UUID et l’identité du
   worker dans le compte rendu interne ; aucun contenu client dans GitHub.
5. Recharger le projet : les observations doivent persister et les corrections
   des murs doivent rester intactes. Aucune observation ne valide un mur.
6. Répéter le contrôle de connexion après le redémarrage normal prévu par l’autre
   session. Vérifier la redécouverte et les tests de démarrage sans commande Jupyter.

Après un délai réseau dépassé, ne pas rejouer une tâche interrompue : vérifier son
UUID dans les résultats persistants RunPod avant réconciliation. Le worker peut
continuer à calculer alors qu’OVH a perdu la connexion.

Le raccordement des trois IA permet l’OCR, les observations de zones et un diagnostic
RTMDet. **Le modèle spécialisé de segmentation des murs reste à sélectionner et
qualifier** ; il n’est pas fourni par le checkpoint RTMDet COCO. Un mur exporté
reste un seul trait noir plein sur son axe médian, soumis à validation humaine.
