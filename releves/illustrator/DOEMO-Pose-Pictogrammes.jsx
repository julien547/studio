#target illustrator
/* Illustrator 2024+ (28+). Uses native Illustrator import and saveAs only.
   Original files are never overwritten. Run on the licensed designer workstation. */
(function () {
    var home = File($.fileName).parent;
    $.evalFile(File(home.fsName + "/doemo-core.js"));
    var doc = null, assetDoc = null, previousCoordinates = app.coordinateSystem;
    var PREFIX = "DOEMO-PLACEMENT:", META = "DOEMO-META:", rootName, rootLayer;
    function read(file, binary) {
        file.encoding = binary ? "BINARY" : "UTF-8";
        if (!file.open("r")) throw new Error("Impossible de lire " + file.name);
        var bytes = file.read(); file.close(); return bytes;
    }
    function write(file, content) {
        if (file.exists) throw new Error("Le rapport existe déjà : " + file.name);
        file.encoding = "UTF-8"; if (!file.open("w")) throw new Error("Rapport non enregistrable");
        file.write(content); file.close();
    }
    function round(n) { return Math.round(n * 1000000) / 1000000; }
    function color(c) {
        if (!c) return null;
        var t=c.typename;
        if(t==="RGBColor")return[t,round(c.red),round(c.green),round(c.blue)];
        if(t==="CMYKColor")return[t,round(c.cyan),round(c.magenta),round(c.yellow),round(c.black)];
        if(t==="GrayColor")return[t,round(c.gray)];
        if(t==="SpotColor")return[t,c.spot.name,round(c.tint),color(c.spot.color)];
        if(t==="LabColor")return[t,round(c.l),round(c.a),round(c.b)];
        if(t==="GradientColor"||t==="PatternColor")return[t,t==="GradientColor"?c.gradient.name:c.pattern.name];
        return[t];
    }
    function itemData(item) {
        var out={type:item.typename,bounds:[],hidden:item.hidden,opacity:round(item.opacity)},i,p;
        var bounds=item.geometricBounds;for(i=0;i<4;i++)out.bounds.push(round(bounds[i]));
        if(item.typename==="GroupItem"){out.items=[];out.clipped=item.clipped;for(i=0;i<item.pageItems.length;i++)if(item.pageItems[i].parent===item)out.items.push(itemData(item.pageItems[i]));}
        else if(item.typename==="CompoundPathItem"){out.paths=[];for(i=0;i<item.pathItems.length;i++)out.paths.push(itemData(item.pathItems[i]));}
        else if(item.typename==="PathItem"){
            out.closed=item.closed;out.filled=item.filled;out.stroked=item.stroked;
            out.fill=item.filled?color(item.fillColor):null;out.stroke=item.stroked?color(item.strokeColor):null;
            out.width=round(item.strokeWidth);out.points=[];
            for(i=0;i<item.pathPoints.length;i++){p=item.pathPoints[i];out.points.push([round(p.anchor[0]),round(p.anchor[1]),round(p.leftDirection[0]),round(p.leftDirection[1]),round(p.rightDirection[0]),round(p.rightDirection[1])]);}
        } else if(item.typename==="TextFrame") {out.text=item.contents;out.matrix=[item.matrix.mValueA,item.matrix.mValueB,item.matrix.mValueC,item.matrix.mValueD,item.matrix.mValueTX,item.matrix.mValueTY];}
        else if(item.typename==="SymbolItem")out.symbol=item.symbol.name;
        return out;
    }
    function fingerprint(item){return DOEMO.sha256(DOEMO.utf8(DOEMO.stringify(itemData(item))));}
    function architecture(document) {
        var result=[];
        function layerData(layer){var out={name:layer.name,visible:layer.visible,items:[],layers:[]},i;for(i=0;i<layer.pageItems.length;i++)if(layer.pageItems[i].parent===layer)out.items.push(itemData(layer.pageItems[i]));for(i=0;i<layer.layers.length;i++)out.layers.push(layerData(layer.layers[i]));return out;}
        for(var i=0;i<document.layers.length;i++)if(document.layers[i].name!==rootName)result.push(layerData(document.layers[i]));
        return DOEMO.sha256(DOEMO.utf8(DOEMO.stringify(result)));
    }
    function groupLayer(parent,name){for(var i=0;i<parent.layers.length;i++)if(parent.layers[i].name===name)return parent.layers[i];var layer=parent.layers.add();layer.name=name;return layer;}
    function visibleLayer(layer){while(layer&&layer.typename==="Layer"){if(!layer.visible)return false;layer=layer.parent;}return true;}
    function ensureVector(item){if(item.typename==="RasterItem"||item.typename==="PlacedItem"||item.typename==="PluginItem"||item.typename==="NonNativeItem")throw new Error("La ressource comporte un objet raster, lié ou non natif : import refusé.");if(item.typename==="GroupItem")for(var i=0;i<item.pageItems.length;i++)if(item.pageItems[i].parent===item)ensureVector(item.pageItems[i]);}
    function importGroup(assetFile,layer) {
        assetDoc=app.open(assetFile);
        if(assetDoc.artboards.length!==1)throw new Error("La ressource SAI doit contenir un seul plan de travail.");
        var roots=[],i,item;
        for(i=0;i<assetDoc.pageItems.length;i++){item=assetDoc.pageItems[i];if(item.parent.typename==="Layer"&&!item.hidden&&visibleLayer(item.parent)&&!(item.typename==="PathItem"&&item.guides)){ensureVector(item);roots.push(item);}}
        if(!roots.length)throw new Error("Ressource SAI sans contenu vectoriel visible.");
        var group=layer.groupItems.add();
        // Reverse traversal preserves Illustrator's front-to-back stacking order.
        for(i=roots.length-1;i>=0;i--)roots[i].duplicate(group,ElementPlacement.PLACEATBEGINNING);
        assetDoc.close(SaveOptions.DONOTSAVECHANGES);assetDoc=null;doc.activate();return group;
    }
    function place(group,p,floor) {
        // Reset by importing the original resource for each accepted update; no cumulative scale/rotation.
        var bounds=group.visibleBounds,w=bounds[2]-bounds[0],h=bounds[1]-bounds[3];
        if(w<=0||h<=0)throw new Error("Dimensions de pictogramme nulles.");
        var scale=p.size_mm*72/25.4/Math.max(w,h)*100;
        group.resize(scale,scale,true,true,true,true,scale,Transformation.CENTER);
        group.rotate(-p.rotation_deg,true,true,true,true,Transformation.CENTER);
        bounds=group.visibleBounds;
        var position=DOEMO.point(doc.artboards[floor.artboard_index].artboardRect,p.x,p.y);
        group.translate(position[0]-(bounds[0]+bounds[2])/2,position[1]-(bounds[1]+bounds[3])/2);
        group.name=p.equipment_type+" · "+p.placement_id;
    }
    try {
        if(parseInt(app.version,10)<28)throw new Error("Illustrator 2024 ou version ultérieure requis.");
        var jsonFile=File.openDialog("Choisir placements.json validé par DOEMO Studio","*.json");if(!jsonFile)return;
        if(jsonFile.length>16*1024*1024)throw new Error("JSON trop volumineux.");
        var data=DOEMO.parse(read(jsonFile,false)),index=DOEMO.validate(data);
        var bat=File.openDialog("Choisir le BAT .ai d’origine ou une sortie DOEMO précédente","*.ai");if(!bat)return;
        var assetRoot=Folder.selectDialog("Choisir le dossier library contenant les sous-dossiers UUID SAI");if(!assetRoot)return;
        var output=File.saveDialog("Enregistrer une NOUVELLE copie Illustrator","*.ai");if(!output)return;
        if(!/\.ai$/i.test(output.name))output=File(output.fsName+".ai");
        if(output.exists||output.fsName===bat.fsName)throw new Error("Choisir un nouveau nom : aucun fichier ne sera écrasé.");
        var reportFile=File(output.fsName+".placements.json");if(reportFile.exists)throw new Error("Le rapport associé existe déjà.");
        var i,key,file,files={},currentOpen;
        for(key in index.assets)if(Object.prototype.hasOwnProperty.call(index.assets,key)){
            file=File(assetRoot.fsName+"/"+DOEMO.safePath(index.assets[key].relative_path));
            if(!file.exists||file.alias||DOEMO.sha256(read(file,true))!==index.assets[key].sha256)throw new Error("Ressource SAI absente ou empreinte différente : "+index.assets[key].name);
            files[key]=file;
        }
        // Never operate on another document's unsaved work, including an already open asset.
        for(i=0;i<app.documents.length;i++){
            currentOpen=app.documents[i];
            try{var openPath=currentOpen.fullName.fsName;if(openPath===bat.fsName)throw new Error("Fermer le BAT dans Illustrator avant d’exécuter le script ; son travail ouvert ne sera pas modifié.");for(key in files)if(Object.prototype.hasOwnProperty.call(files,key)&&files[key].fsName===openPath)throw new Error("Fermer les ressources SAI ouvertes avant l’import.");}
            catch(openError){if(String(openError).indexOf("Fermer")>=0)throw openError;}
        }
        var inputHash=DOEMO.sha256(read(bat,true));
        app.coordinateSystem=CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        doc=app.open(bat);rootName="DOEMO — PICTOGRAMMES ["+data.project_id+"]";
        var metadata=null,metadataItem=null,existing={},items={},before,layer,j,note;
        for(i=0;i<doc.layers.length;i++)if(doc.layers[i].name===rootName)rootLayer=doc.layers[i];
        if(rootLayer){
            if(rootLayer.locked||!rootLayer.visible)throw new Error("Le calque DOEMO est masqué ou verrouillé : le rendre disponible avant la reprise.");
            for(i=0;i<doc.pageItems.length;i++){
                var item=doc.pageItems[i];note=item.note||"";
                if(note.indexOf(META)===0){var candidate=DOEMO.parse(note.substring(META.length));if(candidate.project_id===data.project_id){metadata=candidate;metadataItem=item;}}
                if(note.indexOf(PREFIX)===0){var saved=DOEMO.parse(note.substring(PREFIX.length));if(saved.project_id===data.project_id){if(items[saved.placement_id])throw new Error("Identifiants de placement dupliqués dans le BAT.");items[saved.placement_id]=item;existing[saved.placement_id]={signature:saved.signature,manually_changed:fingerprint(item)!==saved.fingerprint};}}
            }
            if(!metadata)throw new Error("Un calque du même nom existe sans métadonnées DOEMO : arrêt sans modification.");
        }
        before=architecture(doc);
        if(inputHash!==data.target.sha256&&(!metadata||metadata.original_sha256!==data.target.sha256||metadata.architecture!==before))throw new Error("BAT différent de la référence ou architecture modifiée : refaire la validation web.");
        for(key in index.floors)if(Object.prototype.hasOwnProperty.call(index.floors,key)){
            var floor=index.floors[key];if(floor.artboard_index>=doc.artboards.length)throw new Error("Plan de travail du niveau absent.");
            var rect=doc.artboards[floor.artboard_index].artboardRect,dims=data.target.pages[floor.target_page-1].pdf_size_pt;
            if(Math.abs(rect[2]-rect[0]-dims[0])>.1||Math.abs(rect[1]-rect[3]-dims[1])>.1)throw new Error("Dimensions du plan de travail différentes de l’aperçu BAT.");
        }
        var changes=DOEMO.diff(data.placements,existing),counts={add:0,update:0,unchanged:0,conflict:0,removed_preserve:0};
        for(i=0;i<changes.length;i++)counts[changes[i].action]++;
        if(!confirm("Comparaison avant application\nAjouts : "+counts.add+"\nMises à jour : "+counts.update+"\nInchangés : "+counts.unchanged+"\nModifiés manuellement : "+counts.conflict+"\nAbsents du nouveau relevé, conservés : "+counts.removed_preserve+"\n\nLes pictogrammes existants sans identifiant DOEMO sont conservés. Vérifier les doublons métier.\nAccepter les ajouts et mises à jour proposés ?")){doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;return;}
        rootLayer=rootLayer||doc.layers.add();rootLayer.name=rootName;
        var report={schema_version:"doemo.placement-report/1",project_id:data.project_id,revision:data.revision,input_sha256:inputHash,original_sha256:data.target.sha256,output_name:output.name,counts:counts,items:[],measurements:[],recognition_report:data.report,native_ai_verified:false,architecture_unchanged:false,conformity_passed:false};
        for(i=0;i<changes.length;i++){
            var change=changes[i],p=change.placement;
            if(change.action==="removed_preserve"||change.action==="unchanged"){report.items.push({placement_id:change.id,action:change.action});continue;}
            if(change.action==="conflict"&&!confirm("Le pictogramme "+change.id+" a été modifié manuellement.\nRemplacer explicitement cette version par le placement validé ?")){report.items.push({placement_id:change.id,action:"manual_edit_preserved"});continue;}
            layer=groupLayer(rootLayer,index.floors[p.floor_id].name+" ["+p.floor_id+"]");
            if(layer.locked||!layer.visible)throw new Error("Sous-calque de niveau verrouillé ou masqué.");
            var group=importGroup(files[p.asset_id],layer);place(group,p,index.floors[p.floor_id]);
            group.note=PREFIX+DOEMO.stringify({project_id:data.project_id,placement_id:p.placement_id,source_document_id:p.source_document_id,source_page:p.source_page,annotation_source:p.annotation_source,asset_id:p.asset_id,original_sha256:data.target.sha256,signature:DOEMO.signature(p),fingerprint:fingerprint(group)});
            if(items[p.placement_id])items[p.placement_id].remove();
            items[p.placement_id]=group;
            report.items.push({placement_id:p.placement_id,source_document_id:p.source_document_id,source_page:p.source_page,action:change.action==="add"?"added":"updated",asset_id:p.asset_id,x:p.x,y:p.y,floor_id:p.floor_id});
        }
        if(architecture(doc)!==before)throw new Error("La géométrie ou les propriétés contrôlées de l’architecture ont changé : sauvegarde refusée.");
        report.architecture_unchanged=true;
        metadataItem=metadataItem||rootLayer.groupItems.add();metadataItem.locked=false;metadataItem.hidden=false;
        metadataItem.name="DOEMO — traçabilité (sans dessin)";metadataItem.note=META+DOEMO.stringify({project_id:data.project_id,original_sha256:data.target.sha256,architecture:before});metadataItem.hidden=true;metadataItem.locked=true;
        var options=new IllustratorSaveOptions();options.pdfCompatible=true;options.compressed=true;
        doc.saveAs(output,options);doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;
        // Reopen natively and verify object identities and architecture before reporting success.
        doc=app.open(output);
        var placed=0,found={};
        for(i=0;i<doc.pageItems.length;i++){note=doc.pageItems[i].note||"";if(note.indexOf(PREFIX)===0){var record=DOEMO.parse(note.substring(PREFIX.length));if(record.project_id===data.project_id){if(found[record.placement_id])throw new Error("Doublon après réouverture.");found[record.placement_id]=doc.pageItems[i];placed++;}}}
        for(i=0;i<data.placements.length;i++)if(!found[data.placements[i].placement_id])throw new Error("Placement absent après réouverture native.");
        if(architecture(doc)!==before)throw new Error("Contrôle architectural après réouverture en échec.");
        var conforms=counts.removed_preserve===0;
        for(i=0;i<data.placements.length;i++){
            var expected=data.placements[i],actual=found[expected.placement_id],currentNote=DOEMO.parse(actual.note.substring(PREFIX.length));
            var box=actual.visibleBounds,center=[(box[0]+box[2])/2,(box[1]+box[3])/2],wanted=DOEMO.point(doc.artboards[index.floors[expected.floor_id].artboard_index].artboardRect,expected.x,expected.y);
            var distance=Math.sqrt(Math.pow(center[0]-wanted[0],2)+Math.pow(center[1]-wanted[1],2));
            var matches=distance<=.05&&currentNote.signature===DOEMO.signature(expected)&&currentNote.fingerprint===fingerprint(actual);
            if(!matches)conforms=false;
            report.measurements.push({placement_id:expected.placement_id,position_error_pt:distance,expected_document_center:wanted,actual_document_center:center,validated_placement_matches:matches});
        }
        report.conformity_passed=conforms;
        report.placed_total=placed;report.native_ai_verified=true;report.output_sha256=DOEMO.sha256(read(output,true));
        write(reportFile,DOEMO.stringify(report));
        alert("Copie AI enregistrée et réouverte dans Illustrator.\n"+placed+" objets DOEMO présents.\nLes modifications manuelles refusées et les placements absents du nouveau relevé sont conservés dans le rapport.\nContrôler visuellement la fidélité et les positions avant livraison.");
        doc=null; // Leave the verified output open for the designer.
    } catch(error) {
        if(assetDoc){try{assetDoc.close(SaveOptions.DONOTSAVECHANGES);}catch(ignoreAsset){}}
        if(doc){try{doc.close(SaveOptions.DONOTSAVECHANGES);}catch(ignoreDoc){}}
        alert("DOEMO — traitement interrompu\n"+error.message+"\nAucun fichier source n’a été écrasé. Une éventuelle copie de sortie ne doit pas être livrée sans rapport de contrôle réussi.");
    } finally {app.coordinateSystem=previousCoordinates;}
}());
