import { expect, it } from "vitest";
import { CAPTION } from "../covenSlip";

it("Coven caption voice leads with the digits face, ahead of Caveat", () => {
  const stack = String(CAPTION.fontFamily).split(",").map((f) => f.trim());
  expect(stack[0]).toBe('"Caveat Figures"');
  expect(stack[1]).toBe("var(--font-faction-script)");
});
