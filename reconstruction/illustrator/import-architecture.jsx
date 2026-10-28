#target illustrator
/* DOEMO reconstruction 0.2. Import contract for a local connector adapter.
   Also runnable with File > Scripts > Other Script. Does not save/overwrite AI files. */
(function () {
    if (typeof JSON === 'undefined' || typeof JSON.parse !== 'function') {
        alert('Le connecteur doit fournir un parseur JSON validé. Aucun eval du fichier.'); return;
    }
    var file = File.openDialog('Choisir le JSON architectural validé', '*.json');
    if (!file) return;
    var previousCoordinates = app.coordinateSystem;
    try {
        file.encoding = 'UTF-8'; if (!file.open('r')) throw Error('Fichier illisible');
        var text = file.read(); file.close();
        var job = JSON.parse(text);
        if (job.schema !== 'doemo.architecture.illustrator/2') throw Error('Contrat incompatible');
        // Validate everything before mutating Illustrator.
        for (var n=0;n<job.levels.length;n++) {
            var l=job.levels[n];
            if(l.unit!=='pt') throw Error('Unité image : conversion en points à valider avant import.');
            if(!(l.stroke_width>0&&l.stroke_width<=50)) throw Error('Trait graphique invalide');
            if(!(l.width>0&&l.height>0&&l.width<16000&&l.height<16000)) throw Error('Format non pris en charge');
            for(var w=0;w<l.walls.length;w++) for(var p=0;p<l.walls[w].paths.length;p++) {
                var axis=l.walls[w].paths[p];
                if(axis.length!==2) throw Error('Axe de mur invalide');
                for(var v=0;v<2;v++) if(!isFinite(axis[v][0])||!isFinite(axis[v][1])) throw Error('Coordonnées invalides');
            }
        }
        app.coordinateSystem=CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        for(var i=0;i<job.levels.length;i++) {
            var level=job.levels[i];
            var doc=app.documents.add(DocumentColorSpace.RGB,level.width,level.height);
            var rect=doc.artboards[0].artboardRect;
            doc.artboards[0].name=level.id;
            var names=['Équipements incendie','Textes','Pièces','Escaliers','Fenêtres','Portes','Murs'];
            var layers={};
            for(var k=0;k<names.length;k++){var layer=doc.layers.add();layer.name=names[k];layers[names[k]]=layer;}
            var black=new RGBColor();black.red=0;black.green=0;black.blue=0;
            for(var j=0;j<level.walls.length;j++) {
                var wall=level.walls[j],group=layers['Murs'].groupItems.add();group.name='wall-'+wall.id;
                for(var m=0;m<wall.paths.length;m++) {
                    var pts=wall.paths[m],coords=[];
                    for(var q=0;q<pts.length;q++) coords.push([rect[0]+pts[q][0],rect[1]-pts[q][1]]);
                    var path=group.pathItems.add();path.setEntirePath(coords);path.closed=false;path.stroked=true;path.filled=false;path.strokeColor=black;path.strokeWidth=level.stroke_width;path.strokeDashes=[];path.strokeCap=StrokeCap.BUTTENDCAP;path.strokeJoin=StrokeJoin.MITERENDJOIN;
                }
            }
            if(level.reference && level.reference.indexOf('data:image/png;base64,')===0) {
                var tmp=new File(Folder.temp.fsName+'/doemo-reference-'+(new Date().getTime())+'-'+i+'.png');
                try {
                    tmp.encoding='BINARY';if(!tmp.open('w'))throw Error('Référence temporaire inaccessible');
                    tmp.write(decode64(level.reference.substring(22)));tmp.close();
                    var reference=doc.layers.add();reference.name='Référence';
                    var placed=reference.placedItems.add();placed.file=tmp;placed.position=[rect[0],rect[1]];
                    placed.width=level.width;placed.height=level.height;placed.embed();
                    reference.locked=true;reference.visible=false;
                } finally {if(tmp.opened)tmp.close();tmp.remove();}
            }
        }
        alert('Murs validés importés. Contrôlez les raccords et enregistrez chaque document au format AI.');
    } catch(error) {alert('Import interrompu : '+error.message);}
    finally {app.coordinateSystem=previousCoordinates;}
    function decode64(s) {
        var abc='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',buffer=0,bits=0,out='';
        for(var i=0;i<s.length;i++){if(s.charAt(i)==='=')break;var v=abc.indexOf(s.charAt(i));if(v<0)throw Error('Référence base64 invalide');buffer=(buffer<<6)|v;bits+=6;if(bits>=8){bits-=8;out+=String.fromCharCode((buffer>>bits)&255);}}
        return out;
    }
})();
