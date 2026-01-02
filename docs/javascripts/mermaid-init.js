/* global mermaid, document$ */
mermaid.initialize({ startOnLoad: false });

let mermaidIdCounter = 0;

function renderMermaid() {
  const blocks = document.querySelectorAll(".mermaid:not([data-processed])");
  blocks.forEach((el) => {
    const code = (el.textContent || "").trim();
    if (!code) return;

    const id = `mermaid-${mermaidIdCounter++}`;
    Promise.resolve(mermaid.render(id, code))
      .then(({ svg, bindFunctions }) => {
        el.innerHTML = svg;
        el.setAttribute("data-processed", "true");
        if (typeof bindFunctions === "function") bindFunctions(el);
      })
      .catch(() => {
        // Mermaid renders its own error message; don't break navigation.
      });
  });
}

if (typeof document$ !== "undefined" && document$ && document$.subscribe) {
  document$.subscribe(renderMermaid);
} else {
  window.addEventListener("load", renderMermaid);
}

