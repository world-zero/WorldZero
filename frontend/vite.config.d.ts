/**
 * DO NOT strip console output (esbuild `drop`, terser `drop_console`): Singularity's
 * Era 1 perk IS console output (#1869, `src/components/TheArray.tsx`), and losing it
 * fails nothing visibly. `theArray.test.ts` asserts the absence here.
 */
declare const _default: import("vite").UserConfig;
export default _default;
