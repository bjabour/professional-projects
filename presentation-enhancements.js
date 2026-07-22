(() => {
  document.body.classList.add("skill-enhanced");

  // The electricity presentation already carries the complete bundled viewer.
  if (document.querySelector("#plotZoom")) return;

  const plotSelectors = [
    "figure:has(img)",
    "figure:has(canvas)",
    "figure:has(svg)",
    "figure.benchmark-chart",
    "figure.probability-chart",
    "figure.importance-panel",
    "figure.validation-panel"
  ];
  const plots = Array.from(document.querySelectorAll(plotSelectors.join(",")));
  if (!plots.length) return;

  plots.forEach((plot) => {
    const caption = plot.querySelector("figcaption")?.textContent.trim();
    const imageLabel = plot.querySelector("img")?.alt;
    plot.classList.add("plot-enhanced");
    plot.tabIndex = 0;
    plot.setAttribute("role", "button");
    plot.setAttribute("aria-label", `Enlarge ${caption || imageLabel || "plot"}`);
  });

  const viewer = document.createElement("div");
  viewer.className = "shared-plot-viewer";
  viewer.id = "sharedPlotViewer";
  viewer.setAttribute("role", "dialog");
  viewer.setAttribute("aria-modal", "true");
  viewer.setAttribute("aria-hidden", "true");
  viewer.setAttribute("aria-label", "Enlarged plot");
  viewer.innerHTML = `
    <div class="shared-plot-viewer__shell">
      <div class="shared-plot-viewer__toolbar">
        <div class="shared-plot-viewer__meta">
          <strong id="sharedPlotTitle">Plot viewer</strong>
          <span id="sharedPlotCounter"></span>
        </div>
        <div class="shared-plot-viewer__actions">
          <button id="sharedPlotPrev" type="button" aria-label="Previous plot">Previous</button>
          <button id="sharedPlotClear" class="is-active" type="button">Clear view</button>
          <div class="shared-plot-viewer__levels" role="group" aria-label="Plot zoom level">
            <button type="button" data-shared-zoom="1">1&times;</button>
            <button type="button" data-shared-zoom="1.25">1.25&times;</button>
            <button type="button" data-shared-zoom="1.5">1.5&times;</button>
            <button type="button" data-shared-zoom="2">2&times;</button>
          </div>
          <span class="shared-plot-viewer__level" id="sharedPlotLevel" aria-live="polite">Clear</span>
          <button id="sharedPlotNext" type="button" aria-label="Next plot">Next</button>
          <button class="shared-plot-viewer__close" id="sharedPlotClose" type="button">Close</button>
        </div>
      </div>
      <div class="shared-plot-viewer__viewport" id="sharedPlotViewport">
        <div class="shared-plot-viewer__canvas" id="sharedPlotCanvas"></div>
      </div>
      <div class="shared-plot-viewer__hint">Choose 1&times;, 1.25&times;, 1.5&times;, or 2&times; &middot; Clear view resets &middot; drag to pan &middot; Left/Right to browse &middot; Esc to close</div>
    </div>`;
  document.body.append(viewer);

  const canvas = viewer.querySelector("#sharedPlotCanvas");
  const viewport = viewer.querySelector("#sharedPlotViewport");
  const title = viewer.querySelector("#sharedPlotTitle");
  const counter = viewer.querySelector("#sharedPlotCounter");
  const level = viewer.querySelector("#sharedPlotLevel");
  const closeButton = viewer.querySelector("#sharedPlotClose");
  const previousButton = viewer.querySelector("#sharedPlotPrev");
  const nextButton = viewer.querySelector("#sharedPlotNext");
  const clearButton = viewer.querySelector("#sharedPlotClear");
  const zoomButtons = Array.from(viewer.querySelectorAll("[data-shared-zoom]"));
  const zoomLevels = [1, 1.25, 1.5, 2];

  let gallery = [];
  let galleryIndex = 0;
  let returnTarget = null;
  let zoomScale = 1;
  let zoomMode = "clear";
  let panX = 0;
  let panY = 0;
  let dragging = false;
  let pointerX = 0;
  let pointerY = 0;

  function updateTransform() {
    canvas.style.transform = `translate(-50%, -50%) translate(${panX}px, ${panY}px) scale(${zoomScale})`;
    level.textContent = zoomMode === "clear" ? "Clear" : `${zoomScale}\u00d7`;
    clearButton.classList.toggle("is-active", zoomMode === "clear");
    zoomButtons.forEach((button) => {
      button.classList.toggle("is-active", zoomMode === "level" && Number(button.dataset.sharedZoom) === zoomScale);
    });
  }

  function clearZoom() {
    zoomScale = 1;
    zoomMode = "clear";
    panX = 0;
    panY = 0;
    updateTransform();
  }

  function setZoom(value) {
    zoomScale = value;
    zoomMode = "level";
    if (value === 1) {
      panX = 0;
      panY = 0;
    }
    updateTransform();
  }

  function stepZoom(direction) {
    const currentIndex = zoomLevels.findIndex((value) => value >= zoomScale);
    const nextIndex = Math.max(0, Math.min(zoomLevels.length - 1, currentIndex + direction));
    setZoom(zoomLevels[nextIndex]);
  }

  function getPlotTitle(plot) {
    return plot.dataset.title ||
      plot.querySelector("figcaption strong")?.textContent.trim() ||
      plot.querySelector("figcaption")?.textContent.trim() ||
      plot.querySelector("img")?.alt ||
      "Plot viewer";
  }

  function renderPlot() {
    const source = gallery[galleryIndex];
    const image = source.querySelector(":scope > img:only-of-type");
    const clone = image ? image.cloneNode(true) : source.cloneNode(true);
    clone.removeAttribute("tabindex");
    clone.removeAttribute("role");
    clone.removeAttribute("aria-label");
    clone.classList.remove("plot-enhanced", "hover-lift");
    canvas.replaceChildren(clone);
    title.textContent = getPlotTitle(source);
    counter.textContent = `${galleryIndex + 1} of ${gallery.length} on this slide`;
    previousButton.disabled = gallery.length < 2;
    nextButton.disabled = gallery.length < 2;
    clearZoom();
  }

  function openPlot(source) {
    returnTarget = source;
    const slide = source.closest(".slide") || document;
    gallery = Array.from(slide.querySelectorAll(".plot-enhanced"));
    galleryIndex = Math.max(0, gallery.indexOf(source));
    renderPlot();
    document.body.classList.add("plot-zoom-open");
    viewer.classList.add("is-open");
    viewer.setAttribute("aria-hidden", "false");
    closeButton.focus();
  }

  function closePlot() {
    viewer.classList.remove("is-open");
    viewer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("plot-zoom-open");
    canvas.replaceChildren();
    returnTarget?.focus();
  }

  function browse(direction) {
    galleryIndex = (galleryIndex + direction + gallery.length) % gallery.length;
    renderPlot();
  }

  plots.forEach((plot) => {
    plot.addEventListener("click", () => openPlot(plot));
    plot.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openPlot(plot);
      }
    });
  });

  closeButton.addEventListener("click", closePlot);
  previousButton.addEventListener("click", () => browse(-1));
  nextButton.addEventListener("click", () => browse(1));
  clearButton.addEventListener("click", clearZoom);
  zoomButtons.forEach((button) => button.addEventListener("click", () => setZoom(Number(button.dataset.sharedZoom))));
  viewport.addEventListener("wheel", (event) => {
    event.preventDefault();
    stepZoom(event.deltaY < 0 ? 1 : -1);
  }, { passive: false });
  viewport.addEventListener("dblclick", () => zoomMode === "clear" ? setZoom(2) : clearZoom());
  viewport.addEventListener("pointerdown", (event) => {
    if (zoomScale <= 1) return;
    dragging = true;
    pointerX = event.clientX;
    pointerY = event.clientY;
    viewport.classList.add("is-dragging");
    viewport.setPointerCapture(event.pointerId);
  });
  viewport.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    panX += event.clientX - pointerX;
    panY += event.clientY - pointerY;
    pointerX = event.clientX;
    pointerY = event.clientY;
    updateTransform();
  });
  const stopDragging = () => {
    dragging = false;
    viewport.classList.remove("is-dragging");
  };
  viewport.addEventListener("pointerup", stopDragging);
  viewport.addEventListener("pointercancel", stopDragging);
  viewer.addEventListener("click", (event) => {
    if (event.target === viewer) closePlot();
  });

  window.addEventListener("keydown", (event) => {
    if (!viewer.classList.contains("is-open")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (event.key === "Escape") closePlot();
    else if (event.key === "ArrowLeft") browse(-1);
    else if (event.key === "ArrowRight") browse(1);
    else if (event.key === "+" || event.key === "=") stepZoom(1);
    else if (event.key === "-") stepZoom(-1);
    else if (event.key === "0") clearZoom();
  }, true);
})();
