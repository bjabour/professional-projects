import { access, readFile } from "node:fs/promises";
import path from "node:path";

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

const inputArg = argument("--input");
if (!inputArg) throw new Error("Usage: node validate_report.mjs --input <index.html>");
const input = path.resolve(inputArg);
const baseDir = path.dirname(input);
const html = await readFile(input, "utf8");
const errors = [];
const warnings = [];

const slides = [...html.matchAll(/<section\b[^>]*class=["'][^"']*\bslide\b[^"']*["'][^>]*>/gi)];
const nav = [...html.matchAll(/class=["'][^"']*\bnav-link\b[^"']*["']/gi)];
if (slides.length < 6 || slides.length > 8) warnings.push(`Expected 6-8 slides; found ${slides.length}.`);
if (slides.length !== nav.length) errors.push(`Slide count ${slides.length} does not match navigation count ${nav.length}.`);
if (/\{\{[^}]+\}\}/.test(html)) errors.push("Unresolved template placeholders remain.");
if (!/<title>[^<]+<\/title>/i.test(html)) errors.push("Missing document title.");
if (!/id=["']slide-analytics["']/i.test(html)) warnings.push("Missing Analytics slide.");
if (!/id=["']slide-decision["']/i.test(html)) warnings.push("Missing Decision slide.");
const analyticsIndex = html.search(/id=["']slide-analytics["']/i);
const decisionIndex = html.search(/id=["']slide-decision["']/i);
if (analyticsIndex >= 0 && decisionIndex >= 0 && analyticsIndex > decisionIndex) errors.push("Analytics must appear before Decision.");

const localPath = (value) => !/^(?:data:|https?:|#|mailto:|javascript:)/i.test(value);
const sources = [...new Set([...html.matchAll(/<img\b[^>]*\bsrc=["']([^"']+)["']/gi)].map((match) => match[1]))];
for (const src of sources) {
  if (!localPath(src)) continue;
  try { await access(path.resolve(baseDir, src)); }
  catch { errors.push(`Missing local image: ${src}`); }
}

const toggleTargets = [...html.matchAll(/data-plot-target=["']([^"']+)["']/gi)].map((match) => match[1]);
for (const target of toggleTargets) {
  if (!new RegExp(`id=["']${target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']`, "i").test(html)) errors.push(`Missing plot panel for toggle target: ${target}`);
}
const plotSlices = [...html.matchAll(/<canvas\b[^>]*class=["'][^"']*\bplot-slice\b[^"']*["'][^>]*>/gi)].map((match) => match[0]);
const readAttribute = (tag, name) => tag.match(new RegExp(`${name}=["']([^"']+)["']`, "i"))?.[1];
for (const slice of plotSlices) {
  const sourceId = readAttribute(slice, "data-source");
  const crop = readAttribute(slice, "data-crop");
  const title = readAttribute(slice, "data-title");
  if (!sourceId) errors.push("Plot slice is missing data-source.");
  else if (!new RegExp(`id=["']${sourceId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']`, "i").test(html)) errors.push(`Plot slice source does not exist: ${sourceId}`);
  const cropValues = crop?.split(",").map(Number) || [];
  if (cropValues.length !== 4 || cropValues.some((value) => !Number.isFinite(value)) || cropValues[2] <= 0 || cropValues[3] <= 0) errors.push(`Invalid plot slice crop: ${crop || "missing"}`);
  if (!title) errors.push("Plot slice is missing data-title.");
}
const zoomables = [...html.matchAll(/class=["'][^"']*\bzoomable(?:-chart)?\b[^"']*["']/gi)];
if (zoomables.length) {
  for (const id of ["plotZoom", "plotZoomViewport", "plotZoomClear", "plotZoom1", "plotZoom125", "plotZoom150", "plotZoom200", "plotZoomPrev", "plotZoomNext", "plotZoomClose"]) {
    if (!new RegExp(`id=["']${id}["']`, "i").test(html)) errors.push(`Zoomable plots require viewer control: ${id}`);
  }
}

console.log(`slides=${slides.length} nav=${nav.length} images=${sources.length} toggles=${toggleTargets.length} zoomables=${zoomables.length} plotSlices=${plotSlices.length}`);
for (const warning of warnings) console.log(`warning: ${warning}`);
for (const error of errors) console.error(`error: ${error}`);
if (errors.length) process.exit(1);
