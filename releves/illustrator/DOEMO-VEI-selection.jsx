#target illustrator
(function () {
    var etape = "Verification de la selection";
    try {
        if (!app.documents.length)
            throw Error("Ouvrir la legende et selectionner le VEI complet.");
        var source = app.activeDocument;
        var selection = source.selection;
        if (!selection || !selection.length || selection.typename === "TextRange")
            throw Error("Selectionner les objets du VEI avec la fleche noire (V), pas du texte en cours de saisie.");

        etape = "Choix du fichier de sortie";
        var fichier = File.saveDialog("Enregistrer sous VEI-DOEMO.ai", "*.ai");
        if (!fichier) return;
        if (!/\.ai$/i.test(fichier.name)) fichier = File(fichier.fsName + ".ai");
        if (fichier.exists) throw Error("Choisir un nouveau nom : ce fichier existe deja.");

        etape = "Copie du VEI selectionne";
        source.activate();
        app.copy();
        etape = "Creation du document";
        var resultat = app.documents.add(source.documentColorSpace, 300, 300);
        etape = "Collage des objets natifs";
        resultat.activate();
        app.paste();
        app.redraw();
        if (!resultat.selection || !resultat.selection.length)
            throw Error("Le collage est vide.");

        etape = "Ajustement du plan de travail";
        if (!resultat.fitArtboardToSelectedArt(0))
            throw Error("Impossible d'ajuster le plan de travail a la selection.");
        var r = resultat.artboards[0].artboardRect;
        resultat.artboards[0].artboardRect = [r[0]-2, r[1]+2, r[2]+2, r[3]-2];

        etape = "Enregistrement Illustrator";
        var options = new IllustratorSaveOptions();
        options.pdfCompatible = true;
        options.compressed = true;
        resultat.saveAs(fichier, options);

        etape = "Reouverture du fichier enregistre";
        resultat.close(SaveOptions.DONOTSAVECHANGES);
        resultat = app.open(fichier);
        if (resultat.artboards.length !== 1 || !resultat.pageItems.length)
            throw Error("Le fichier rouvert est vide ou contient plusieurs plans de travail.");
        alert("VEI-DOEMO.ai est enregistre et rouvert.\nVerifier la pastille, le texte, le trait et le point, puis renvoyer ce fichier AI dans le chat.");
    } catch (erreur) {
        alert("Etape : " + etape + "\nErreur : " + erreur.message + "\nLigne : " + erreur.line);
    }
})();
