/** @vitest-environment jsdom */
/**
 * The Coven masthead's twinkles stay out of the middle (#1983): a star beside
 * the "c" read as "tozy". Stars sit at a fixed fraction of the band while
 * the centred wordmark is fixed-size, so narrowing pushes central stars further
 * under it, and y doesn't map to "above the lettering". Horizontal exclusion is
 * the only rule that holds at every width.
 *
 * At 375px: band = 375 − 2×12 − 2×16 = 319px; wordmark = 30 + 8 + 3.832em×22
 * ("cozy coven", grenze-gotisch wght 400) + 10×0.02×22 = 126.7px → 39.7%
 * centred → 144.8…335.2 of 480. [105, 375] reaches the wordmark only at a 281px
 * viewport. If the wordmark grows, widen the exclusion.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import "../../../../i18n";
import { anEditPraxisState } from "../../../../test/fixtures";
import type { PraxisOut } from "../../../../api/praxis";
import type { TaskOut } from "../../../../api/tasks";

const mocks = vi.hoisted(() => ({
  formFactor: "desktop" as "mobile" | "desktop",
}));
vi.mock("../../../../hooks/useFormFactor", () => ({
  useFormFactor: () => mocks.formFactor,
}));

import CovenEditPraxis from "../CovenEditPraxis";

/** The wordmark is centred, so the exclusion is symmetric about 240 of 480. */
const CLEAR_FROM = 105;
const CLEAR_TO = 375;

const task = {
  id: 7,
  title: "Bless the work",
  description: "Do a small honest thing.",
  point_value: 20,
  level_required: 1,
  status: "active",
  task_type: "standard",
  primary_faction_slug: "coven",
  allowed_modes: ["solo", "collab", "duel"],
} as unknown as TaskOut;

const praxis = {
  id: 55,
  task_id: 7,
  task_title: "Bless the work",
  task_faction_slug: "coven",
  type: "solo",
  status: "in_progress",
  title: "I helped a stranger",
  body_text: "Caught the papers.",
  moderation_status: "visible",
  duel_id: null,
  created_by_id: 3,
  members: [],
  invites: [],
  media_items: [],
} as unknown as PraxisOut;

const state = anEditPraxisState({
  praxis,
  task,
  // Spelled: `praxis.title` is `string | null`, the draft title is not.
  title: "I helped a stranger",
  body: "Caught the papers.",
  autoSubmitDays: 10,
  duelChipVisible: true,
});

/** Bounding box of an `M x y l dx dy …z` path (the only shape starPath emits). */
function pathBox(d: string): { minX: number; maxX: number; minY: number; maxY: number } {
  const n = d.match(/-?[\d.]+/g)!.map(Number);
  let x = n[0];
  let y = n[1];
  const xs = [x];
  const ys = [y];
  for (let i = 2; i < n.length; i += 2) {
    x += n[i];
    y += n[i + 1];
    xs.push(x);
    ys.push(y);
  }
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

/** Each star is its own svg, left = x/480 of the band, width = 2× its reach in viewBox units. */
function twinkleSpans(formFactor: "mobile" | "desktop"): [number, number][] {
  mocks.formFactor = formFactor;
  const markup = renderToStaticMarkup(
    <MemoryRouter>
      <CovenEditPraxis state={state} />
    </MemoryRouter>,
  );
  const doc = new DOMParser().parseFromString(markup, "text/html");
  return Array.from(doc.querySelectorAll("svg"))
    .filter((svg) => svg.querySelector(":scope > path") && svg.getAttribute("viewBox")?.startsWith("-"))
    .map((svg) => {
      const w = Number(svg.getAttribute("width"));
      expect(svg.getAttribute("height"), "a twinkle must be as tall as it is wide").toBe(String(w));
      const [vx, vy, vw, vh] = svg.getAttribute("viewBox")!.split(" ").map(Number);
      const box = pathBox(svg.querySelector("path")!.getAttribute("d")!);
      const tol = 1e-6;
      expect(
        box.minX >= vx - tol && box.maxX <= vx + vw + tol && box.minY >= vy - tol && box.maxY <= vy + vh + tol,
        `star path ${JSON.stringify(box)} is clipped by its viewBox ${vx} ${vy} ${vw} ${vh}`,
      ).toBe(true);
      expect(Math.abs(box.maxY - box.minY - (box.maxX - box.minX)), "star must be as tall as wide").toBeLessThan(tol);
      const left = Number(/left:\s*([\d.]+)%/.exec(svg.getAttribute("style")!)![1]);
      const x = (left / 100) * 480;
      return [x - w / 2, x + w / 2] as [number, number];
    });
}

describe("Coven masthead twinkles (#1983)", () => {
  it.each(["desktop", "mobile"] as const)(
    "keeps every star clear of the wordmark's centre on %s",
    (formFactor) => {
      const spans = twinkleSpans(formFactor);
      expect(spans.length).toBeGreaterThan(0);
      for (const [min, max] of spans) {
        expect(
          max <= CLEAR_FROM || min >= CLEAR_TO,
          `star spanning ${min}…${max} enters the wordmark's clear band ` +
            `[${CLEAR_FROM}, ${CLEAR_TO}] of the 480-unit viewBox`,
        ).toBe(true);
      }
    },
  );

  it("keeps the ornament at full strength — six twinkles, not fewer", () => {
    // Thinning the field would pass the clear-band check for the wrong reason.
    expect(twinkleSpans("desktop")).toHaveLength(6);
  });
});
