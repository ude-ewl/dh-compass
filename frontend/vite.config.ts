import { readFileSync } from "node:fs";

import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

interface FrontendPackage {
  version?: string;
}

const packageJson = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf8"),
) as FrontendPackage;
const applicationVersion =
  process.env.VITE_DH_COMPASS_VERSION ?? packageJson.version ?? "unknown";

function projectVersion(): string {
  const pyproject = readFileSync(
    new URL("../pyproject.toml", import.meta.url),
    "utf8",
  );
  const match = pyproject.match(
    /^\[project\][\s\S]*?^version\s*=\s*["']([^"']+)["']/m,
  );
  if (!match?.[1]) {
    throw new Error(
      "Unable to read the DH-COMPASS version from pyproject.toml.",
    );
  }
  return match[1];
}

// The API version must have the same source as the Python package. Keeping it
// separate from the frontend package version prevents a normal Python release
// from producing assets that the server rejects at startup.
const apiVersion = process.env.VITE_DH_COMPASS_API_VERSION ?? projectVersion();

/**
 * Emit the small compatibility contract inspected by the packaged API.
 *
 * The API version can be set explicitly when a frontend is built outside this
 * repository. By default it is read from the Python distribution metadata, so
 * a normal local build remains compatible after a package version bump.
 */
function compatibilityManifestPlugin(): Plugin {
  return {
    name: "dh-compass-compatibility-manifest",
    apply: "build",
    generateBundle() {
      const manifest = {
        application: "dh-compass",
        frontend_version: applicationVersion,
        api_version: apiVersion,
        api_prefix: "/api/v1",
      };
      this.emitFile({
        type: "asset",
        fileName: "dh-compass-frontend.json",
        source: `${JSON.stringify(manifest, null, 2)}\n`,
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), compatibilityManifestPlugin()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
