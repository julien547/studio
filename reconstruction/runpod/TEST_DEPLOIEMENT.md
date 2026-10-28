# Tester les trois IA sur RunPod

Ce paquet prépare un essai d’inférence privée sur la **page 1 de `2(2).pdf`**.
Les trois environnements ont été déclarés restaurés et vérifiés par le propriétaire.
Ce service doit encore être exécuté contre ces installations pour confirmer ses adaptateurs.
La [transmission commune OVH–RunPod](../ovh/RACCORDEMENT_RUNPOD.md) rassemble les
paramètres des deux côtés et les critères de raccordement de la page Studio.
Il ne constitue pas encore le redessin automatique des murs : la segmentation spécialisée
reste à qualifier. RTMDet COCO sert uniquement à vérifier une inférence d’objets génériques.

## À transmettre à la session Docker

Intégrer ce service à l’image privée versionnée que cette session prépare. Conserver
les trois environnements existants dans `/opt`. Prévoir un environnement Python 3.12
séparé `/opt/doemo-service-venv` pour `requirements-test-service.txt` et copier le code
de ce paquet sous `/opt/doemo-inference-test`. Les dépendances du service sont installées
pendant la construction de l’image, jamais à chaque démarrage. Geler aussi leurs
dépendances transitives dans la construction reproductible de l’image.

Ce paquet ne contient ni Dockerfile ni gestion du démarrage ou de l’arrêt du Pod.
Il ne restaure pas d’archive et n’installe aucun modèle. L’autre session conserve
la responsabilité de l’image, du volume persistant et du transport OVH–RunPod.

Le paquet de test privé contient une image du plan client : ne pas l’intégrer à
l’image Docker ni la publier dans GitHub. Les seuls répertoires à copier dans
l’image sont `doemo_reconstruction/` et `runpod/`. Le dossier `sample/` reste sur
OVH pour l’essai. Aucun poids ni secret n’est fourni.

## Configuration du worker sur RunPod

Créer une configuration locale à partir de `runpod/models.example.json` sans écraser
une configuration existante. Renseigner les chemins **observés sur le Pod courant**
des modèles détection/reconnaissance PaddleOCR et de la configuration/checkpoint
RTMDet. Le chemin Qwen est déjà indiqué. Renseigner des versions locales vérifiées
et figées ; les libellés contenant `to-verify` sont refusés. Ne pas télécharger
d’autres poids pour faire disparaître une erreur de configuration.

Variables du service à définir dans le template ou le superviseur :

```text
DOEMO_MODELS_CONFIG=/workspace/doemo-studio/config/models.json
DOEMO_OVH_PUBLIC_KEY=/workspace/doemo-studio/config/ovh-worker-public.pem
DOEMO_RUNPOD_RESULTS=/workspace/doemo-studio/exports/ai-jobs
```

`RUNPOD_POD_ID` est fourni par RunPod au conteneur courant : ne pas coder une ancienne
valeur. `DOEMO_ENGINE_RUNNER` est déduit de l’installation du paquet. Les résultats
et journaux d’erreur restent sur le volume persistant ; les fichiers temporaires
sont sous `/tmp`. Le worker n’utilise pas SQLite sur le volume FUSE/geesefs.

La session Docker configure cette commande comme démarrage automatique du service :

```bash
/opt/doemo-service-venv/bin/python /opt/doemo-inference-test/runpod/serve_test.py
```

L’écoute par défaut est `127.0.0.1:8009`, utilisable via tunnel SSH privé depuis OVH.
Pour un transport HTTPS privé terminé par un proxy, le lancement peut préciser
`--host 0.0.0.0 --behind-tls-proxy`. Ce drapeau ne crée pas TLS : le proxy et les
restrictions réseau doivent être réellement configurés par la session infrastructure.
Le client refuse HTTP hors boucle locale et ne désactive jamais la vérification TLS.

Les trois moteurs réalisent une inférence de démarrage sur une petite image de test,
séquentiellement pour libérer la VRAM entre modèles. `/health` ne passe à `ready: true`
que si les trois appels ont réussi. `/models` distingue présence des environnements
et inférence réussie. Un seul processus Uvicorn est autorisé pour conserver le verrou GPU.

