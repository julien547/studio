# Comparer un référentiel Qwen sur un plan

Cette livraison raccorde la page Entraînement à deux inférences Qwen : une avec le
prompt habituel, l’autre avec les conventions de la version sélectionnée. Le modèle
lit la même page source dans les deux cas. Ce n’est pas un fine-tuning ; aucun poids
ni pointeur de production n’est modifié. Les tests exécutés ici sont locaux avec
sorties de modèle simulées. Aucune inférence réelle ni intervention serveur n’a été
réalisée par cette session.

## Parcours administrateur

1. Dans **Qwen → Modèles IA**, enregistrer une version du référentiel à partir d’un
   dataset autorisé et validé, contenant des groupes indépendants train/validation/test.
   Ses conventions proviennent uniquement du lot train.
2. Dans la carte de version, cliquer **Comparer Qwen sur un plan**. Choisir un
   exemple du lot test ; un exemple d’entraînement ne peut pas être sélectionné.
3. Cliquer **Lancer les deux analyses Qwen** et confirmer le coût potentiel. Deux
   tâches persistantes sont ajoutées à la file d’analyses existante. Son contrôleur
   peut démarrer le GPU selon la configuration OVH autorisée. Le lancement n’attend
   pas les inférences dans la requête HTTP du navigateur.
4. Lire les résultats **Sans référentiel** et **Avec ce référentiel**, avec leurs
   états et erreurs séparés. Le texte lu et l’interprétation métier proposée restent
   distincts et incertains. La page source est consultable. L’interprétation attendue
   est affichée pour l’administrateur ; elle n’est pas envoyée au modèle.
5. Lorsque les deux tâches sont terminées, enregistrer un avis motivé : meilleur avec,
   meilleur sans, équivalent ou non concluant. L’avis conserve auteur/date et audit.
   Il ne constitue ni une approbation du modèle ni une autorisation de publication.

Le bouton **Tester le référentiel** existant reste un test lexical sur CPU. Il est
distinct de cette nouvelle comparaison par inférence. Les résultats de comparaison
ne sont pas ajoutés aux analyses du projet visibles par les dessinateurs et ne
peuvent pas être appliqués à un plan de production par la route d’application.

## Fichiers et installation — session de déploiement uniquement

| Fichier | Fonction |
| --- | --- |
| `backend/doemo_releves/qwen_preview.py` | Admission administrative, paire de tâches, contrôle et historique |
| `backend/doemo_releves/migrations/005_qwen_previews.sql` | Persistance des comparaisons, clés et avis |
| `backend/doemo_releves/queue.py` | Envoi du contexte figé et vérification de son accusé de réception |
| `backend/doemo_releves/studio_api.py` | Séparation des comparaisons et des analyses de production |
| `backend/doemo_releves/ai_contracts.py` | Interprétation Qwen séparée du texte visible |
| `services/runpod/qwen_prompt.py` | Contrat borné des conventions, prompt et empreintes |
| `services/runpod/gateway.py`, `infer.py` | Contexte authentifié, déduplication et utilisation dans le modèle |
| `services/runpod/training_service.py` | Empreinte du runtime incluant le nouveau module Qwen |
| `web/src/training/QwenPreview.tsx` | Comparaison visuelle, historique et avis humain |

La session de déploiement doit examiner et reprendre le code de la même révision,
préserver ses secrets/chemins, vérifier la sauvegarde restaurable puis livrer le
backend et reconstruire le frontend. Le Store applique automatiquement `005` une
seule fois ; les migrations précédentes restent nécessaires.

Sur le Pod, livrer ensemble les modules `services/runpod/` concernés. Aucun nouveau
package Python n’est requis par cette comparaison. Les environnements et modèles
Qwen existants doivent déjà avoir passé leur recette d’inférence. Une version
ancienne du gateway qui ignore le contexte est refusée par le worker OVH : aucun
résultat n’est présenté comme comparaison valide sans accusé des empreintes.

**Impact RTMDet :** le profil accepté lie le hash du runtime, dont le gateway et
l’adaptateur d’inférence. Cette modification invalide un ancien profil d’entraînement.
La session de déploiement doit organiser le déploiement sans tâche en cours et refaire
la recette `accept_training.py` avant de réactiver ce profil, suivant
[ENTRAINEMENT-RTMDET.md](ENTRAINEMENT-RTMDET.md). Ne pas remplacer ses empreintes à la
main. Cette session n’effectue aucune de ces opérations serveur.

