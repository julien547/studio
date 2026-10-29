"""Adaptateur d'entraînement des MURS : relevé client -> segmentation sémantique (contrat de segmentation/run_onnx.py).

Le modèle produit un raster de 11 classes (wall_module.CLASSES) ; seules « background » et « wall » sont apprises ici.
Le raster passe ensuite par wall_module.reconstruct_mask (axe médian) : aucune boîte RTMDet n'est un mur."""
CLASSES = ['background', 'wall', 'partition', 'door', 'window', 'stairs', 'text',
           'annotation', 'furniture', 'symbol', 'room']
