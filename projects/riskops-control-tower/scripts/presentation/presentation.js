const slides = Array.from(document.querySelectorAll(".slide"));
const navButtons = Array.from(document.querySelectorAll(".nav-link"));
const progressFill = document.querySelector("#progressFill");
const slideCounter = document.querySelector("#slideCounter");
const prevBtn = document.querySelector("#prevBtn");
const nextBtn = document.querySelector("#nextBtn");
const query = new URLSearchParams(window.location.search);
if (query.get("static") === "1") document.documentElement.classList.add("static-render");
let current = 0;

function showSlide(index) {
  current = Math.max(0, Math.min(index, slides.length - 1));
  slides.forEach((slide, i) => { const active = i === current; slide.classList.toggle("active", active); slide.setAttribute("aria-hidden", active ? "false" : "true"); });
  navButtons.forEach((button, i) => { const active = i === current; button.classList.toggle("active", active); button.setAttribute("aria-current", active ? "page" : "false"); });
  progressFill.style.width = `${((current + 1) / slides.length) * 100}%`;
  slideCounter.textContent = `${current + 1} / ${slides.length}`;
  prevBtn.disabled = current === 0;
  nextBtn.disabled = current === slides.length - 1;
}

navButtons.forEach((button) => button.addEventListener("click", () => showSlide(Number(button.dataset.slide))));
prevBtn.addEventListener("click", () => showSlide(current - 1));
nextBtn.addEventListener("click", () => showSlide(current + 1));
window.addEventListener("keydown", (event) => {
  if (document.body.classList.contains("plot-zoom-open")) return;
  if (event.key === "ArrowRight" || event.key === "PageDown") showSlide(current + 1);
  if (event.key === "ArrowLeft" || event.key === "PageUp") showSlide(current - 1);
  if (event.key === "Home") showSlide(0);
  if (event.key === "End") showSlide(slides.length - 1);
});

document.querySelectorAll("[data-plot-group]").forEach((group) => {
  const toggles = Array.from(group.querySelectorAll(".plot-toggle"));
  const panels = Array.from(group.querySelectorAll(".plot-panel"));
  toggles.forEach((toggle) => toggle.addEventListener("click", () => {
    toggles.forEach((item) => item.classList.toggle("is-active", item === toggle));
    panels.forEach((panel) => panel.classList.toggle("is-active", panel.id === toggle.dataset.plotTarget));
  }));
});

function initializePlotSlices() {
  document.querySelectorAll("canvas.plot-slice").forEach((canvas) => {
    const source = document.getElementById(canvas.dataset.source);
    const crop = (canvas.dataset.crop || "").split(",").map(Number);
    if (!source || crop.length !== 4 || crop.some((value) => !Number.isFinite(value))) return;
    const [sourceX, sourceY, sourceWidth, sourceHeight] = crop;
    const drawSlice = () => {
      canvas.width = sourceWidth;
      canvas.height = sourceHeight;
      canvas.getContext("2d").drawImage(source, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, sourceWidth, sourceHeight);
      canvas.dataset.ready = "true";
    };
    if (source.complete && source.naturalWidth) drawSlice();
    else source.addEventListener("load", drawSlice, { once: true });
  });
}

initializePlotSlices();

const plotZoom = document.querySelector("#plotZoom");
const plotZoomContent = document.querySelector("#plotZoomContent");
const plotZoomViewport = document.querySelector("#plotZoomViewport");
const plotZoomClose = document.querySelector("#plotZoomClose");
const plotZoomTitle = document.querySelector("#plotZoomTitle");
const plotZoomCounter = document.querySelector("#plotZoomCounter");
const plotZoomLevel = document.querySelector("#plotZoomLevel");
const plotZoomPrev = document.querySelector("#plotZoomPrev");
const plotZoomNext = document.querySelector("#plotZoomNext");
const plotZoomClear = document.querySelector("#plotZoomClear");
const plotZoomButtons = Array.from(document.querySelectorAll("[data-zoom]"));
const zoomLevels = [1, 1.25, 1.5, 2];
let zoomReturnTarget = null;
let zoomGallery = [];
let zoomIndex = 0;
let zoomScale = 1;
let zoomMode = "clear";
let zoomPanX = 0;
let zoomPanY = 0;
let zoomDragging = false;
let zoomPointerX = 0;
let zoomPointerY = 0;

function updateZoomTransform() {
  plotZoomContent.style.transform = `translate(-50%, -50%) translate(${zoomPanX}px, ${zoomPanY}px) scale(${zoomScale})`;
  plotZoomLevel.textContent = zoomMode === "clear" ? "Clear" : `${zoomScale}×`;
  plotZoomClear.classList.toggle("is-active", zoomMode === "clear");
  plotZoomButtons.forEach((button) => button.classList.toggle("is-active", zoomMode === "level" && Number(button.dataset.zoom) === zoomScale));
}

function clearPlotZoom() {
  zoomMode = "clear";
  zoomScale = 1;
  zoomPanX = 0;
  zoomPanY = 0;
  updateZoomTransform();
}

function setPlotZoom(nextScale) {
  zoomMode = "level";
  zoomScale = zoomLevels.includes(nextScale) ? nextScale : 1;
  zoomPanX = 0;
  zoomPanY = 0;
  updateZoomTransform();
}

