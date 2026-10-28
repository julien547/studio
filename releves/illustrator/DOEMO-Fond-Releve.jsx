#target illustrator
/* Standalone template. The delivery build embeds the already registered PNG.
   Run in Illustrator 2024+ with the target AI open. No PDF-to-AI conversion. */
(function () {
    var encoded = "__DOEMO_REGISTERED_PNG_BASE64__";
    var stage = "Verification du document", layer = null, temporary = null;
    var saved = false, coordinates = app.coordinateSystem;
    var layerName = "DOEMO - RELEVE DE CONTROLE - NON VALIDE";
    function decode(input) {
        var alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        var output = [], value = 0, bits = 0, i, n;
        for (i = 0; i < input.length; i++) {
            if (input.charAt(i) === "=") break;
            n = alphabet.indexOf(input.charAt(i));
            if (n < 0) throw Error("Image integree invalide.");
            value = (value << 6) | n; bits += 6;
            if (bits >= 8) { bits -= 8; output.push(String.fromCharCode((value >> bits) & 255)); }
        }
        return output.join("");
    }
    try {
        if (parseInt(app.version, 10) < 28) throw Error("Illustrator 2024 ou plus recent requis.");
        if (!app.documents.length) throw Error("Ouvrir le plan CO26100239-1.ai, ou votre copie de ce plan avec les pictogrammes.");
        var doc = app.activeDocument;
        if (doc.artboards.length !== 1) throw Error("Ce fond est prepare pour le plan Animalis avec un seul plan de travail.");
        app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        var rect = doc.artboards[0].artboardRect;
        var width = rect[2] - rect[0], height = rect[1] - rect[3];
        if (Math.abs(width - 841.890991) > 0.2 || Math.abs(height - 1190.550049) > 0.2)
            throw Error("Dimensions differentes du plan Animalis attendu : 841,89 x 1190,55 pt.");
        for (var i = 0; i < doc.layers.length; i++)
            if (doc.layers[i].name === layerName) throw Error("Le calque du releve existe deja. Aucun doublon ajoute.");
        if (encoded.indexOf("__DOEMO_") === 0) throw Error("Utiliser le script livre avec le releve integre, pas le modele source.");

        stage = "Choix de la nouvelle copie AI";
        var output = File.saveDialog("Enregistrer une nouvelle copie du plan avec le releve", "*.ai");
        if (!output) return;
        if (!/\.ai$/i.test(output.name)) output = File(output.fsName + ".ai");
        if (output.exists) throw Error("Choisir un nouveau nom : aucun fichier existant ne sera ecrase.");

        stage = "Preparation du releve integre";
        var folder = Folder(Folder.temp.fsName + "/DOEMO-releve-" + new Date().getTime() + "-" + Math.floor(Math.random() * 1000000));
        if (folder.exists || !folder.create()) throw Error("Impossible de creer le dossier temporaire.");
        temporary = File(folder.fsName + "/releve.png");
        temporary.encoding = "BINARY";
        if (!temporary.open("w")) throw Error("Impossible de preparer l'image du releve.");
        var bytes = decode(encoded);
        try { if (!temporary.write(bytes)) throw Error("Ecriture du releve impossible."); }
        finally { temporary.close(); }
        if (temporary.length !== bytes.length) throw Error("Image temporaire incomplete.");

        stage = "Insertion du calque d'arriere-plan";
        layer = doc.layers.add(); layer.name = layerName;
        layer.zOrder(ZOrderMethod.SENDTOBACK);
        var item = layer.placedItems.add(); item.file = temporary;
        item.width = width; item.height = height; item.position = [rect[0], rect[1]];
        stage = "Incorporation du releve dans le document";
        item.embed();
        if (layer.placedItems.length || layer.rasterItems.length !== 1)
            throw Error("Le releve n'a pas ete incorpore correctement.");
        var raster = layer.rasterItems[0];
        // Reassert full-page alignment after Illustrator's native embed operation.
        raster.width = width; raster.height = height; raster.position = [rect[0], rect[1]];
        raster.name = "RELEVEDEUX - RDC et R-1 recales - controle provisoire";
        raster.note = "Releve incorpore, recale separement par niveau. Positions non validees. Erreurs de controle : RDC 8,75 px ; R-1 6,32 px (seuil 5 px).";
        layer.opacity = 45; layer.locked = true;

        stage = "Enregistrement de la copie Illustrator";
        var options = new IllustratorSaveOptions(); options.pdfCompatible = true; options.compressed = true;
        doc.saveAs(output, options); saved = true;
        app.redraw();
        alert("Copie AI enregistree : " + output.name + "\nLe releve est incorpore au fond, dans un calque verrouille a 45 %.\nLes calques du plan et les pictogrammes deja presents sont conserves.\nVerifier visuellement le calage ; les positions restent provisoires.");
    } catch (error) {
        if (layer && !saved) { try { layer.locked = false; layer.remove(); } catch (cleanupError) {} }
        alert("DOEMO - Etape : " + stage + "\n" + error.message + "\nAucun fichier existant n'a ete ecrase. Une copie partielle eventuelle n'est pas validee.");
    } finally {
        app.coordinateSystem = coordinates;
        if (temporary) { try { temporary.remove(); temporary.parent.remove(); } catch (tempError) {} }
    }
}());
