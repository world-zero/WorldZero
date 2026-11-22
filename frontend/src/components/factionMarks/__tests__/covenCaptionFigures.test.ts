import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";
import { CAPTION } from "../covenSlip";

const SRC = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..", "..");
const read = (rel: string) => readFileSync(join(SRC, rel), "utf-8");

it("Coven caption voice leads with the digits face, ahead of Caveat", () => {
  const stack = String(CAPTION.fontFamily).split(",").map((f) => f.trim());
  expect(stack[0]).toBe('"Caveat Figures"');
  expect(stack[1]).toBe("var(--font-faction-script)");
});

it("fonts.faction.css declares Caveat Figures for the digits only", () => {
  const face = read("fonts.faction.css").match(/@font-face\s*{[^}]*Caveat Figures[^}]*}/);
  expect(face?.[0]).toMatch(/unicode-range:\s*U\+0030-0039/);
});

it.each([
  "components/taskCard/CovenTaskCard.tsx",
  "components/feed/CovenFeedFrame.tsx",
  "components/comments/voices/CovenComment.tsx",
  "pages/taskDetail/archetypes/CovenTaskDetail.tsx",
])("%s sets its caption in CAPTION_FONT", (file) => {
  expect(read(file)).toMatch(/fontFamily:\s*CAPTION_FONT/);
});
