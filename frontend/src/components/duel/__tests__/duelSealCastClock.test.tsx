/** The active seal body carries the cast-clock line (#4005). */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it, expect, vi } from "vitest";
import "../../../i18n";
import type { GameConfigOut } from "../../../api/gameConfig";
import type { DuelDetailOut, DuelSideOut } from "../../../api/duel";

const config = {
  factions: [],
  duel_cast_lapse_days: 7,
} as unknown as GameConfigOut;
vi.mock("../../../hooks/useGameConfig", () => ({
  useGameConfig: () => config,
}));

const { DefaultDuelSealConfirm } = await import("../DuelSealConfirm");

const side = (id: number, name: string, is_submitted: boolean): DuelSideOut =>
  ({
    character_id: id,
    praxis_id: id,
    display_name: name,
    faction_slug: "wow",
    is_submitted,
  }) as DuelSideOut;

describe("active duel seal copy", () => {
  it("appends the days the rival has left once the clock runs", () => {
    const duel = {
      id: 5,
      status: "active",
      cast_clock_started_at: new Date(
        Date.now() - 2 * 86_400_000,
      ).toISOString(),
      challenger: side(1, "Ada", false),
      opponent: side(2, "Rax", true),
    } as unknown as DuelDetailOut;
    const html = renderToStaticMarkup(
      <DefaultDuelSealConfirm
        duel={duel}
        viewerCharacterId={1}
        taskPointValue={60}
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(html).toContain(
      "Rax has submitted. You have 5 days left, or you forfeit.",
    );
  });
});