function stepPlotZoom(direction) {
  const currentIndex = zoomMode === "clear" ? 0 : zoomLevels.indexOf(zoomScale);
  const nextIndex = Math.max(0, Math.min(zoomLevels.length - 1, currentIndex + direction));
  if (zoomMode === "clear" && direction < 0) return;
  setPlotZoom(zoomLevels[nextIndex]);
}

function cloneZoomSource(source) {
  if (source instanceof HTMLCanvasElement) {
    const clone = document.createElement("canvas");
    clone.width = source.width;
    clone.height = source.height;
    clone.getContext("2d").drawImage(source, 0, 0);
    return clone;
  }
  return source.cloneNode(true);
}

function renderZoomSource() {
  const source = zoomGallery[zoomIndex];
  plotZoomContent.replaceChildren();
  const clone = cloneZoomSource(source);
  clone.removeAttribute("tabindex");
  clone.classList.remove("zoomable", "zoomable-chart");
  plotZoomContent.append(clone);
  plotZoomTitle.textContent = source.dataset.title || source.getAttribute("aria-label") || source.getAttribute("alt") || source.textContent.trim() || "Plot viewer";
  plotZoomCounter.textContent = `${zoomIndex + 1} of ${zoomGallery.length} on this slide`;
  plotZoomPrev.disabled = zoomGallery.length < 2;
  plotZoomNext.disabled = zoomGallery.length < 2;
  clearPlotZoom();
}

function openPlotZoom(source) {
  zoomReturnTarget = source;
  const slide = source.closest(".slide") || document;
  zoomGallery = Array.from(slide.querySelectorAll(".zoomable, .zoomable-chart"));
  zoomIndex = Math.max(0, zoomGallery.indexOf(source));
  renderZoomSource();
  document.body.classList.add("plot-zoom-open");
  plotZoom.classList.add("is-open");
  plotZoom.setAttribute("aria-hidden", "false");
  plotZoomClose.focus();
}

function closePlotZoom() {
  plotZoom.classList.remove("is-open");
  plotZoom.setAttribute("aria-hidden", "true");
  document.body.classList.remove("plot-zoom-open");
  plotZoomContent.replaceChildren();
  zoomReturnTarget?.focus();
}

function browseZoomGallery(direction) {
  if (zoomGallery.length < 2) return;
  zoomIndex = (zoomIndex + direction + zoomGallery.length) % zoomGallery.length;
  renderZoomSource();
}

document.querySelectorAll(".zoomable, .zoomable-chart").forEach((source) => {
  source.addEventListener("click", () => openPlotZoom(source));
  source.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openPlotZoom(source); }
  });
});
plotZoomClose.addEventListener("click", closePlotZoom);
plotZoomPrev.addEventListener("click", () => browseZoomGallery(-1));
plotZoomNext.addEventListener("click", () => browseZoomGallery(1));
plotZoomClear.addEventListener("click", clearPlotZoom);
plotZoomButtons.forEach((button) => button.addEventListener("click", () => setPlotZoom(Number(button.dataset.zoom))));
plotZoomViewport.addEventListener("wheel", (event) => { event.preventDefault(); stepPlotZoom(event.deltaY < 0 ? 1 : -1); }, { passive: false });
plotZoomViewport.addEventListener("dblclick", () => { if (zoomMode === "clear") setPlotZoom(2); else clearPlotZoom(); });
plotZoomViewport.addEventListener("pointerdown", (event) => {
  if (zoomScale <= 1) return;
  zoomDragging = true;
  zoomPointerX = event.clientX;
  zoomPointerY = event.clientY;
  plotZoomViewport.classList.add("is-dragging");
  plotZoomViewport.setPointerCapture(event.pointerId);
});
plotZoomViewport.addEventListener("pointermove", (event) => {
  if (!zoomDragging) return;
  zoomPanX += event.clientX - zoomPointerX;
  zoomPanY += event.clientY - zoomPointerY;
  zoomPointerX = event.clientX;
  zoomPointerY = event.clientY;
  updateZoomTransform();
});
function stopZoomDrag() { zoomDragging = false; plotZoomViewport.classList.remove("is-dragging"); }
plotZoomViewport.addEventListener("pointerup", stopZoomDrag);
plotZoomViewport.addEventListener("pointercancel", stopZoomDrag);
plotZoom.addEventListener("click", (event) => { if (event.target === plotZoom) closePlotZoom(); });
window.addEventListener("keydown", (event) => {
  if (!plotZoom.classList.contains("is-open")) return;
  let handled = true;
  if (event.key === "Escape") closePlotZoom();
  else if (event.key === "ArrowLeft") browseZoomGallery(-1);
  else if (event.key === "ArrowRight") browseZoomGallery(1);
  else if (event.key === "+" || event.key === "=" || event.key === "]") stepPlotZoom(1);
  else if (event.key === "-" || event.key === "[") stepPlotZoom(-1);
  else if (event.key === "0" || event.key.toLowerCase() === "c") clearPlotZoom();
  else handled = false;
  if (handled) event.preventDefault();
});

const requested = Number(query.get("slide"));
showSlide(Number.isInteger(requested) ? requested : 0);
