"""External deterministic fixture adapter, not a production generator or model.

Input directory contains only handoff.json and target.html. No Visparse imports,
source assets, oracle, or source implementation are read.
"""
import json
from pathlib import Path


def generate(directory):
    directory=Path(directory)
    handoff=json.loads((directory/'handoff.json').read_text())
    binding=next(b for b in handoff['bindings'] if b['ready'])
    pattern=next(p for p in handoff['source_export']['patterns'] if p['id']==binding['pattern_id'])
    if pattern['semantic']!='save-entity' or pattern['persistence']!='reload':
        raise ValueError('fixture adapter supports only grounded save/remove/reload')
    if not {'save','remove','reload'} <= set(binding['roles']):raise ValueError('incomplete roles')
    # The target owns labels, entity IDs and storage key. Transfer only the supplied
    # save/remove/persistence pattern, preserving independently implemented tasks.
    script="""
<script data-transferred-pattern="save-entity">
(() => {
const storageKey=document.body.dataset.storage;
const selected=new Set(JSON.parse(localStorage.getItem(storageKey)||'[]'));
for(const control of document.querySelectorAll('[data-bookmark]')) {
 const entity=control.closest('[data-id]').dataset.id;
 const paint=()=>{control.textContent=selected.has(entity)?control.dataset.removeLabel:control.dataset.saveLabel;control.setAttribute('aria-pressed',String(selected.has(entity)))};
 control.onclick=()=>{if(selected.has(entity))selected.delete(entity);else selected.add(entity);localStorage.setItem(storageKey,JSON.stringify([...selected]));paint()};
 paint();
}
})();
</script>
"""
    html=(directory/'target.html').read_text()
    if '</body>' not in html:raise ValueError('unsupported target fixture')
    (directory/'generated.html').write_text(html.replace('</body>',script+'</body>'))


if __name__=='__main__':
    import sys
    generate(sys.argv[1])
