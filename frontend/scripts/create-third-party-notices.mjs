import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lock = JSON.parse(
  fs.readFileSync(path.join(root, "package-lock.json"), "utf8"),
);
const sections = [
  "Third-party runtime dependency notices for DH-COMPASS\n" +
    "Conservative inventory of non-dev npm lock entries; review against shipped chunks.\n" +
    "Project code licensing is tracked separately.\n",
];
const missing = [];
for (const [relative, item] of Object.entries(lock.packages).sort()) {
  if (!relative || item.dev) continue;
  const directory = path.resolve(root, relative);
  if (!directory.startsWith(root + path.sep))
    throw new Error("Invalid package path");
  if (!fs.existsSync(directory)) {
    if (!item.optional) missing.push(relative);
    continue;
  }
  const texts = fs
    .readdirSync(directory)
    .filter((name) => /^(licen[sc]e|copying|notice)([.-]|$)/i.test(name));
  const files = texts.filter((name) =>
    fs.statSync(path.join(directory, name)).isFile(),
  );
  if (!files.length && fs.existsSync(path.join(directory, "README.md"))) {
    const readme = fs.readFileSync(path.join(directory, "README.md"), "utf8");
    if (readme.includes("Permission is hereby granted"))
      files.push("README.md");
  }
  if (!files.length) {
    missing.push(relative);
    sections.push(
      `UNRESOLVED LICENSE TEXT: ${relative}. Release approval required.\n`,
    );
  }
  sections.push(
    `\n${relative} ${item.version} (${item.license ?? "license unverified"})\n`,
  );
  for (const name of files) {
    sections.push(
      `${name}\n${fs.readFileSync(path.join(directory, name), "utf8")}\n`,
    );
  }
}
fs.mkdirSync(path.join(root, "dist"), { recursive: true });
fs.writeFileSync(
  path.join(root, "dist", "THIRD_PARTY_LICENSES.txt"),
  sections.join("\n"),
);
if (missing.length) {
  console.error("Missing complete runtime license texts:", missing.join(", "));
  process.exitCode = 1;
} else {
  console.log(
    "Complete runtime license texts written to dist/THIRD_PARTY_LICENSES.txt",
  );
}
