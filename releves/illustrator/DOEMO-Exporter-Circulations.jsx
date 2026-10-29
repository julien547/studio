#target illustrator
/* Extract without modifying the source. Review calculated JSON in DOEMO Studio. */
(function(){
    var home=File($.fileName).parent,previous=app.coordinateSystem;
    $.evalFile(File(home+'/doemo-core.js'));$.evalFile(File(home+'/circulations-core.js'));$.evalFile(File(home+'/circulations-native.js'));
    try{
        if(parseInt(app.version,10)<28||!app.documents.length)throw Error('Ouvrir le fichier AI dans Illustrator 2024 ou plus récent.');
        var doc=app.activeDocument;if(!doc.saved||!/\.ai$/i.test(doc.fullName.name))throw Error('Enregistrer la version source AI avant extraction.');
        app.coordinateSystem=CoordinateSystem.DOCUMENTCOORDINATESYSTEM;DOEMO_CIRC_NATIVE.preflight(doc);
        var inv=DOEMO_CIRC_NATIVE.inventory(doc),paths=[],texts=[],levels=[],counter=0,warnings=[];
        function role(name){var n=name.toUpperCase();if(n.indexOf('DOEMO:SEUIL')>=0)return 'door_threshold';if(n.indexOf('DOEMO:PASSAGE')>=0)return 'passage';if(n.indexOf('DOEMO:OBSTACLE')>=0)return 'obstacle';if(n.indexOf('DOEMO:VERT_EXISTANT')>=0)return 'existing_green';if(n.indexOf('DOEMO:MUR')>=0)return 'wall';return 'unknown';}
        function visit(o,parentRole,layer,visible,clipped){var r=role(o.name)||parentRole,i;if(r==='unknown')r=parentRole;var isClip=clipped||o.clipped||o.clipping;
            if(o.type==='PathItem'&&o.nodes.length>=2&&(!o.guides||r!=='unknown'||(o.name||'').indexOf('DOEMO:EMPRISE:')===0)){
                var name=o.name||'',nodes=o.nodes;
                if(name.indexOf('DOEMO:EMPRISE:')===0){
                    if(!o.closed||isClip)throw Error('Emprise fermée, sans masque requise.');
                    var shell=[];for(i=0;i<nodes.length;i++){if(nodes[i][0]!==nodes[i][2]||nodes[i][1]!==nodes[i][3]||nodes[i][0]!==nodes[i][4]||nodes[i][1]!==nodes[i][5])throw Error('Emprise courbe : fournir un contour polygonal de contrôle avec tolérance vérifiée.');shell.push([nodes[i][0],nodes[i][1]]);}
                    var board=-1;for(i=0;i<inv.artboards.length;i++){var b=inv.artboards[i],fits=true;for(var j=0;j<shell.length;j++)if(shell[j][0]<b[0]||shell[j][0]>b[2]||shell[j][1]>b[1]||shell[j][1]<b[3])fits=false;if(fits){if(board>=0)throw Error('Emprise dans plusieurs plans de travail.');board=i;}}
                    if(board<0)throw Error('Emprise hors plan de travail');var id=name.substring(14);levels.push({id:id,name:id,artboard:board,footprint:{shell:shell,holes:[]}});
                }else paths.push({id:'path-'+(++counter),role:r,nodes:nodes,closed:o.closed,filled:o.filled,fill:o.fill,stroke:o.stroke,stroke_width:o.stroked?o.width:0,visible:r==='door_threshold'||(visible&&!o.hidden),clipped:!!isClip,layer:layer});
            }else if(o.type==='TextFrame'&&visible&&!o.hidden)texts.push({text:o.text,point:[(o.bounds[0]+o.bounds[2])/2,(o.bounds[1]+o.bounds[3])/2],level:''});
            for(i=0;i<o.children.length;i++)visit(o.children[i],r,layer,visible&&!o.hidden,isClip||o.type==='CompoundPathItem');
        }
        function walk(l,parentVisible,parentRole){var r=role(l.name);if(r==='unknown')r=parentRole;for(var i=0;i<l.items.length;i++)visit(l.items[i],r,l.name,parentVisible&&l.visible,false);for(i=0;i<l.layers.length;i++)walk(l.layers[i],parentVisible&&l.visible,r);}
        for(var i=0;i<inv.layers.length;i++)walk(inv.layers[i],true,'unknown');
        // Raw texts are assigned spatially after level qualification in DOEMO.
        // No footprint is invented when the source has no named helper paths.
        var levelTexts=texts;
        var sha=DOEMO.sha256(DOEMO_CIRC_NATIVE.read(doc.fullName,true));
        var output=File.saveDialog('Exporter la géométrie pour la page Circulations DOEMO','*.json');if(!output)return;
        DOEMO_CIRC_NATIVE.write(output,{schema_version:'doemo.circulations-source/1',provider:'illustrator',document_id:DOEMO_CIRC_NATIVE.hash(doc.fullName.fsName).substring(0,24),source_name:doc.fullName.name,
            source_sha256:sha,architecture_sha256:DOEMO_CIRC_NATIVE.hash(inv),units:'pt',coordinate_system:'illustrator_document_y_up',color_space:inv.color_space,
            artboards:inv.artboards,levels:levels,paths:paths,texts:levelTexts,inventory:inv});
        alert('Géométrie exportée. Importez ce JSON dans DOEMO → Circulations, confirmez les murs et emprises puis validez les surfaces. Le fichier source est inchangé.');
    }catch(e){alert('Extraction circulations interrompue : '+e.message);}finally{app.coordinateSystem=previous;}
}());
