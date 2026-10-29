/* Shared ExtendScript/Node geometry contract. No Illustrator side effects here. */
var DOEMO_CIRC = (function () {
    var layerName = "DOEMO — VERT CIRCULATIONS";
    function finite(n) { return typeof n === "number" && isFinite(n) && Math.abs(n) <= 10000000; }
    function ring(v) { if (!(v instanceof Array) || v.length < 3 || v.length > 20000) throw Error("Contour invalide"); for (var i=0;i<v.length;i++) if(v[i].length!==2||!finite(v[i][0])||!finite(v[i][1]))throw Error("Coordonnées invalides"); }
    function validate(d) {
        if(d.schema_version!=="doemo.circulations-export/1"||d.units!=="pt"||d.coordinate_system!=="illustrator_document_y_up")throw Error("Contrat de coordonnées incompatible");
        if(!/^[0-9a-f]{64}$/.test(d.source_sha256)||!/^[0-9a-f]{64}$/.test(d.architecture_sha256))throw Error("Empreinte source absente");
        if(!d.color||d.color.approved!==true||!d.regions||!d.regions.length||d.regions.length>10000)throw Error("Circulations ou nuance non validées");
        var c=d.color,limit=c.mode==='RGB'?255:100;
        if(!finite(c.opacity)||c.opacity<=0||c.opacity>100||!finite(c.tint)||c.tint<0||c.tint>100)throw Error('Opacité ou teinte invalide');
        if(c.mode==='SPOT'){if(typeof c.swatch!=='string'||!c.swatch)throw Error('Ton direct absent');}
        else{if(c.mode!=='RGB'&&c.mode!=='CMYK')throw Error('Mode de nuance invalide');if(c.mode!==d.color_space||c.values.length!==(c.mode==='RGB'?3:4))throw Error('Mode du document incompatible');for(var k=0;k<c.values.length;k++)if(!finite(c.values[k])||c.values[k]<0||c.values[k]>limit)throw Error('Composante de nuance invalide');}
        if(!d.artboards||!d.artboards.length)throw Error('Plans de travail absents');
        var ids={},i,j,r;
        for(i=0;i<d.regions.length;i++){r=d.regions[i];if(r.status!=="validated"||r.category!=="circulation"||ids[r.id])throw Error("Région non validée ou dupliquée");ids[r.id]=true;ring(r.shape.shell);for(j=0;j<r.shape.holes.length;j++)ring(r.shape.holes[j]);var bounds=d.artboards[r.artboard];if(!bounds)throw Error('Plan de travail de région absent');var rings=[r.shape.shell].concat(r.shape.holes);for(j=0;j<rings.length;j++)for(var p=0;p<rings[j].length;p++){var xy=rings[j][p];if(xy[0]<bounds[0]||xy[0]>bounds[2]||xy[1]>bounds[1]||xy[1]<bounds[3])throw Error('Région hors du plan de travail');}}
        return d;
    }
    function area(points){var a=0;for(var i=0;i<points.length;i++){var j=(i+1)%points.length;a+=points[i][0]*points[j][1]-points[j][0]*points[i][1];}return a/2;}
    function oriented(points,positive){var p=points.slice();if(p.length>1&&p[0][0]===p[p.length-1][0]&&p[0][1]===p[p.length-1][1])p.pop();if((area(p)>0)!==positive)p.reverse();return p;}
    return {layerName:layerName,validate:validate,oriented:oriented};
}());
if(typeof module!=="undefined")module.exports=DOEMO_CIRC;
