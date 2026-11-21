import { describe, it, expect } from "vitest";
import i18n from "../../../i18n";
import type { DuelDetailOut, DuelSideOut } from "../../../api/duel";
import { castClockLine } from "../shared";

const DAY = 86_400_000;
const t = i18n.getFixedT("en", "praxis");
const side = (name: string, is_submitted: boolean) =>
  ({ display_name: name, is_submitted }) as DuelSideOut;
const duel = (startedAgoDays: number | null, now: number) =>
  ({
    cast_clock_started_at:
      startedAgoDays == null
        ? null
        : new Date(now - startedAgoDays * DAY).toISOString(),
  }) as DuelDetailOut;
const now = Date.UTC(2026, 10, 21);

describe("castClockLine", () => {
  it("tells the side that cast how many days the other has left", () => {
    const line = castClockLine(
      duel(2, now),
      side("Ada", true),
      side("Rax", false),
      7,
      t,
      now,
    );
    expect(line).toBe("Rax has 5 days to submit, or forfeits.");
  });

  it("tells the side that has not cast how much time is left", () => {
    const line = castClockLine(
      duel(2, now),
      side("Ada", false),
      side("Rax", true),
      7,
      t,
      now,
    );
    expect(line).toBe(
      "Rax has submitted. You have 5 days left, or you forfeit.",
    );
  });

  it('says "1 day" singular on the last day', () => {
    const line = castClockLine(
      duel(6.5, now),
      side("Ada", true),
      side("Rax", false),
      7,
      t,
      now,
    );
    expect(line).toBe("Rax has 1 day to submit, or forfeits.");
  });

  it("is silent once the clock has run out, for both sides", () => {
    for (const ago of [7, 9]) {
      expect(
        castClockLine(
          duel(ago, now),
          side("Ada", true),
          side("Rax", false),
          7,
          t,
          now,
        ),
      ).toBeNull();
      expect(
        castClockLine(
          duel(ago, now),
          side("Ada", false),
          side("Rax", true),
          7,
          t,
          now,
        ),
      ).toBeNull();
    }
  });

  it("is silent with no clock or no window", () => {
    const [me, foe] = [side("Ada", true), side("Rax", false)];
    expect(castClockLine(duel(null, now), me, foe, 7, t, now)).toBeNull();
    expect(castClockLine(duel(1, now), me, foe, null, t, now)).toBeNull();
    expect(castClockLine(duel(1, now), me, foe, undefined, t, now)).toBeNull();
  });
});
