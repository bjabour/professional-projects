import { access, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

const inputArg = argument("--input");
if (!inputArg) throw new Error("Usage: node export_standalone.mjs --input <index.html> [--output <report.html>]");

const input = path.resolve(inputArg);
const baseDir = path.dirname(input);
const output = path.resolve(argument("--output") || path.join(baseDir, "project-presentation-standalone.html"));
let html = await readFile(input, "utf8");

const localPath = (value) => !/^(?:data:|https?:|#|mailto:|javascript:)/i.test(value);
const mime = (file) => ({
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
}[path.extname(file).toLowerCase()] || "application/octet-stream");

for (const match of [...html.matchAll(/<link\s+rel=["']stylesheet["']\s+href=["']([^"']+)["']\s*\/?>/gi)]) {
  const href = match[1];
  if (!localPath(href)) continue;
  const file = path.resolve(baseDir, href);
  await access(file);
  const css = await readFile(file, "utf8");
  html = html.replace(match[0], `<style>\n${css}\n</style>`);
}

for (const match of [...html.matchAll(/<script\s+src=["']([^"']+)["']\s*><\/script>/gi)]) {
  const src = match[1];
  if (!localPath(src)) continue;
  const file = path.resolve(baseDir, src);
  await access(file);
  const js = await readFile(file, "utf8");
  html = html.replace(match[0], `<script>\n${js}\n</script>`);
}

const sources = [...new Set([...html.matchAll(/<img\b[^>]*\bsrc=["']([^"']+)["']/gi)].map((match) => match[1]))];
for (const src of sources) {
  if (!localPath(src)) continue;
  const file = path.resolve(baseDir, src);
  await access(file);
  const bytes = await readFile(file);
  html = html.replaceAll(src, `data:${mime(file)};base64,${bytes.toString("base64")}`);
}

await writeFile(output, html, "utf8");
console.log(output);
