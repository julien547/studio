#target illustrator
/* Save a NEW native AI, reopen and compare vector content. Never overwrite input. */
(function(){
    var home=File($.fileName).parent,previous=app.coordinateSystem,doc=null;
    $.evalFile(File(home+'/doemo-core.js'));$.evalFile(File(home+'/circulations-core.js'));$.evalFile(File(home+'/circulations-native.js'));
    function ring(parent,points,positive){var p=parent.pathItems.add();p.setEntirePath(DOEMO_CIRC.oriented(points,positive));p.closed=true;p.stroked=false;p.filled=true;p.evenodd=true;return p;}
    function paint(c){var v;if(c.mode==='SPOT'){v=new SpotColor();v.spot=doc.spots.getByName(c.swatch);v.tint=c.tint;return v;}
        if(c.mode==='RGB'){v=new RGBColor();v.red=c.values[0];v.green=c.values[1];v.blue=c.values[2];}else{v=new CMYKColor();v.cyan=c.values[0];v.magenta=c.values[1];v.yellow=c.values[2];v.black=c.values[3];}return v;}
    function fingerprint(o){var v=DOEMO_CIRC_NATIVE.item(o);v.note='';return DOEMO_CIRC_NATIVE.hash(v);}
    function opaqueWhite(o){var c=o.fill;if(!o.filled||o.opacity<99||!c)return false;if(c[0]==='RGBColor')return c[1]>254&&c[2]>254&&c[3]>254;if(c[0]==='CMYKColor')return c[1]<.01&&c[2]<.01&&c[3]<.01&&c[4]<.01;return false;}
    function checkBackground(o,regions){if(opaqueWhite(o)){for(var i=0;i<regions.length;i++){var pts=regions[i].shape.shell,inside=true,b=o.bounds;for(var j=0;j<pts.length;j++)if(pts[j][0]<b[0]||pts[j][0]>b[2]||pts[j][1]>b[1]||pts[j][1]<b[3])inside=false;if(inside)throw Error('Fond blanc susceptible de masquer le vert. Isoler ce fond dans un calque inférieur DOEMO:FOND dans la copie de préparation, puis refaire l’extraction.');}}for(var k=0;k<o.children.length;k++)checkBackground(o.children[k],regions);}
    function checkLayer(l,regions){for(var i=0;i<l.items.length;i++)checkBackground(l.items[i],regions);for(i=0;i<l.layers.length;i++)checkLayer(l.layers[i],regions);}
    try{
        if(parseInt(app.version,10)<28)throw Error('Illustrator 2024 ou plus récent requis');
        var jsonFile=File.openDialog('Choisir le résultat de circulations validé dans DOEMO','*.json');if(!jsonFile)return;
        if(jsonFile.length>32*1024*1024)throw Error('Résultat trop volumineux');
        var data=DOEMO_CIRC.validate(DOEMO.parse(DOEMO_CIRC_NATIVE.read(jsonFile,false)));
        var source=File.openDialog('Choisir le fichier AI ayant servi à cette extraction','*.ai');if(!source)return;
        if(DOEMO.sha256(DOEMO_CIRC_NATIVE.read(source,true))!==data.source_sha256)throw Error('Le fichier source a changé : refaire l’extraction et la revue');
        for(var n=0;n<app.documents.length;n++)if(app.documents[n].fullName.fsName===source.fsName)throw Error('Fermer ce document avant import pour préserver toute modification en cours');
        var output=File.saveDialog('Nouvelle copie NOM_CIRCULATIONS_VERT.ai','*.ai');if(!output)return;
        if(!/\.ai$/i.test(output.name))output=File(output.fsName+'.ai');
        if(output.exists||output.fsName===source.fsName)throw Error('Choisir un nouveau nom : aucun fichier existant ne sera remplacé');
        var report=File(output.fsName+'.circulations.json');if(report.exists)throw Error('Rapport déjà existant');
        app.coordinateSystem=CoordinateSystem.DOCUMENTCOORDINATESYSTEM;doc=app.open(source);DOEMO_CIRC_NATIVE.preflight(doc);
        var before=DOEMO_CIRC_NATIVE.inventory(doc);
        if(DOEMO_CIRC_NATIVE.hash(before)!==data.architecture_sha256||DOEMO.stringify(before.artboards)!==DOEMO.stringify(data.artboards)||before.color_space!==data.color_space)throw Error('Inventaire Illustrator incompatible avec le calcul');
        if(data.color.mode!=='SPOT'&&data.color.mode!==before.color_space)throw Error('Mode colorimétrique incompatible');
        var background=null;for(var bi=0;bi<before.layers.length;bi++){if(before.layers[bi].name==='DOEMO:FOND'){if(bi!==before.layers.length-1)throw Error('Le calque DOEMO:FOND doit être sous toute l’architecture');background=doc.layers.getByName('DOEMO:FOND');}else checkLayer(before.layers[bi],data.regions);}
        var fill=paint(data.color),layer=null,i,j;
        for(i=0;i<doc.layers.length;i++)if(doc.layers[i].name===DOEMO_CIRC.layerName){if(layer)throw Error('Plusieurs calques DOEMO existent');layer=doc.layers[i];}
        var existing={};
        if(layer){if(layer.locked||layer.layers.length)throw Error('Calque vert verrouillé ou sous-calques non gérés : validation manuelle requise');
            for(i=0;i<layer.pageItems.length;i++){var old=layer.pageItems[i];if(old.parent!==layer)continue;var m=/^DOEMO-CIRC:([a-f0-9]+):([a-f0-9]{64})$/.exec(old.note||'');if(!m||fingerprint(old)!==m[2])throw Error('Surfaces vertes modifiées manuellement : conserver ou revalider avant régénération');existing[m[1]]=old;}
        }else{layer=doc.layers.add();layer.name=DOEMO_CIRC.layerName;}
        layer.visible=true;layer.locked=false;layer.zOrder(ZOrderMethod.SENDTOBACK);
        if(background)layer.move(background,ElementPlacement.PLACEBEFORE);
        // Keep unchanged generated objects; replace only changed owned shapes/styles.
        var created=[];
        for(i=0;i<data.regions.length;i++){
            var r=data.regions[i],compound=layer.compoundPathItems.add(),p=ring(compound,r.shape.shell,true);p.fillColor=fill;
            for(j=0;j<r.shape.holes.length;j++){p=ring(compound,r.shape.holes[j],false);p.fillColor=fill;}
            compound.opacity=data.color.opacity;compound.name=r.level+' / Circulation_'+r.id;
            var hash=fingerprint(compound);compound.note='DOEMO-CIRC:'+r.id+':'+hash;
            if(existing[r.id]){if(fingerprint(existing[r.id])===hash)compound.remove();else existing[r.id].remove();delete existing[r.id];}created.push(r.id);
        }
        for(var key in existing)if(Object.prototype.hasOwnProperty.call(existing,key))existing[key].remove();
        if(DOEMO_CIRC_NATIVE.hash(DOEMO_CIRC_NATIVE.inventory(doc))!==data.architecture_sha256)throw Error('Un objet original ou sa nuance a changé : sauvegarde annulée');
        var options=new IllustratorSaveOptions();options.pdfCompatible=true;options.compressed=true;
        doc.saveAs(output,options);doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;
        doc=app.open(output);DOEMO_CIRC_NATIVE.preflight(doc);
        var after=DOEMO_CIRC_NATIVE.hash(DOEMO_CIRC_NATIVE.inventory(doc));if(after!==data.architecture_sha256)throw Error('La copie enregistrée échoue au contrôle d’intégrité ; ne pas la valider');
        var checked=doc.layers.getByName(DOEMO_CIRC.layerName),count=0;
        for(i=0;i<checked.compoundPathItems.length;i++){var item=checked.compoundPathItems[i],match=/^DOEMO-CIRC:([a-f0-9]+):([a-f0-9]{64})$/.exec(item.note||'');if(!match||fingerprint(item)!==match[2])throw Error('Surface non conforme après réouverture');count++;}
        if(count!==created.length)throw Error('Nombre de surfaces incorrect après réouverture');
        DOEMO_CIRC_NATIVE.write(report,{schema:'doemo.circulations-native-report/1',source_sha256:data.source_sha256,output_sha256:DOEMO.sha256(DOEMO_CIRC_NATIVE.read(output,true)),
            native_ai_saved:true,reopened:true,editable_compound_paths:count,architecture_preserved:true,illustrator_version:app.version,visual_review_required:true});
        alert('Copie AI native enregistrée et rouverte. '+count+' surfaces éditables. Vérifier visuellement le vert et les portes avant livraison.');doc=null;
    }catch(e){alert('Import circulations interrompu : '+e.message+'. Le fichier source est conservé. Une copie éventuellement créée doit être contrôlée.');if(doc){try{doc.close(SaveOptions.DONOTSAVECHANGES);}catch(ignore){}}}finally{app.coordinateSystem=previous;}
}());
