#target illustrator
/* Extract the original VEI objects from the supplied four-artboard legend.
   Illustrator 2024+. Source is opened read-only and never saved. */
(function () {
    var folder=File($.fileName).parent, source=null, output=null;
    var previousCoordinates=app.coordinateSystem;
    function read(file,binary){file.encoding=binary?"BINARY":"UTF-8";if(!file.open("r"))throw new Error("Fichier illisible : "+file.name);var text=file.read();file.close();return text;}
    function write(file,text){file.encoding="UTF-8";if(!file.open("w"))throw new Error("Rapport non enregistrable.");file.write(text);file.close();}
    function visible(item){var p=item;while(p&&p.typename!=="Document"){if(p.typename==="Layer"&&!p.visible)return false;if(p.hidden)return false;p=p.parent;}return true;}
    function vector(item){var t=item.typename,i;if(t==="RasterItem"||t==="PlacedItem"||t==="PluginItem"||t==="NonNativeItem")throw new Error("Un objet image, lié ou non natif se trouve dans le VEI : arrêt.");if(t==="GroupItem")for(i=0;i<item.pageItems.length;i++)if(item.pageItems[i].parent===item)vector(item.pageItems[i]);}
    function within(b,r){return b[0]>=r[0]&&b[1]<=r[1]&&b[2]<=r[2]&&b[3]>=r[3];}
    function intersects(b,r){return b[2]>r[0]&&b[0]<r[2]&&b[1]>r[3]&&b[3]<r[1];}
    var roots=[],region;
    function collect(item){
        if(!visible(item)||(item.typename==="PathItem"&&item.guides))return;
        var b=item.visibleBounds,i;
        if(!intersects(b,region))return;
        if(within(b,region)){vector(item);roots.push(item);return;}
        if(item.typename!=="GroupItem"||item.clipped||item.opacity!==100||item.blendingMode!==BlendModes.NORMAL)
            throw new Error("Un objet ou effet traverse la zone VEI. Aucun découpage destructif n’est appliqué.");
        for(i=0;i<item.pageItems.length;i++)if(item.pageItems[i].parent===item)collect(item.pageItems[i]);
    }
    function collectLayer(layer){var i;for(i=0;i<layer.pageItems.length;i++)if(layer.pageItems[i].parent===layer)collect(layer.pageItems[i]);for(i=0;i<layer.layers.length;i++)collectLayer(layer.layers[i]);}
    try {
        if(parseInt(app.version,10)<28)throw new Error("Illustrator 2024 ou plus récent requis.");
        var core=File(folder.fsName+"/doemo-core.js");
        if(!core.exists)throw new Error("Décompresser toute l’archive ZIP avant de lancer le script.");
        $.evalFile(core);
        var manifest=DOEMO.parse(read(File(folder.fsName+"/selection-VEI.json"),false));
        var sourceFile=File(folder.fsName+"/"+DOEMO.safePath(manifest.source_file));
        if(!sourceFile.exists||DOEMO.sha256(read(sourceFile,true))!==manifest.source_sha256)
            throw new Error("Le fichier source ne correspond pas à la légende fournie.");
        for(var i=0;i<app.documents.length;i++){
            var opened=null;try{opened=app.documents[i].fullName.fsName;}catch(ignored){}
            if(opened===sourceFile.fsName)throw new Error("Fermer source-VEI.ai avant de lancer le script. Aucun travail ouvert ne sera modifié.");
        }
        var destination=File.saveDialog("Enregistrer le symbole isolé sous VEI-DOEMO.ai","*.ai");
        if(!destination)return;
        if(!/\.ai$/i.test(destination.name))destination=File(destination.fsName+".ai");
        var reportFile=File(destination.fsName+".extraction.json");
        if(destination.exists||reportFile.exists)throw new Error("Choisir un nouveau nom : aucun fichier existant ne sera écrasé.");
        app.coordinateSystem=CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        source=app.open(sourceFile);
        if(source.artboards.length!==manifest.source_artboard_count)throw new Error("Nombre de plans de travail inattendu.");
        var rect=source.artboards[manifest.source_artboard_index].artboardRect;
        var w=rect[2]-rect[0],h=rect[1]-rect[3],b=manifest.selection_box_normalized;
        if(Math.abs(w-manifest.source_page_size_pt[0])>.1||Math.abs(h-manifest.source_page_size_pt[1])>.1)
            throw new Error("Dimensions de la première planche différentes de l’aperçu contrôlé.");
        region=[rect[0]+b.x*w,rect[1]-b.y*h,rect[0]+(b.x+b.w)*w,rect[1]-(b.y+b.h)*h];
        for(i=0;i<source.layers.length;i++)collectLayer(source.layers[i]);
        if(!roots.length||roots.length>100)throw new Error("Sélection VEI vide ou trop étendue : extraction interrompue.");
        output=app.documents.add(source.documentColorSpace,200,200);
        var group=output.activeLayer.groupItems.add();group.name="DOEMO — Vous êtes ici";
        for(i=roots.length-1;i>=0;i--)roots[i].duplicate(group,ElementPlacement.PLACEATBEGINNING);
        var bounds=group.visibleBounds,expectedWidth=bounds[2]-bounds[0],expectedHeight=bounds[1]-bounds[3];
        if(expectedWidth<=0||expectedHeight<=0)throw new Error("Dimensions du VEI invalides.");
        var count=group.pageItems.length;
        group.note="DOEMO-VEI-SOURCE:"+manifest.source_sha256;
        output.artboards[0].artboardRect=[bounds[0]-2,bounds[1]+2,bounds[2]+2,bounds[3]-2];
        source.close(SaveOptions.DONOTSAVECHANGES);source=null;
        var options=new IllustratorSaveOptions();options.pdfCompatible=true;options.compressed=true;
        output.saveAs(destination,options);output.close(SaveOptions.DONOTSAVECHANGES);output=null;
        output=app.open(destination);
        var found=null;for(i=0;i<output.groupItems.length;i++)if(output.groupItems[i].note==="DOEMO-VEI-SOURCE:"+manifest.source_sha256)found=output.groupItems[i];
        if(!found||output.artboards.length!==1||found.pageItems.length!==count)throw new Error("Contrôle de réouverture en échec : résultat à examiner, non validé.");
        vector(found);bounds=found.visibleBounds;
        if(Math.abs(bounds[2]-bounds[0]-expectedWidth)>.05||Math.abs(bounds[1]-bounds[3]-expectedHeight)>.05)
            throw new Error("Dimensions modifiées après sauvegarde : résultat non validé.");
        if(DOEMO.sha256(read(sourceFile,true))!==manifest.source_sha256)throw new Error("Empreinte de la source modifiée.");
        write(reportFile,DOEMO.stringify({schema_version:"doemo.native-asset-extraction/1",name:manifest.name,
            source_sha256:manifest.source_sha256,source_selection:manifest.selection_box_normalized,
            output_sha256:DOEMO.sha256(read(destination,true)),output_name:destination.name,
            native_ai_reopened:true,source_unchanged:true,root_object_count:roots.length,
            group_item_count:count,width_pt:expectedWidth,height_pt:expectedHeight,
            visual_review_required:true,placement_on_plan_performed:false}));
        alert("VEI extrait dans un fichier Illustrator natif et réouvert.\nVérifier visuellement la pastille, le texte, le trait et le point.\nRenvoyer le fichier .ai et son rapport .extraction.json.\nAucun pictogramme n’a été posé sur le plan.");
        output=null; // Leave the resulting document open for the designer's review.
    } catch(error) {
        if(source){try{source.close(SaveOptions.DONOTSAVECHANGES);}catch(ignoredSource){}}
        if(output){try{output.close(SaveOptions.DONOTSAVECHANGES);}catch(ignoredOutput){}}
        alert("Extraction VEI interrompue : "+error.message);
    } finally {app.coordinateSystem=previousCoordinates;}
})();
