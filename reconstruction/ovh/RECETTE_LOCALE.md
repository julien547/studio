# Vérification de la livraison OVH 0.3.1

Le 28 octobre 2026, 64 tests Python passent. Ils couvrent les axes noirs, les
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