## Contrat et persistance

Sous `/projects/training/models/qwen/{version_id}` :

- `GET /preview-options` : exemples réservés au test, autorisation de réutilisation contrôlée.
- `POST /previews` : `example_id`, `confirmed:true`, `request_key` (16–80 caractères,
  lettres/chiffres/tiret/underscore). Crée les deux tâches dans une seule transaction.
- `GET /previews` : 50 dernières comparaisons, avec les deux états/résultats et l’avis.
- `POST /previews/{id}/review` : `verdict` (`candidate_better`, `same`,
  `baseline_better`, `inconclusive`) et `notes` obligatoires. Refus avant la fin des
  deux inférences. Le changement d’avis est journalisé.

Toutes ces routes exigent `admin` ou `administration`. Le navigateur passe par le
relais PHP/session ou le middleware autonome existant ; aucun jeton GPU n’est exposé.

Une clé de demande répétée pour le même exemple/version renvoie la même paire de
tâches. Sa réutilisation avec d’autres paramètres renvoie 409. Le formulaire conserve
la clé après erreur tant qu’il reste monté. Après rechargement de page, consulter
l’historique avant un nouveau lancement. En cas d’échec définitif, un nouveau lancement
confirmé crée une nouvelle paire ; il ne réécrit pas les résultats précédents.

Le contexte `doemo.qwen-reference/1` contient seulement la version, ses règles du
lot train et leur SHA-256. Il est limité à 100 conventions et 32 Kio, sans troncature
silencieuse. Le contrôle du consentement et des liaisons est répété avant chaque
envoi d’image. L’empreinte PNG est figée à l’admission et contrôlée avant l’envoi et
au retour ; une page modifiée entre les appels invalide la comparaison.

Le gateway inclut le contexte dans sa clé de déduplication. Même identifiant avec
une autre version/règle/image : refus 409. Il conserve `reference.json`, les résultats
et les métadonnées dans `/workspace/doemo-studio/jobs/<job_id>`. Les fichiers de calcul
restent dans `/tmp`. La réponse comporte les empreintes du contexte et du prompt ;
le worker vérifie le contexte et l’image avant d’enregistrer le résultat sur OVH.

Les tâches utilisent le worker d’analyse existant et comptent dans la protection
contre l’arrêt GPU. Le mécanisme de pause RTMDet pour priorité à l’inférence est
réutilisé. Aucun nouveau service, aucune migration ou action RunPod n’est exécuté
par le simple affichage de cette page.

## Portée des résultats

Le texte des conventions est fourni comme vocabulaire métier et reste une donnée,
jamais une commande à exécuter. Les résultats restent incertains, sans coordonnées
inventées ni équipement automatiquement créé. Le contrôle humain reste nécessaire.

Cette comparaison est un diagnostic visuel, sans score automatique d’amélioration.
Elle ne vérifie pas cryptographiquement les poids du serveur entre les deux appels.
La session de déploiement doit donc maintenir le même modèle/configuration pendant
la recette. Une évaluation comparative reproductible avec poids attestés, puis
l’approbation/publication/rollback restent à développer. Les capacités de promotion
restent désactivées même après un avis humain favorable.

Le fine-tuning Qwen/PaddleOCR et le réseau architectural restent également à
implémenter. Les packages d’inférence PaddleOCR ne suffisent pas à identifier un
trainer de reconnaissance compatible : sa configuration/dépôt d’entraînement doivent
être établis par la session de déploiement avant d’écrire cet adaptateur spécifique.

## Vérifications locales

126 tests backend et 7 parcours Playwright réussis, avec build TypeScript validé.
Le test de protocole traverse la vraie API, SQLite, le worker et le gateway locaux,
mais remplace l’exécution du modèle par une fixture CPU clairement identifiée.
Le test navigateur rejoue également des sorties de fixture, vérifie l’affichage
comparatif, l’avis humain et sa conservation après rechargement. Aucun de ces tests
ne prouve la qualité ou la disponibilité du vrai Qwen sur RunPod.
