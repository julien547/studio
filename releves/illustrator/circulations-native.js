/* Native inventory in DOCUMENTCOORDINATESYSTEM; requires doemo-core.js. */
var DOEMO_CIRC_NATIVE=(function(){
    function read(f,binary){f.encoding=binary?"BINARY":"UTF-8";if(!f.open("r"))throw Error("Lecture impossible : "+f.name);var s=f.read();f.close();return s;}
    function write(f,v){if(f.exists)throw Error("Fichier déjà présent : "+f.name);f.encoding="UTF-8";if(!f.open("w"))throw Error("Écriture impossible");f.write(DOEMO.stringify(v));f.close();}
    function color(c){if(!c)return null;var k=c.typename;if(k==="RGBColor")return [k,c.red,c.green,c.blue];if(k==="CMYKColor")return[k,c.cyan,c.magenta,c.yellow,c.black];if(k==="GrayColor")return[k,c.gray];if(k==="SpotColor")return[k,c.spot.name,c.tint,color(c.spot.color)];return[k,String(c)];}
    function node(p){return[p.anchor[0],p.anchor[1],p.leftDirection[0],p.leftDirection[1],p.rightDirection[0],p.rightDirection[1]];}
    function item(o){var d={type:o.typename,name:o.name||"",hidden:o.hidden,locked:o.locked,opacity:o.opacity,note:o.note||"",bounds:[],children:[]},i,b=o.geometricBounds;
        for(i=0;i<4;i++)d.bounds.push(b[i]);
        if(o.typename==="PathItem"){d.closed=o.closed;d.filled=o.filled;d.stroked=o.stroked;d.width=o.strokeWidth;d.fill=o.filled?color(o.fillColor):null;d.stroke=o.stroked?color(o.strokeColor):null;d.clipping=o.clipping;d.guides=o.guides;d.evenodd=o.evenodd;d.nodes=[];for(i=0;i<o.pathPoints.length;i++)d.nodes.push(node(o.pathPoints[i]));}
        else if(o.typename==="CompoundPathItem"){for(i=0;i<o.pathItems.length;i++)d.children.push(item(o.pathItems[i]));}
        else if(o.typename==="GroupItem"){d.clipped=o.clipped;for(i=0;i<o.pageItems.length;i++)if(o.pageItems[i].parent===o)d.children.push(item(o.pageItems[i]));}
        else if(o.typename==="TextFrame"){d.text=o.contents;d.fonts=[];for(i=0;i<o.textRanges.length;i++){try{d.fonts.push(o.textRanges[i].characterAttributes.textFont.name);}catch(e){d.fonts.push("UNRESOLVED");}}}
        else if(o.typename==="PlacedItem"){d.file=o.file.fsName;d.link_exists=o.file.exists;}
        else if(o.typename==="SymbolItem")d.symbol=o.symbol.name;
        try{var m=o.matrix;d.matrix=[m.mValueA,m.mValueB,m.mValueC,m.mValueD,m.mValueTX,m.mValueTY];}catch(e){}
        return d;
    }
    function inventory(doc){
        function layer(l){var d={name:l.name,visible:l.visible,locked:l.locked,items:[],layers:[]},i;
            for(i=0;i<l.pageItems.length;i++)if(l.pageItems[i].parent===l)d.items.push(item(l.pageItems[i]));
            for(i=0;i<l.layers.length;i++)d.layers.push(layer(l.layers[i]));return d;}
        var result={artboards:[],layers:[],color_space:doc.documentColorSpace===DocumentColorSpace.CMYK?"CMYK":"RGB",swatches:[]},i,r;
        for(i=0;i<doc.artboards.length;i++){r=doc.artboards[i].artboardRect;result.artboards.push([r[0],r[1],r[2],r[3]]);}
        for(i=0;i<doc.layers.length;i++)if(doc.layers[i].name!==DOEMO_CIRC.layerName)result.layers.push(layer(doc.layers[i]));
        for(i=0;i<doc.swatches.length;i++)result.swatches.push({name:doc.swatches[i].name,color:color(doc.swatches[i].color)});
        return result;
    }
    function hash(v){return DOEMO.sha256(DOEMO.utf8(DOEMO.stringify(v)));}
    function preflight(doc){var missing=[],i,f;for(i=0;i<doc.placedItems.length;i++)if(!doc.placedItems[i].file.exists)missing.push(doc.placedItems[i].file.name);
        if(missing.length)throw Error("Liens manquants : "+missing.join(", "));
        for(i=0;i<doc.textFrames.length;i++){try{f=doc.textFrames[i].textRange.characterAttributes.textFont.name;if(!f)throw Error("Font");app.textFonts.getByName(f);}catch(e){throw Error("Police non résolue : contrôler le document dans Illustrator");}}
    }
    return{read:read,write:write,item:item,inventory:inventory,hash:hash,preflight:preflight};
}());
