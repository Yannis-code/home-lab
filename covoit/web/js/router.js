const routes = [];

/** Enregistre une route. ``pattern`` est une regexp avec groupes nommés, ex: /^#\/groups\/(?<id>\d+)$/ */
export function route(pattern, handler) {
  routes.push({ pattern, handler });
}

function match(hash) {
  for (const r of routes) {
    const result = r.pattern.exec(hash);
    if (result) return { handler: r.handler, params: result.groups || {} };
  }
  return null;
}

export function navigate(hash) {
  location.hash = hash;
}

export function start(root, { defaultHash = "#/login", onRender } = {}) {
  async function render() {
    const hash = location.hash || defaultHash;
    if (!location.hash) {
      location.hash = defaultHash;
      return;
    }
    const found = match(hash);
    if (onRender) onRender(hash);
    if (!found) {
      root.innerHTML = `<div class="card"><p>Page introuvable.</p></div>`;
      return;
    }
    root.innerHTML = `<p class="muted">Chargement…</p>`;
    try {
      await found.handler(root, found.params);
    } catch (error) {
      root.innerHTML = `<div class="error">${error.message}</div>`;
    }
  }
  window.addEventListener("hashchange", render);
  render();
}