## Authentification et essai depuis OVH

Utiliser une paire **Ed25519 de signature de service au format PEM**, distincte de la
clé SSH. La clé privée PKCS8 reste sur OVH dans un fichier réservé au compte de service ;
seule la clé publique SubjectPublicKeyInfo est copiée sur RunPod. Réutiliser la paire
de service prévue par l’autre session si elle existe. Une création initiale peut être
faite par cette session avec `openssl genpkey -algorithm Ed25519`, puis
`openssl pkey -pubout`, dans le gestionnaire de secrets prévu. Ne jamais inclure la clé
privée dans l’image, les archives, une Page ou une variable exposée au navigateur.

Chaque appel utilise un jeton signé valable 120 secondes, vérifié à l’admission.
Les routes `/health`, `/models`, `/infer/{uuid}` et `/drain` nécessitent ce jeton.
La route d’inférence est synchrone pour cet essai. Le transport doit tolérer jusqu’à
2 800 secondes sans réponse pendant le calcul ; utiliser le tunnel ou le proxy privé
configuré en conséquence. Ne pas supposer que le proxy HTTP public RunPod accepte
ce délai. Le module web 0.3.1 place cette requête dans une tâche OVH persistante et
le navigateur suit son état ; la requête OVH vers le worker reste synchrone.

Avec le tunnel exposant le service sur `127.0.0.1:8009` côté OVH, exécuter une fois
depuis la racine du paquet (le même environnement de dépendances légères est nécessaire
sur OVH, sans CUDA ni installation des trois IA) :

```bash
/opt/doemo-service-venv/bin/python runpod/probe_client.py \
  --url http://127.0.0.1:8009 \
  --private-key /etc/doemo/worker-signing-private.pem \
  --image sample/page-1.png \
  --manifest sample/page-1.manifest.json \
  --output /var/lib/doemo/inference-tests/page-1-premier-essai
```

Adapter le chemin de la clé à celui réellement géré sur OVH. Pour un endpoint privé
HTTPS, remplacer uniquement `--url`. Le client attend la disponibilité, lit les
versions actives puis demande une analyse par PaddleOCR, Qwen et RTMDet. Il n’appelle
aucune API RunPod de démarrage, arrêt, migration ou suppression.

Le dossier de résultat contient :

- `request-receipt.json` : identifiant unique sauvegardé avant l’envoi et provenance du plan.
- `evidence.json` : réponses des moteurs, versions, identité du Pod et empreintes des données.
- `report.json` : confirmation technique du retour des inférences, sans validation architecturale.

Après un délai réseau dépassé, relancer avec **le même dossier de résultat**. Le même
identifiant est réutilisé et un résultat déjà committé est relu sans refaire les calculs.
Une configuration ou une image différente nécessite un nouveau dossier. Ne pas relancer
automatiquement un essai dont la provenance ou l’identité du worker est incohérente.

## Critères de réception

1. Un appel sans signature est refusé. La configuration d’exemple incomplète ne démarre pas.
2. Les trois inférences de démarrage passent sur le GPU courant et `/models` le confirme.
3. L’essai page 1 produit les trois réponses avec les empreintes et les versions attendues.
4. La même requête relancée relit son résultat persistant sans nouveau calcul.
5. Le dessinateur vérifie les textes et observations ; aucune sortie n’est un mur validé.

La page 1 est conservée dans son orientation PDF d’origine, à 1 787 × 1 263 pixels.
Le manifeste contient la conversion vers les points du PDF, sans échelle métrique.
Le scan étant à l’envers dans le document, ce premier essai mesure surtout le raccordement.
L’orientation, la résolution native et les zones de lecture devront être traitées avant
d’évaluer la précision OCR. Qwen classe uniquement les zones fournies : ici la page entière.

La règle DOEMO reste **un mur = un trait noir plein sur l’axe médian**, avec ouvertures
préservées et validation humaine. Ni le succès de cet essai ni une boîte RTMDet ne
valident un redessin architectural. Aucun déploiement sur RunPod n’a été effectué depuis
cet environnement Codex, dont l’accès réseau RunPod n’est pas configuré.
