#target illustrator
(function () {
  var src = null, dst = null, roots = [];
  var previous = app.coordinateSystem, region;
  function bytes(file) {
    file.encoding = "BINARY";
    if (!file.open("r")) throw Error("Lecture impossible : " + file.name);
    var value = file.read(); file.close(); return value;
  }
  function visible(item) {
    while (item && item.typename !== "Document") {
      if (item.hidden || (item.typename === "Layer" && !item.visible)) return false;
      item = item.parent;
    }
    return true;
  }
  function vector(item) {
    if (/^(RasterItem|PlacedItem|PluginItem|NonNativeItem)$/.test(item.typename))
      throw Error("Objet image ou non natif dans la sélection.");
    if (item.typename === "GroupItem")
      for (var i = 0; i < item.pageItems.length; i++)
        if (item.pageItems[i].parent === item) vector(item.pageItems[i]);
  }
  function collect(item) {
    if (!visible(item) || (item.typename === "PathItem" && item.guides)) return;
    var b = item.visibleBounds;
    if (b[2] <= region[0] || b[0] >= region[2] || b[1] <= region[3] || b[3] >= region[1]) return;
    if (b[0] >= region[0] && b[1] <= region[1] && b[2] <= region[2] && b[3] >= region[3]) {
      vector(item); roots.push(item); return;
    }
    if (item.typename !== "GroupItem" || item.clipped || item.opacity !== 100 || item.blendingMode !== BlendModes.NORMAL)
      throw Error("Un objet traverse la zone VEI. Extraction interrompue.");
    for (var i = 0; i < item.pageItems.length; i++)
      if (item.pageItems[i].parent === item) collect(item.pageItems[i]);
  }
  function layerItems(layer) {
    var i;
    for (i = 0; i < layer.pageItems.length; i++)
      if (layer.pageItems[i].parent === layer) collect(layer.pageItems[i]);
    for (i = 0; i < layer.layers.length; i++) layerItems(layer.layers[i]);
  }
  try {
    if (parseInt(app.version, 10) < 28) throw Error("Illustrator 2024 ou plus récent requis.");
    var input = File.openDialog("Choisir Légende OK - Copie (1).ai", "*.ai");
    if (!input) return;
    for (var i = 0; i < app.documents.length; i++) {
      var path = null;
      try { path = app.documents[i].fullName.fsName; } catch (ignored) {}
      if (path === input.fsName) throw Error("Fermer la légende dans Illustrator avant de relancer le script.");
    }
    var original = bytes(input);
    var output = File.saveDialog("Enregistrer sous VEI-DOEMO.ai", "*.ai");
    if (!output) return;
    if (!/\.ai$/i.test(output.name)) output = File(output.fsName + ".ai");
    if (output.exists) throw Error("Choisir un nouveau nom : ce fichier existe déjà.");
    app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
    src = app.open(input);
    if (src.artboards.length !== 4) throw Error("La légende attendue possède quatre plans de travail.");
    var r = src.artboards[0].artboardRect;
    var w = r[2] - r[0], h = r[1] - r[3];
    if (Math.abs(w - 1489.160034) > 0.1 || Math.abs(h - 1202.229980) > 0.1)
      throw Error("Les dimensions ne correspondent pas au fichier fourni.");
    region = [r[0] + w * 844 / 2400, r[1] - h * 40 / 1938,
              r[0] + w * 1010 / 2400, r[1] - h * 270 / 1938];
    for (i = 0; i < src.layers.length; i++) layerItems(src.layers[i]);
    if (!roots.length || roots.length > 100) throw Error("Sélection VEI vide ou trop étendue.");
    dst = app.documents.add(src.documentColorSpace, 200, 200);
    var group = dst.activeLayer.groupItems.add();
    group.name = "DOEMO - Vous etes ici";
    group.note = "DOEMO-VEI-EXTRAIT-LEGENDE";
    for (i = roots.length - 1; i >= 0; i--) roots[i].duplicate(group, ElementPlacement.PLACEATBEGINNING);
    var b = group.visibleBounds, width = b[2] - b[0], height = b[1] - b[3];
    if (width <= 0 || height <= 0) throw Error("Dimensions du VEI invalides.");
    var count = group.pageItems.length;
    dst.artboards[0].artboardRect = [b[0] - 2, b[1] + 2, b[2] + 2, b[3] - 2];
    src.close(SaveOptions.DONOTSAVECHANGES); src = null;
    var options = new IllustratorSaveOptions();
    options.pdfCompatible = true; options.compressed = true;
    dst.saveAs(output, options);
    dst.close(SaveOptions.DONOTSAVECHANGES); dst = null;
    dst = app.open(output);
    var found = null;
    for (i = 0; i < dst.groupItems.length; i++)
      if (dst.groupItems[i].note === "DOEMO-VEI-EXTRAIT-LEGENDE") found = dst.groupItems[i];
    if (!found || dst.artboards.length !== 1 || found.pageItems.length !== count)
      throw Error("Contrôle de réouverture en échec : résultat non validé.");
    vector(found); b = found.visibleBounds;
    if (Math.abs(b[2] - b[0] - width) > 0.05 || Math.abs(b[1] - b[3] - height) > 0.05)
      throw Error("Dimensions modifiées après sauvegarde : résultat non validé.");
    if (bytes(input) !== original) throw Error("Le fichier source a changé.");
    alert("VEI enregistré et réouvert. Vérifier la pastille, le texte, le trait et le point, puis renvoyer le fichier AI dans le chat.");
    dst = null;
  } catch (error) {
    if (src) { try { src.close(SaveOptions.DONOTSAVECHANGES); } catch (e1) {} }
    if (dst) { try { dst.close(SaveOptions.DONOTSAVECHANGES); } catch (e2) {} }
    alert("Extraction interrompue : " + error.message);
  } finally { app.coordinateSystem = previous; }
})();
