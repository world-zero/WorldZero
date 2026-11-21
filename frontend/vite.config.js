var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
var __spreadArray = (this && this.__spreadArray) || function (to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
        if (ar || !(i in from)) {
            if (!ar) ar = Array.prototype.slice.call(from, 0, i);
            ar[i] = from[i];
        }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
};
/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
// The flow is lazy, so its chunk is found one waterfall level behind the entry's own preloads (#3593).
// A guest on `/`, or anyone on `/start`, fetches it with the entry. Script-injected, not static tags: the byte
// budget parses index.html, and it must run before the blocking stylesheet.
function preloadWelcomeFlow() {
    return {
        name: 'preload-welcome-flow',
        transformIndexHtml: {
            order: 'post',
            handler: function (html, ctx) {
                var _a, _b, _c;
                var bundle = ctx.bundle;
                if (!bundle)
                    return html;
                var files = new Set((_a = ctx.chunk) === null || _a === void 0 ? void 0 : _a.imports);
                var css = new Set();
                var walk = function (name) {
                    var _a;
                    var chunk = bundle[name];
                    if (!chunk || chunk.type !== 'chunk' || files.has(name))
                        return;
                    files.add(name);
                    chunk.imports.forEach(walk);
                    (_a = chunk.viteMetadata) === null || _a === void 0 ? void 0 : _a.importedCss.forEach(function (c) { return css.add(c); });
                };
                // Copy first: it is one tiny file the flow cannot mount without, and it queues behind the rest.
                for (var _i = 0, _d = [/locales[/\\]en[/\\](onboarding|forms|admin)\.json$/, /pages[/\\]Onboarding\.tsx$/]; _i < _d.length; _i++) {
                    var re = _d[_i];
                    for (var _e = 0, _f = Object.values(bundle); _e < _f.length; _e++) {
                        var chunk = _f[_e];
                        if (chunk.type === 'chunk' && re.test((_b = chunk.facadeModuleId) !== null && _b !== void 0 ? _b : ''))
                            walk(chunk.fileName);
                    }
                }
                (_c = ctx.chunk) === null || _c === void 0 ? void 0 : _c.imports.forEach(function (i) { return files.delete(i); });
                if (!files.size)
                    return html;
                var script = "(function(){var p=location.pathname,h;try{h=localStorage.getItem('wz_session_hint')==='true'}catch(e){}if(p!=='/start'&&(p!=='/'||h))return;var m=".concat(JSON.stringify(__spreadArray([], files, true)), ",c=").concat(JSON.stringify(__spreadArray([], css, true)), ";function a(r,u){var l=document.createElement('link');l.rel=r;l.href='/'+u;l.crossOrigin='';if(r!=='modulepreload')l.as='style';document.head.appendChild(l)}m.forEach(function(u){a('modulepreload',u)});c.forEach(function(u){a('preload',u)})})()");
                return { html: html, tags: [{ tag: 'script', children: script, injectTo: 'head-prepend' }] };
            },
        },
    };
}
// public/sw.js can't read the i18n bundle, so the build bakes src/locales/en/push.json and the faction names into the copied worker.
function bakePushStrings() {
    var outDir = 'dist';
    return {
        name: 'bake-push-strings',
        apply: 'build',
        configResolved: function (c) {
            outDir = c.build.outDir;
        },
        closeBundle: function () {
            var strings = JSON.parse(readFileSync('src/locales/en/push.json', 'utf8'));
            var names = JSON.parse(readFileSync('src/locales/en/factions.json', 'utf8')).names;
            if (!names || !Object.keys(names).length)
                throw new Error('factions.json lost its names, so the letter push has no faction to say');
            var file = join(outDir, 'sw.js');
            var js = readFileSync(file, 'utf8');
            if (!js.includes('const PUSH_STRINGS = null'))
                throw new Error('sw.js lost its PUSH_STRINGS placeholder');
            writeFileSync(file, js.replace('const PUSH_STRINGS = null', function () { return "const PUSH_STRINGS = ".concat(JSON.stringify(__assign(__assign({}, strings), { factions: names }))); }));
        },
    };
}
/**
 * DO NOT strip console output (esbuild `drop`, terser `drop_console`): Singularity's
 * Era 1 perk IS console output (#1869, `src/components/TheArray.tsx`), and losing it
 * fails nothing visibly. `theArray.test.ts` asserts the absence here.
 */
export default defineConfig({
    plugins: [react(), preloadWelcomeFlow(), bakePushStrings()],
    server: {
        port: 5173,
        strictPort: true,
    },
    build: {
        /**
         * Never inline a font (#2038): a data: URI defeats `unicode-range` lazy fetching
         * (#1977) and the immutable /assets cache, and bloats render-blocking CSS.
         */
        assetsInlineLimit: function (filePath) { return (filePath.endsWith('.woff2') ? false : undefined); },
        /**
         * Explicit React vendor chunk (#2843): Rollup's automatic split stopped firing
         * with React 19, folding the runtime into the entry chunk so returning visitors
         * re-fetched it every deploy. Match on the package directory: a bare `react`
         * test also catches react-i18next/react-router. `scheduler` is react-dom-only.
         * Ratchet: `src/__tests__/reactVendorChunk.test.ts`.
         */
        rollupOptions: {
            output: {
                manualChunks: function (id) {
                    if (/node_modules[/\\](react|react-dom|scheduler)[/\\]/.test(id))
                        return 'react-vendor';
                    return undefined;
                },
            },
        },
    },
    // renderToStaticMarkup needs no DOM, so the default 'node' environment is fine; a file that needs effects opts into jsdom itself.
    test: {
        include: ['src/**/*.test.{ts,tsx}'],
        // Resolves code-split archetypes (see src/test/preloadArchetypes.ts).
        setupFiles: ['./src/test/preloadArchetypes.ts'],
        // Cold CI transform of ~195 archetype modules overruns the 10s default.
        hookTimeout: 60000,
    },
});
