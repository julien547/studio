/* Pure ES3 core shared by ExtendScript and the automated Node tests. No eval. */
var DOEMO = (function () {
  function fail(message) {
    throw new Error(message);
  }
  function finite(n) {
    return typeof n === "number" && isFinite(n);
  }
  function parse(text) {
    var at = 0,
      depth = 0;
    if (text.charCodeAt(0) === 65279) text = text.substring(1);
    function space() {
      while (/\s/.test(text.charAt(at)) && at < text.length) at++;
    }
    function string() {
      var s = "",
        c,
        esc,
        code;
      if (text.charAt(at++) !== '"') fail("Chaîne JSON attendue");
      while (at < text.length) {
        c = text.charAt(at++);
        if (c === '"') return s;
        if (c === "\\") {
          esc = text.charAt(at++);
          if (esc === "u") {
            code = text.substr(at, 4);
            if (!/^[0-9a-fA-F]{4}$/.test(code)) fail("Unicode JSON invalide");
            s += String.fromCharCode(parseInt(code, 16));
            at += 4;
          } else if (esc === '"' || esc === "\\" || esc === "/") s += esc;
          else if (esc === "n") s += "\n";
          else if (esc === "r") s += "\r";
          else if (esc === "t") s += "\t";
          else if (esc === "b") s += "\b";
          else if (esc === "f") s += "\f";
          else fail("Échappement JSON invalide");
        } else {
          if (c.charCodeAt(0) < 32) fail("Caractère JSON invalide");
          s += c;
        }
      }
      fail("Chaîne JSON incomplète");
    }
    function value() {
      var c, result, key, match;
      if (++depth > 60) fail("JSON trop imbriqué");
      space();
      c = text.charAt(at);
      if (c === '"') result = string();
      else if (c === "{" || c === "[") {
        at++;
        result = c === "{" ? {} : [];
        space();
        if (text.charAt(at) === (c === "{" ? "}" : "]")) at++;
        else
          while (true) {
            space();
            if (c === "{") {
              key = string();
              if (
                key === "__proto__" ||
                key === "constructor" ||
                key === "prototype" ||
                Object.prototype.hasOwnProperty.call(result, key)
              )
                fail("Clé JSON dangereuse ou dupliquée");
              space();
              if (text.charAt(at++) !== ":") fail("Deux-points attendu");
              result[key] = value();
            } else result.push(value());
            space();
            key = text.charAt(at++);
            if (key === (c === "{" ? "}" : "]")) break;
            if (key !== ",") fail("Séparateur JSON invalide");
          }
      } else if (text.substr(at, 4) === "true") {
        at += 4;
        result = true;
      } else if (text.substr(at, 5) === "false") {
        at += 5;
        result = false;
      } else if (text.substr(at, 4) === "null") {
        at += 4;
        result = null;
      } else {
        match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(text.substring(at));
        if (!match) fail("Valeur JSON invalide");
        result = Number(match[0]);
        at += match[0].length;
        if (!finite(result)) fail("Nombre JSON non fini");
      }
      depth--;
      return result;
    }
    var result = value();
    space();
    if (at !== text.length) fail("Contenu après JSON");
    return result;
  }
  function stringify(v) {
    var parts = [],
      i,
      key;
    if (v === null) return "null";
    if (typeof v === "string")
      return (
        '"' +
        v.replace(/["\\\x00-\x1f]/g, function (c) {
          var n = c.charCodeAt(0).toString(16);
          if (c === '"' || c === "\\") return "\\" + c;
          return "\\u" + ("0000" + n).slice(-4);
        }) +
        '"'
      );
    if (typeof v === "number") {
      if (!finite(v)) fail("Nombre non fini");
      return String(v);
    }
    if (typeof v === "boolean") return String(v);
    if (v instanceof Array) {
      for (i = 0; i < v.length; i++) parts.push(stringify(v[i]));
      return "[" + parts.join(",") + "]";
    }
    for (key in v)
      if (Object.prototype.hasOwnProperty.call(v, key) && typeof v[key] !== "undefined")
        parts.push(stringify(key) + ":" + stringify(v[key]));
    return "{" + parts.join(",") + "}";
  }
  function sha256(bytes) {
    var k = [],
      h = [],
      prime = 2,
      divisor,
      isPrime,
      i,
      j,
      words = [],
      bitLength = bytes.length * 8,
      w = [],
      a,
      b,
      c,
      d,
      e,
      f,
      g,
      hh,
      t1,
      t2;
    function rotr(x, n) {
      return (x >>> n) | (x << (32 - n));
    }
    while (k.length < 64) {
      isPrime = true;
      for (divisor = 2; divisor * divisor <= prime; divisor++)
        if (prime % divisor === 0) {
          isPrime = false;
          break;
        }
      if (isPrime) {
        if (h.length < 8) h.push((Math.pow(prime, 0.5) * 4294967296) | 0);
        k.push((Math.pow(prime, 1 / 3) * 4294967296) | 0);
      }
      prime++;
    }
    for (i = 0; i < bytes.length; i++)
      words[i >> 2] = (words[i >> 2] || 0) | ((bytes.charCodeAt(i) & 255) << (24 - (i % 4) * 8));
    words[bytes.length >> 2] =
      (words[bytes.length >> 2] || 0) | (128 << (24 - (bytes.length % 4) * 8));
    i = (((bytes.length + 8) >> 6) + 1) * 16;
    words[i - 2] = Math.floor(bitLength / 4294967296);
    words[i - 1] = bitLength | 0;
    for (j = 0; j < i; j += 16) {
      for (var n = 0; n < 64; n++) {
        if (n < 16) w[n] = words[j + n] || 0;
        else
          w[n] =
            ((rotr(w[n - 15], 7) ^ rotr(w[n - 15], 18) ^ (w[n - 15] >>> 3)) +
              w[n - 16] +
              (rotr(w[n - 2], 17) ^ rotr(w[n - 2], 19) ^ (w[n - 2] >>> 10)) +
              w[n - 7]) |
            0;
      }
      a = h[0];
      b = h[1];
      c = h[2];
      d = h[3];
      e = h[4];
      f = h[5];
      g = h[6];
      hh = h[7];
      for (n = 0; n < 64; n++) {
        t1 =
          (hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + k[n] + w[n]) | 0;
        t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        hh = g;
        g = f;
        f = e;
        e = (d + t1) | 0;
        d = c;
        c = b;
        b = a;
        a = (t1 + t2) | 0;
      }
      h[0] = (h[0] + a) | 0;
      h[1] = (h[1] + b) | 0;
      h[2] = (h[2] + c) | 0;
      h[3] = (h[3] + d) | 0;
      h[4] = (h[4] + e) | 0;
      h[5] = (h[5] + f) | 0;
      h[6] = (h[6] + g) | 0;
      h[7] = (h[7] + hh) | 0;
    }
    var out = "";
    for (i = 0; i < 8; i++) out += ("00000000" + (h[i] >>> 0).toString(16)).slice(-8);
    return out;
  }
  function utf8(text) {
    return unescape(encodeURIComponent(text));
  }
  function safePath(path) {
    if (typeof path !== "string" || !path || /(^\/|\\|:|\x00)/.test(path))
      fail("Chemin SAI invalide");
    var bits = path.split("/");
    for (var i = 0; i < bits.length; i++)
      if (!bits[i] || bits[i] === "." || bits[i] === "..") fail("Chemin SAI invalide");
    return path;
  }
  function validate(data) {
    if (
      data.schema_version !== "doemo.placements/1" ||
      !/^[a-zA-Z0-9_-]{1,80}$/.test(data.project_id)
    )
      fail("Format de placement inconnu");
    var coord = data.coordinate_system;
    if (
      !coord ||
      coord.unit !== "pt" ||
      coord.origin !== "artboard_top_left" ||
      coord.x_axis !== "right" ||
      coord.y_axis !== "down" ||
      coord.rotation_rule !== "clockwise_degrees" ||
      coord.size_rule !== "longest_visible_edge_mm_before_rotation"
    )
      fail("Repère de coordonnées incompatible");
    if (!data.target || !/^[a-f0-9]{64}$/.test(data.target.sha256)) fail("Empreinte BAT absente");
    if (
      !(data.placements instanceof Array) ||
      !data.placements.length ||
      data.placements.length > 10000
    )
      fail("Aucun placement ou lot excessif");
    var assets = {},
      floors = {},
      seen = {},
      i,
      p,
      a,
      f,
      keys = ["equipment", "asset", "floor", "position", "orientation", "size"];
    for (i = 0; i < data.assets.length; i++) {
      a = data.assets[i];
      if (assets[a.asset_id] || !/^[a-f0-9]{64}$/.test(a.sha256)) fail("Ressource SAI invalide");
      safePath(a.relative_path);
      if (!/\.ai$/i.test(a.relative_path)) fail("Ressource vectorielle AI requise");
      assets[a.asset_id] = a;
    }
    for (i = 0; i < data.target.floors.length; i++) {
      f = data.target.floors[i];
      if (
        floors[f.id] ||
        !f.confirmed ||
        !finite(f.artboard_index) ||
        f.artboard_index % 1 ||
        f.artboard_index < 0 ||
        !finite(f.target_page) ||
        f.target_page % 1 ||
        f.target_page < 1 ||
        f.target_page > data.target.pages.length
      )
        fail("Niveau invalide");
      floors[f.id] = f;
    }
    for (i = 0; i < data.placements.length; i++) {
      p = data.placements[i];
      f = floors[p.floor_id];
      if (
        !/^[a-zA-Z0-9_-]{1,80}$/.test(p.placement_id) ||
        seen[p.placement_id] ||
        p.validated !== true ||
        !assets[p.asset_id] ||
        !f
      )
        fail("Placement non validé ou dupliqué");
      seen[p.placement_id] = true;
      for (var j = 0; j < keys.length; j++)
        if (!p.review || p.review[keys[j]] !== true) fail("Six critères de validation requis");
      if (
        !finite(p.x) ||
        !finite(p.y) ||
        !finite(p.rotation_deg) ||
        !finite(p.size_mm) ||
        p.size_mm <= 0 ||
        p.size_mm > 200 ||
        Math.abs(p.rotation_deg) > 360
      )
        fail("Coordonnées ou taille invalides");
      var dims = data.target.pages[f.target_page - 1].pdf_size_pt;
      if (
        !dims ||
        !finite(dims[0]) ||
        !finite(dims[1]) ||
        p.x < 0 ||
        p.y < 0 ||
        p.x > dims[0] ||
        p.y > dims[1]
      )
        fail("Placement hors plan");
    }
    return { assets: assets, floors: floors };
  }
  function point(rect, x, y) {
    return [rect[0] + x, rect[1] - y];
  }
  function diff(placements, existing) {
    var result = [],
      seen = {},
      i,
      p,
      old;
    for (i = 0; i < placements.length; i++) {
      p = placements[i];
      seen[p.placement_id] = true;
      old = existing[p.placement_id];
      result.push({
        id: p.placement_id,
        action: !old
          ? "add"
          : old.manually_changed
            ? "conflict"
            : old.signature === signature(p)
              ? "unchanged"
              : "update",
        placement: p
      });
    }
    for (var key in existing)
      if (Object.prototype.hasOwnProperty.call(existing, key) && !seen[key])
        result.push({ id: key, action: "removed_preserve" });
    return result;
  }
  function signature(p) {
    return sha256(
      utf8(
        stringify({
          asset_id: p.asset_id,
          floor_id: p.floor_id,
          x: p.x,
          y: p.y,
          rotation_deg: p.rotation_deg,
          size_mm: p.size_mm
        })
      )
    );
  }
  return {
    parse: parse,
    stringify: stringify,
    sha256: sha256,
    utf8: utf8,
    safePath: safePath,
    validate: validate,
    point: point,
    diff: diff,
    signature: signature
  };
})();
if (typeof module !== "undefined") module.exports = DOEMO;
