#!/usr/bin/env python3
"""Build the existing editor as an external JS file; no inline script/CSP relaxation."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
template = (root / 'reconstruction/editor/editor.html').read_text()
markup = template[template.index('<style>'):template.index('<script id="project-data"')]
# Embedded under the current studio-host menu: no second application banner.
markup = markup[:markup.index('<header>')] + markup[markup.index('</header>')+len('</header>'):]
markup = markup.replace(':root{', ':host{').replace('height:calc(100vh - 68px)', 'height:782px')
markup = markup.replace('</style>', '[hidden]{display:none!important}main{grid-template-rows:minmax(0,1fr)}#stage,#viewport{min-height:0}</style>')
code = template.split('<script>\n', 1)[1].rsplit('</script>', 1)[0]
code = code[:code.index("try{const data=$('project-data')")]
code = code.replace("render();say('Correction enregistrée dans la session. Enregistrez le projet JSON.');",
                    "onChange();render();say('Correction en mémoire. Cliquez sur Enregistrer sur OVH.');")
code = code.replace("index=doc.levels.indexOf(l);$('level').value=index;", "onChange();index=doc.levels.indexOf(l);$('level').value=index;")
output = """// Generated from reconstruction/editor/editor.html by reconstruction/ovh/build_web.py.
(() => {
let active = null;
window.doemoEditor = {
  mount: async function(host, initial, user, onChange) {
    const root = host.shadowRoot || host.attachShadow({mode:'open'});
    root.innerHTML = MARKUP;
    const realDocument = globalThis.document;
    const document = {
      getElementById: id => root.getElementById(id),
      createElement: (...args) => realDocument.createElement(...args),
      createElementNS: (...args) => realDocument.createElementNS(...args),
      addEventListener: (...args) => root.addEventListener(...args),
    };
CODE
    $('actor').value = user; $('actor').readOnly = true;
    $('load').parentElement.hidden = true;
    load(initial);
    active = {document:()=>clone(doc),replace:value=>{doc=check(value);render()},
      lock:value=>{root.querySelector('main').inert=value}};
  },
  document: () => active.document(),
  replace: value => active.replace(value),
  lock: value => active && active.lock(value),
};
})();
""".replace('MARKUP', json.dumps(markup, ensure_ascii=False)).replace('CODE', code)
(root / 'redessin/editor.js').write_text(output)
print('redessin/editor.js generated')
