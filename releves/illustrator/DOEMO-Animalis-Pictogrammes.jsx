#target illustrator
/* Native, editable review placements for the supplied Animalis plan.
   Positions, sizes and orientations remain provisional; never a final export. */
(function () {
    var doc=null, source=null, owned=false, sourceSelection=null, root=null;
    var saved=false, stage="Verification du plan", coordinates=app.coordinateSystem;
    var layerName="DOEMO - PICTOGRAMMES PROVISOIRES - ANIMALIS";
    var positions=[
        [2,"r-1","ext",225.048950,961.717038],
        [6,"r-1","vei",201.788221,935.522604],
        [7,"r-1","vei",526.094377,869.000154],
        [9,"rdc","ext",498.051645,518.553769],
        [10,"rdc","ext",649.905242,540.897426],
        [11,"rdc","vei",410.829083,388.763808],
        [12,"rdc","vei",654.792247,559.129791]
    ];
    function visible(item) {
        while(item&&item.typename!=="Document") {
            if(item.typename==="Layer"&&!item.visible)return false;
            if(item.hidden)return false;
            item=item.parent;
        }
        return true;
    }
    function vector(item) {
        if(item.typename==="RasterItem"||item.typename==="PlacedItem"||item.typename==="PluginItem"||item.typename==="NonNativeItem")
            throw Error("Une ressource contient un objet lie ou non vectoriel.");
        if(item.typename==="GroupItem")for(var i=0;i<item.pageItems.length;i++)
            if(item.pageItems[i].parent===item)vector(item.pageItems[i]);
    }
    function closeSource() {
        if(!source)return;
        if(owned)source.close(SaveOptions.DONOTSAVECHANGES);
        else source.selection=sourceSelection;
        source=null;owned=false;sourceSelection=null;
    }
    function importNative(file) {
        var i,item,roots=[],sourceBounds=null,sourceAnchor=null;
        for(i=0;i<app.documents.length;i++) {
            try {if(app.documents[i].fullName.fsName===file.fsName)source=app.documents[i];}catch(ignore){}
        }
        if(source) {
            sourceSelection=source.selection;
            if(!source.saved)throw Error("Enregistrer ou fermer la ressource ouverte avant de continuer : "+file.name);
        } else {source=app.open(file);owned=true;}
        sourceSelection=source.selection;
        if(source.artboards.length!==1)throw Error("La ressource doit contenir un seul plan de travail : "+file.name);
        source.activate();
        if(file.name==="VEI.ai") {
            var art=source.artboards[0].artboardRect;
            if(Math.abs(art[2]-art[0]-41.759)>0.05||Math.abs(art[1]-art[3]-93.778801)>0.05)
                throw Error("Le format du VEI ne correspond pas au fichier fourni.");
            sourceAnchor=[art[0]+37.12679863,art[1]-4.63210296];
        }
        for(i=0;i<source.pageItems.length;i++) {
            item=source.pageItems[i];
            if(item.parent.typename==="Layer"&&visible(item)&&!(item.typename==="PathItem"&&item.guides)) {
                vector(item);roots.push(item);
                var bounds=item.geometricBounds;
                if(!sourceBounds)sourceBounds=[bounds[0],bounds[1],bounds[2],bounds[3]];
                else sourceBounds=[Math.min(sourceBounds[0],bounds[0]),Math.max(sourceBounds[1],bounds[1]),Math.max(sourceBounds[2],bounds[2]),Math.min(sourceBounds[3],bounds[3])];
            }
        }
        if(!roots.length)throw Error("Ressource vectorielle vide : "+file.name);
        source.activate();source.selection=roots;app.copy();
        doc.activate();doc.activeLayer=root;doc.selection=null;app.paste();
        var pasted=doc.selection;
        if(!pasted||!pasted.length)throw Error("Collage vide : "+file.name);
        var group=root.groupItems.add();
        for(i=pasted.length-1;i>=0;i--)pasted[i].move(group,ElementPlacement.PLACEATBEGINNING);
        vector(group);
        if(sourceAnchor) {
            var pastedBounds=group.geometricBounds;
            if(Math.abs((pastedBounds[2]-pastedBounds[0])-(sourceBounds[2]-sourceBounds[0]))>0.05||
               Math.abs((pastedBounds[1]-pastedBounds[3])-(sourceBounds[1]-sourceBounds[3]))>0.05)
                throw Error("Le collage a change les dimensions du VEI.");
            var ax=pastedBounds[0]+sourceAnchor[0]-sourceBounds[0];
            var ay=pastedBounds[1]+sourceAnchor[1]-sourceBounds[1];
            var marker=group.pathItems.rectangle(ay+0.1,ax-0.1,0.2,0.2);
            marker.name="DOEMO_VEI_ANCHOR";marker.note="DOEMO_VEI_ANCHOR";
            marker.filled=false;marker.stroked=false;marker.opacity=0;
        }
        closeSource();doc.activate();return group;
    }
    function circles(group) {
        function find(item) {
            if(item.typename==="PathItem"&&(item.name==="DOEMO_VEI_ANCHOR"||item.note==="DOEMO_VEI_ANCHOR"))return item;
            if(item.typename==="GroupItem")for(var i=0;i<item.pageItems.length;i++) {
                var marker=find(item.pageItems[i]);if(marker)return marker;
            }
            return null;
        }
        var marker=find(group);
        if(!marker)throw Error("Le repere temporaire du VEI est absent. Utiliser le script corrige complet.");
        return {tip:marker,diameter:33.61};
    }
    function place(group,row,rect) {
        var b=group.visibleBounds,w=b[2]-b[0],h=b[1]-b[3],tip=null,reference;
        if(w<=0||h<=0)throw Error("Pictogramme sans dimensions.");
        if(row[2]==="vei") {var c=circles(group);tip=c.tip;reference=c.diameter;}
        else reference=Math.max(w,h);
        var scale=(7*72/25.4)/reference*100;
        group.resize(scale,scale,true,true,true,true,scale,Transformation.CENTER);
        b=tip?tip.geometricBounds:group.visibleBounds;
        group.translate(rect[0]+row[3]-(b[0]+b[2])/2,rect[1]-row[4]-(b[1]+b[3])/2);
        if(tip)tip.remove();
        group.name=row[0]+" - "+(tip?"Vous etes ici":"Extincteur portatif")+" - A CONTROLER";
        group.note="DOEMO Animalis / position "+row[0]+" / PROVISOIRE NON VALIDE / taille 7 mm "+(tip?"diametre pastille; ancrage petit point":"cote")+" / orientation originale";
    }
    try {
        if(parseInt(app.version,10)<28)throw Error("Illustrator 2024 ou plus recent requis.");
        if(!app.documents.length)throw Error("Ouvrir PLANTEST.ai avec le releve en arriere-plan.");
        doc=app.activeDocument;
        if(doc.artboards.length!==1)throw Error("Un seul plan de travail attendu.");
        app.coordinateSystem=CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        var rect=doc.artboards[0].artboardRect;
        if(Math.abs(rect[2]-rect[0]-841.891)>0.2||Math.abs(rect[1]-rect[3]-1190.550)>0.2)
            throw Error("Les dimensions ne correspondent pas au plan Animalis.");
        var background=false;
        for(var i=0;i<doc.layers.length;i++) {
            if(doc.layers[i].name===layerName)throw Error("Les pictogrammes provisoires existent deja. Aucun doublon ajoute.");
            if(doc.layers[i].name==="DOEMO - RELEVE DE CONTROLE - NON VALIDE")background=true;
        }
        if(!background)throw Error("Ouvrir PLANTEST.ai, la copie contenant le releve.");
        var home=File($.fileName).parent;
        var ext=File(home.fsName+"/Extincteur-Portatif.ai"),vei=File(home.fsName+"/VEI.ai");
        if(!ext.exists||!vei.exists)throw Error("Les deux ressources AI doivent rester a cote du JSX.");
        var output=File.saveDialog("Enregistrer une NOUVELLE copie AI avec les 7 pictogrammes provisoires","*.ai");
        if(!output)return;
        if(output.name.slice(-3).toLowerCase()!==".ai")output=File(output.fsName+".ai");
        if(output.exists)throw Error("Choisir un nouveau nom : aucun fichier ne sera ecrase.");
        root=doc.layers.add();root.name=layerName;root.zOrder(ZOrderMethod.BRINGTOFRONT);
        stage="Import de l'extincteur portatif";var extTemplate=importNative(ext);
        stage="Import du VEI";var veiTemplate=importNative(vei);
        var floors={};floors.rdc=root.layers.add();floors.rdc.name="Niveau 0";
        floors["r-1"]=root.layers.add();floors["r-1"].name="Niveau -1";
        for(i=0;i<positions.length;i++) {
            var row=positions[i];stage="Pose du pictogramme "+row[0];
            var group=(row[2]==="ext"?extTemplate:veiTemplate).duplicate(floors[row[1]],ElementPlacement.PLACEATEND);
            place(group,row,rect);
        }
        extTemplate.remove();veiTemplate.remove();doc.selection=null;
        stage="Enregistrement de la copie AI";
        var options=new IllustratorSaveOptions();options.pdfCompatible=true;options.compressed=true;
        doc.saveAs(output,options);saved=true;app.redraw();
        alert("Copie AI enregistree : 3 extincteurs et 4 VEI vectoriels.\nCalque : PICTOGRAMMES PROVISOIRES.\nPositions 1, 3, 4 et 8 encore a preciser.\nVerifier les positions, tailles et orientations avant validation.");
    } catch(e) {
        if(root&&!saved) {try{root.locked=false;root.remove();}catch(ignoreRoot){}}
        alert("DOEMO - Etape : "+stage+"\n"+e.message+"\nAucun fichier existant n'a ete ecrase.");
    } finally {
        try{closeSource();}catch(ignoreSource){}
        if(doc){try{doc.activate();}catch(ignoreDoc){}}
        app.coordinateSystem=coordinates;
    }
}());
