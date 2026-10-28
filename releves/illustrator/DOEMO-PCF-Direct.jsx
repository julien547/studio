#target illustrator
/* Exact polygon paths from the verified SAI PCF PDF, created in the target document.
   No app.open, clipboard operation, or cross-document duplication. */
(function () {
    var doc=null,created=[],old=[],replaced=false;
    var stage="Recherche des deux PCF",coordinates=app.coordinateSystem;
    function inLayer(item) {
        while(item&&item.typename!=="Document") {
            if(item.typename==="Layer"&&item.name==="DOEMO - COMPLEMENTS PROVISOIRES - ANIMALIS")return true;
            item=item.parent;
        }
        return false;
    }
    function available(item) {
        while(item&&item.typename!=="Document") {
            if(item.locked||item.hidden||(item.typename==="Layer"&&!item.visible))return false;
            item=item.parent;
        }
        return true;
    }
    function color(values) {
        var c=new CMYKColor();c.cyan=values[0]*100;c.magenta=values[1]*100;
        c.yellow=values[2]*100;c.black=values[3]*100;return c;
    }
    function draw(group,text,left,bottom,scale) {
        var tokens=text.match(/\S+/g),numbers=[],stack=[],points=[],closed=false,count=0;
        var state={x:0,y:0,fill:[0,0,0,1],stroke:[0,0,0,1],width:1,miter:10};
        function point(x,y){return [left+(x+state.x)*scale,bottom+(y+state.y)*scale];}
        function paint(op) {
            if(points.length<3)throw Error("Trace PCF incomplet.");
            var p=group.pathItems.add();p.setEntirePath(points);p.closed=closed;
            p.filled=op!=="S";p.stroked=op==="S";p.evenodd=op==="f*";
            if(p.filled){p.fillColor=color(state.fill);p.fillOverprint=false;}
            if(p.stroked){p.strokeColor=color(state.stroke);p.strokeWidth=state.width*scale;p.strokeMiterLimit=state.miter;p.strokeJoin=StrokeJoin.MITERENDJOIN;p.strokeOverprint=false;}
            p.opacity=100;p.zOrder(ZOrderMethod.BRINGTOFRONT);
            p.name="PCF - trace source "+(++count);points=[];closed=false;
        }
        for(var i=0;i<tokens.length;i++) {
            var op=tokens[i];
            if(/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(op)){numbers.push(Number(op));continue;}
            if(op.charAt(0)==="/")continue;
            if(op==="q")stack.push({x:state.x,y:state.y,fill:state.fill,stroke:state.stroke,width:state.width,miter:state.miter});
            else if(op==="Q"){if(!stack.length)throw Error("Pile PCF invalide.");state=stack.pop();}
            else if(op==="cm") {
                if(numbers.length!==6||numbers[0]!==1||numbers[1]!==0||numbers[2]!==0||numbers[3]!==1)throw Error("Transformation PCF inattendue.");
                state.x+=numbers[4];state.y+=numbers[5];
            }
            else if(op==="k"||op==="K") {
                if(numbers.length!==4)throw Error("Couleur PCF invalide.");
                if(op==="k")state.fill=numbers.slice(0);else state.stroke=numbers.slice(0);
            }
            else if(op==="scn")state.fill=[0,0,0,0];
            else if(op==="SCN")state.stroke=[0,0,0,0];
            else if(op==="w")state.width=numbers[0];
            else if(op==="M")state.miter=numbers[0];
            else if(op==="m"){if(points.length)throw Error("Contour PCF inattendu.");points=[point(numbers[0],numbers[1])];}
            else if(op==="l")points.push(point(numbers[0],numbers[1]));
            else if(op==="re") {
                var x=numbers[0],y=numbers[1],w=numbers[2],h=numbers[3];
                points=[point(x,y),point(x+w,y),point(x+w,y+h),point(x,y+h)];closed=true;
            }
            else if(op==="h")closed=true;
            else if(op==="f"||op==="f*"||op==="S")paint(op);
            else if(op!=="BDC"&&op!=="EMC"&&op!=="cs"&&op!=="CS"&&op!=="gs")throw Error("Instruction PCF inattendue : "+op);
            numbers=[];
        }
        if(count!==9||stack.length||points.length)throw Error("Les neuf traces du PCF ne sont pas complets.");
    }
    try {
        if(!app.documents.length)throw Error("Ouvrir plansv3.ai.");
        doc=app.activeDocument;app.coordinateSystem=CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
        var found={},i,item,match;
        for(i=0;i<doc.groupItems.length;i++) {
            item=doc.groupItems[i];match=/DOEMO Animalis \/ position (13|14) \//.exec(item.note||"");
            if(match&&inLayer(item)) {
                if(found[match[1]])throw Error("Numero PCF duplique.");
                if((item.note||"").indexOf("DOEMO-PCF-DIRECT-V1")>=0)throw Error("Cette copie contient deja la correction directe.");
                if(!available(item))throw Error("Afficher et deverrouiller le calque des complements.");
                found[match[1]]=item;
            }
        }
        if(!found[13]||!found[14])throw Error("Les deux PCF a remplacer sont introuvables.");
        old=[found[13],found[14]];
        var data=File(File($.fileName).parent.fsName+"/PCF-traces.txt");data.encoding="UTF-8";
        if(!data.exists||data.length>20000||!data.open("r"))throw Error("Fichier PCF-traces.txt absent ou invalide.");
        var text=data.read();data.close();
        var output=File.saveDialog("Enregistrer une NOUVELLE copie AI avec les deux PCF corrigees","*.ai");
        if(!output)return;
        if(output.name.slice(-3).toLowerCase()!==".ai")output=File(output.fsName+".ai");
        if(output.exists)throw Error("Choisir un nouveau nom pour conserver l'original.");
        for(i=0;i<old.length;i++) {
            stage="Creation directe de la PCF "+(i===0?13:14);
            var b=old[i].visibleBounds,x=(b[0]+b[2])/2,y=(b[1]+b[3])/2;
            var size=Math.max(b[2]-b[0],b[1]-b[3]);
            if(size<15||size>25)throw Error("Taille PCF inattendue.");
            var group=old[i].parent.groupItems.add();created.push(group);
            draw(group,text,x-size/2,y-size/2,size/19.842);
            var check=group.visibleBounds;
            if(Math.abs((check[0]+check[2])/2-x)>0.01||Math.abs((check[1]+check[3])/2-y)>0.01)throw Error("Controle de position PCF en echec.");
            group.name=(i===0?13:14)+" - Porte coupe-feu - A CONTROLER";
            group.note=(old[i].note||"")+" / DOEMO-PCF-DIRECT-V1 / 9 traces vectoriels de la ressource SAI";
        }
        stage="Retrait des deux symboles incorrects";replaced=true;
        for(i=0;i<old.length;i++)old[i].remove();
        stage="Enregistrement de la copie AI";
        var options=new IllustratorSaveOptions();options.pdfCompatible=true;options.compressed=true;
        doc.saveAs(output,options);app.redraw();
        alert("Deux PCF creees directement : porte blanche et flamme. Copie AI enregistree. Verifier visuellement les deux portes.");
    } catch(e) {
        if(!replaced)for(var k=created.length-1;k>=0;k--){try{created[k].remove();}catch(ignoreGroup){}}
        alert("DOEMO - Etape : "+stage+"\n"+e.message+(replaced?"\nLes corrections restent ouvertes : verifier puis enregistrer sous un nouveau nom.":"\nLes pictogrammes existants sont conserves."));
    } finally {app.coordinateSystem=coordinates;}
}());
