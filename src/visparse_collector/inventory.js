({maxNodes, maxScan, styles}) => {
  const nodes = [], ids = new Map();
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_ELEMENT);
  let element = walker.currentNode, scanned = 0, truncated = false;
  while (element) {
    if (scanned >= maxScan || nodes.length >= maxNodes) { truncated = true; break; }
    scanned++;
    const css = getComputedStyle(element), box = element.getBoundingClientRect();
    const visible = css.display !== 'none' && css.visibility !== 'hidden' && Number(css.opacity) !== 0 &&
      box.width > 0 && box.height > 0 && box.bottom > 0 && box.right > 0 && box.top < innerHeight && box.left < innerWidth;
    if (visible) {
      const id = `node-${nodes.length + 1}`; ids.set(element, id);
      let parent = element.parentElement;
      while (parent && !ids.has(parent)) parent = parent.parentElement;
      const attributes = {};
      for (const name of ['role', 'aria-label', 'aria-labelledby', 'aria-expanded', 'aria-checked', 'aria-selected', 'aria-disabled', 'tabindex', 'disabled', 'type']) {
        if (element.hasAttribute(name)) attributes[name] = element.getAttribute(name).slice(0, 160);
      }
      const computed = {};
      for (const name of styles) computed[name] = css.getPropertyValue(name).slice(0, 240);
      // Exclude editable content and all form values from textual evidence.
      const sensitive = element.closest('input,textarea,select,[contenteditable]');
      const directText = sensitive ? '' : Array.from(element.childNodes)
        .filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent.slice(0, 160)).join(' ').slice(0, 160);
      nodes.push({id, parent_id: parent ? ids.get(parent) : null, tag: element.tagName.toLowerCase(),
        text: directText, attributes, box: {x: box.x, y: box.y, width: box.width, height: box.height}, styles: computed});
    }
    element = walker.nextNode();
  }
  const css_variables = {}, rootStyle = getComputedStyle(document.documentElement);
  for (let i = 0; i < rootStyle.length && Object.keys(css_variables).length < 64; i++) {
    const key = rootStyle[i];
    if (/^--(color|font|space|radius|shadow)-/.test(key)) css_variables[key] = rootStyle.getPropertyValue(key).slice(0, 240);
  }
  return {nodes, css_variables, coverage: {scanned, captured: nodes.length, truncated,
    omissions: ['Viewport-visible light DOM sample only; offscreen, shadow DOM, and frame contents excluded.',
      'ARIA attributes are raw evidence; implicit roles and computed accessible names are in the separate accessibility capture.',
      'Custom properties limited to 64 matching root properties; no complete token inventory is claimed.',
      'Editable/form values omitted; screenshots mask editable/form controls.']},
    scroll_x: scrollX, scroll_y: scrollY, mutation_count: window.__visparseMutationCount || 0};
}
