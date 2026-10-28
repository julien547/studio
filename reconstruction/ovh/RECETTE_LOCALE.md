# Vérification de la livraison OVH 0.3.4

Le 28 octobre 2026, 111 tests Python passent. Ils couvrent les axes noirs, les
ouvertures, la validation humaine, les contrats d’inférence, l’authentification
du worker, les reprises après interruption, l’isolation des projets par utilisateur
et la détection des sauvegardes concurrentes. Les tests d’IA utilisent des doubles ;
aucun modèle RunPod n’a été appelé depuis cette session.

Les tests ajoutés vérifient les états de connexion, les trois inférences de
démarrage déclarées par le worker, le rejet des versions non renseignées,
l’authentification et l’absence de données privées dans les erreurs publiques.
Un parcours HTTP signé relie le workbench au vrai code du worker avec des moteurs
simulés : les trois adaptateurs répondent, les observations sont enregistrées et
les murs ne changent pas. Cela ne remplace pas la recette du GPU RunPod réel.

Le contrôle de connexion passe aussi dans Chromium : route PHP réelle protégée par
session et état non configuré ; états prêt, occupé, authentification refusée et
service injoignable simulés pour vérifier l’activation du bouton d’analyse.
La commande sur socket retourne bien le code 1 quand RunPod n’est pas configuré.

La syntaxe des deux fichiers PHP passe avec PHP 8.4.27. Les scripts JavaScript et
le script shell d’installation passent leurs vérifications de syntaxe. Le code de
l’éditeur intégré est construit depuis le même éditeur que le prototype autonome.

Un parcours Chromium a été exécuté avec la véritable API PHP, sa session de test,
le socket Unix du backend Python, le worker et le stockage SQLite locaux. Seuls
le domaine attendu et la session ont été adaptés dans une copie de configuration
réservée au test. Les sources destinées à OVH conservent `https://studio.doemo.fr`.

Le parcours vérifie : API refusée sans session ; import de la page 1 de `2(2).pdf` ;
extraction terminée ; affichage de 327 propositions ; sélection et approbation
scriptée d’un axe ; sauvegarde serveur ; réouverture ; téléchargement d’un SVG
contenant un tracé noir ouvert ; refus d’une requête d’origine étrangère. Aucun
erreur JavaScript n’est relevée. Cette approbation de test n’est pas une annotation
humaine pour l’apprentissage. Aucun fichier du plan n’est inclus dans ce dépôt.

Les 327 propositions viennent du traitement géométrique de cette livraison ;
elles diffèrent du regroupement expérimental à 101 axes livré auparavant. Ces
comptages ne constituent ni une précision mesurée ni une validation architecturale.
La référence PDF est conservée dans son orientation d’origine, sans échelle inventée.

Restent à effectuer par la session de déploiement : installation et recette sur
le VPS OVH réel, vérification du transport RunPod, inférences réelles des trois
adaptateurs, coordination du contrôleur d’inactivité, et contrôle dans Illustrator.
Le modèle spécialisé de murs reste à qualifier avant tout redessin sémantique.

La [recette 0.3.2](CORRECTION_AXES.md) ajoute la conservation des portions de bords
non utilisées et la correction explicite « Deux bords → un axe médian ». Le parcours
Chromium de cette commande passe avec annuler/refaire, conservation des extrémités
restantes et protection des ouvertures. Le nouvel essai page 1 produit 381
propositions non validées. Les 327 propositions décrites plus haut concernent
le parcours complet de la livraison initiale ; aucun taux de qualité n’est déduit.

La livraison 0.3.3 ajoute la configuration idempotente OVH : création ou réutilisation
de la paire de signature, sauvegarde hors du web, refus des URL incomplètes et
absence de rotation implicite. Le lanceur RunPod et un fragment pour le superviseur
de l’image existante sont fournis, sans réinstallation des trois moteurs.

Un parcours navigateur dans une iframe, avec menu parent visible, session PHP,
socket Unix, stockage SQLite et vrai transport HTTP signé vers le code du worker,
vérifie les trois adaptateurs simulés, l’affichage OCR/zones et la conservation des
murs. Une erreur d’aller-retour JSON du pont PHP a été corrigée : les objets vides
restent des objets, au lieu de devenir des tableaux qui bloquaient la sauvegarde.
Les bandeaux sont absents du wrapper et de l’éditeur intégré. Aucun GPU réel n’a
été appelé ; la recette RunPod reste à exécuter par la session de déploiement.

La livraison 0.3.4 contrôle les sorties avant de déclarer une inférence réussie :
Qwen couvre toutes les zones demandées ; les coordonnées et scores sont finis et
bornés ; les listes OCR/RTMDet ne peuvent pas être tronquées silencieusement.
Un test avec un véritable sous-processus et un runner synthétique vérifie que la
configuration reste celle du démarrage et qu’une réponse vide de Qwen est refusée.
Les appels PaddleOCR 3 et Qwen sont testés avec des doubles de leurs bibliothèques,
sans installer leurs dépendances GPU. Le paramètre `enable_thinking=False` demande
une réponse JSON directe au template local Qwen ; son comportement effectif reste
à vérifier avec la version Transformers et le modèle présents sur RunPod.

Les tests vérifient aussi que le démarrage contrôle les trois moteurs malgré un
échec, que les états ne divulguent pas les messages privés, et qu’un arrêt ne peut
pas être préparé pendant ces inférences. Les règles des axes noirs, des ouvertures
et de la validation humaine restent couvertes par la suite complète.

Le parcours Chromium 0.3.4 repasse avec PHP, socket Unix, worker HTTP signé et
trois moteurs simulés : menu/iframe conservés, observations persistantes, murs
inchangés. Une réponse de statut simulant l’échec de PaddleOCR affiche cet échec,
conserve les succès de Qwen/RTMDet et désactive l’analyse. Aucun appel GPU réel.
