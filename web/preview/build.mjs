// Builds a one-page preview of the site (preview/dist/index.html) that works without a server:
// React and Motion load from a CDN, the components and CSS are inlined. Uses the built-in CAT sample.
import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const shim = (f) => join(here, "shims", f);

const js = await build({
  entryPoints: [join(here, "entry.tsx")],
  bundle: true,
  write: false,
  minify: true,
  format: "iife",
  jsx: "transform",
  jsxFactory: "React.createElement",
  jsxFragment: "React.Fragment",
  inject: [shim("react-global.js")],
  tsconfigRaw: { compilerOptions: { jsx: "react" } },
  define: { "process.env.NEXT_PUBLIC_API_URL": '""' },
  alias: {
    react: shim("react.js"),
    "react-dom/client": shim("react-dom-client.js"),
    "motion/react": shim("motion.js"),
    "@": root,
  },
});

const css = execFileSync(join(root, "node_modules/.bin/tailwindcss"), ["-i", join(root, "app/globals.css"), "--minify"], {
  cwd: root,
}).toString();

const html = `<title>SEC Filing Terminal</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;1,8..60,400&display=swap">
<style>${css}</style>
<div id="root"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/framer-motion@13.5.1/dist/framer-motion.js"></script>
<script>${js.outputFiles[0].text.replace(/<\/script/gi, "<\\/script")}</script>
`;
mkdirSync(join(here, "dist"), { recursive: true });
writeFileSync(join(here, "dist/index.html"), html);
console.log(`preview/dist/index.html written (${(html.length / 1024).toFixed(0)} KB)`);
