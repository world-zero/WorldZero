/**
 * Long form everywhere (#2598, #4197). Positive, closed vocabulary: a scan for
 * `pts`/`lvl` misses `L1` and `Lv 8`, so assert the long word is present instead.
 */
import { describe, it, expect } from "vitest";

const catalogs = import.meta.glob("../en/*.json", {
  eager: true,
  import: "default",
}) as Record<string, Record<string, unknown>>;

// The players-table columns and the praxis score stamp (#2598 §B0).
const EXEMPT = new Set([
  "common:leaderboard.roster.colLevel",
  "common:leaderboard.roster.colPoints",
  "praxis:card.stamp.pointsShort",
]);

function leaves(node: unknown, path: string): [string, string][] {
  if (typeof node === "string") return [[path, node]];
  if (node && typeof node === "object")
    return Object.entries(node).flatMap(([k, v]) =>
      leaves(v, path ? `${path}.${k}` : k),
    );
  return [];
}

const all = Object.entries(catalogs).flatMap(([file, json]) =>
  leaves(json, "").map(
    ([k, v]) =>
      [`${file.split("/").pop()!.replace(".json", "")}:${k}`, v] as const,
  ),
);

describe("counts of levels and points use the long form", () => {
  it('puts "Level" right before every {{level}}', () => {
    const bad = all.filter(
      ([k, v]) =>
        !EXEMPT.has(k) &&
        /\{\{level\}\}(?!\+)/.test(v) &&
        /(?<!\blevel )\{\{level\}\}(?!\+)/i.test(v),
    );
    expect(bad).toEqual([]);
  });

  it('puts "point" or "points" right after every {{points}}', () => {
    const bad = all.filter(
      ([k, v]) =>
        !EXEMPT.has(k) &&
        /\{\{points\}\}(?! (bonus )?points?\b)/i.test(v),
    );
    expect(bad).toEqual([]);
  });
});
