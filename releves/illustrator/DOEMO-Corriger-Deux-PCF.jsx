#target illustrator
/* Replaces only the two identified PCF groups, using a verified vector PDF.
   No clipboard operations, no reconstruction of the other pictograms. */
(function () {
    var doc=null,source=null,newGroups=[],oldGroups=[],replaced=false;
    var stage="Recherche des deux PCF",coordinates=app.coordinateSystem;
    var oldPdfPage=null;
    function inComplements(item) {
        while(item&&item.typename!=="Document") {
            if(item.typename==="Layer"&&item.name==="DOEMO - COMPLEMENTS PROVISOIRES - ANIMALIS")return true;
            item=item.parent;
        }
        return false;
    }
    function unlocked(item) {
        while(item&&item.typename!=="Document") {
            if(item.locked||item.hidden||(item.typename==="Layer"&&!item.visible))return false;
            item=item.parent;
        }
        return true;
    }
    function vector(item) {
        if(item.typename==="RasterItem"||item.typename==="PlacedItem"||item.typename==="PluginItem"||item.typename==="NonNativeItem")
            throw Error("Le modele PCF contient un objet non vectoriel.");
        if(item.typename==="GroupItem")for(var i=0;i<item.pageItems.length;i++)vector(item.pageItems[i]);
    }
    try {
        if(!app.documents.length)throw Error("Ouvrir plansv2.ai dans Illustrator.");
        doc=app.activeDocument;
        app.coordinateSystem=CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        var found={},i,item,match;
        for(i=0;i<doc.groupItems.length;i++) {
            item=doc.groupItems[i];match=/^(13|14) - /.exec(item.name);
            if(match&&inComplements(item)) {
                if(found[match[1]])throw Error("Plusieurs objets portent le meme numero PCF.");
                if((item.note||"").indexOf("DOEMO-PCF-CORRIGE")>=0)throw Error("Cette copie contient deja les PCF corrigees.");
                if(!unlocked(item))throw Error("Deverrouiller et afficher le calque des complements.");
                found[match[1]]=item;
            }
        }
        if(!found[13]||!found[14])throw Error("Les objets PCF 13 et 14 sont introuvables. Ouvrir plansv2.ai.");
        oldGroups=[found[13],found[14]];
        var file=File(File($.fileName).parent.fsName+"/PCF-verifie.pdf");
        if(!file.exists)throw Error("Laisser PCF-verifie.pdf a cote de ce JSX.");
        var output=File.saveDialog("Enregistrer une NOUVELLE copie AI avec les deux PCF corrigees","*.ai");
        if(!output)return;
        if(output.name.slice(-3).toLowerCase()!==".ai")output=File(output.fsName+".ai");
        if(output.exists)throw Error("Choisir un nouveau nom pour conserver le fichier precedent.");

        stage="Ouverture du modele PCF vectoriel";
        oldPdfPage=app.preferences.PDFFileOptions.pageToOpen;
        app.preferences.PDFFileOptions.pageToOpen=1;
        source=app.open(file);
        if(source.artboards.length!==1||source.rasterItems.length||source.placedItems.length)
            throw Error("Le modele doit contenir une seule page, entierement vectorielle.");
        var roots=[];
        for(i=0;i<source.pageItems.length;i++) {
            item=source.pageItems[i];
            if(item.parent.typename==="Layer"&&unlocked(item)) {vector(item);roots.push(item);}
        }
        if(!roots.length)throw Error("Le modele PCF est vide.");
        doc.activate();
        for(i=0;i<oldGroups.length;i++) {
            stage="Remplacement de la PCF "+(i===0?13:14);
            var old=oldGroups[i],b=old.visibleBounds;
            var x=(b[0]+b[2])/2,y=(b[1]+b[3])/2,size=Math.max(b[2]-b[0],b[1]-b[3]);
            if(size<15||size>25)throw Error("Dimensions inattendues du symbole a remplacer.");
            var group=old.parent.groupItems.add();newGroups.push(group);
            // Direct native duplication: the clipboard cannot supply another symbol.
            for(var j=roots.length-1;j>=0;j--)roots[j].duplicate(group,ElementPlacement.PLACEATBEGINNING);
            vector(group);b=group.visibleBounds;
            var reference=Math.max(b[2]-b[0],b[1]-b[3]);
            if(reference<=0)throw Error("La copie du modele PCF est vide.");
            var scale=size/reference*100;
            group.resize(scale,scale,true,true,true,true,scale,Transformation.CENTER);
            b=group.visibleBounds;group.translate(x-(b[0]+b[2])/2,y-(b[1]+b[3])/2);
            group.name=(i===0?13:14)+" - Porte coupe-feu - A CONTROLER";
            group.note=(old.note||"")+" / DOEMO-PCF-CORRIGE / modele vectoriel SAI porte et flamme";
        }
        source.close(SaveOptions.DONOTSAVECHANGES);source=null;doc.activate();
        stage="Retrait des deux symboles incorrects";
        replaced=true;
        for(i=0;i<oldGroups.length;i++)oldGroups[i].remove();
        stage="Enregistrement de la copie AI";
        var options=new IllustratorSaveOptions();options.pdfCompatible=true;options.compressed=true;
        doc.saveAs(output,options);app.redraw();
        alert("Les deux PCF sont remplacees par le symbole porte et flamme. Copie AI enregistree. Verifier visuellement les deux portes.");
    } catch(e) {
        if(!replaced)for(var k=newGroups.length-1;k>=0;k--){try{newGroups[k].remove();}catch(ignoreGroup){}}
        alert("DOEMO - Etape : "+stage+"\n"+e.message+(replaced?"\nLes corrections restent ouvertes. Verifier puis enregistrer sous un nouveau nom.":"\nLes pictogrammes existants sont conserves."));
    } finally {
        if(source){try{source.close(SaveOptions.DONOTSAVECHANGES);}catch(ignoreSource){}}
        if(oldPdfPage!==null){try{app.preferences.PDFFileOptions.pageToOpen=oldPdfPage;}catch(ignorePdf){}}
        if(doc){try{doc.activate();}catch(ignoreDoc){}}
        app.coordinateSystem=coordinates;
    }
}());
