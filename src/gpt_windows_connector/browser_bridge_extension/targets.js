// Runs in the extension's isolated world. References never enter page attributes.
(() => {
  let targets = new Map();
  const identity = el => JSON.stringify([
    el.tagName, el.getAttribute("role"), el.innerText || "",
    el.getAttribute("aria-label"), el.getAttribute("name"),
    el.getAttribute("placeholder"), el.getAttribute("type"), el.id
  ]);
  globalThis.lucasTargets = {
    observe(nodes) {
      targets = new Map();
      const prefix = "ref:" + crypto.randomUUID() + ":";
      return nodes.map((el, index) => {
        const ref = prefix + index;
        targets.set(ref, { el, identity: identity(el) });
        return ref;
      });
    },
    resolve(ref, visible) {
      const record = targets.get(ref);
      if (!record) throw new Error("Unknown or expired element ref on this tab. Call observe again.");
      const el = record.el;
      if (!el.isConnected || !visible(el) || identity(el) !== record.identity)
        throw new Error("Element changed or disappeared. Call observe again.");
      if (el.disabled) throw new Error("Referenced element is disabled.");
      return el;
    }
  };
})();
