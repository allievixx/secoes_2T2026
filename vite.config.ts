import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

/**
 * dashboard-config.json fica na raiz (é referenciado pela documentação e pelo pipeline) e é buscado
 * em runtime, então precisa ser copiado para dist/. Se dataUrl for relativo, o arquivo de dados vai junto.
 */
function copyRuntimeConfig(): Plugin {
  return {
    name: "copy-runtime-config",
    generateBundle() {
      const configPath = resolve(__dirname, "dashboard-config.json");
      const source = readFileSync(configPath, "utf8");
      this.emitFile({ type: "asset", fileName: "dashboard-config.json", source });
      const { dataUrl } = JSON.parse(source) as { dataUrl?: string };
      if (dataUrl && !/^https?:/i.test(dataUrl)) {
        const fileName = dataUrl.replace(/^\.\//, "");
        this.emitFile({ type: "asset", fileName, source: readFileSync(resolve(__dirname, fileName)) });
      }
    },
  };
}

export default defineConfig({
  // Caminhos relativos: o GitHub Pages serve o site em /secoes_2T2026/, não na raiz do domínio.
  base: "./",
  publicDir: false,
  plugins: [copyRuntimeConfig()],
  build: { outDir: "dist" },
  server: { port: 8080 },
});
