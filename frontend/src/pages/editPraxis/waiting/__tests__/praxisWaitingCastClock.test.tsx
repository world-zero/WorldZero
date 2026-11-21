/** The duel waiting surface names the days the rival has left (#4005). */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import "../../../../i18n";
import type { GameConfigOut } from "../../../../api/gameConfig";
import type { DuelDetailOut } from "../../../../api/duel";
import type { PraxisOut } from "../../../../api/praxis";
import { anEditPraxisState } from "../../../../test/fixtures";
import { DEFAULT_COMPOSER_DRESS } from "../../archetypes/DefaultEditPraxis";

const config = { factions: [], duel_cast_lapse_days: 7 } as unknown as GameConfigOut;
vi.mock("../../../../hooks/useGameConfig", () => ({ useGameConfig: () => config }));

const { default: PraxisWaitingSurface } = await import("../PraxisWaitingSurface");

const NOW = Date.UTC(2026, 10, 21);
const side = (id: number, name: string, is_submitted: boolean) => ({
  praxis_id: id, character_id: id, display_name: name, faction_slug: "coven",
  avatar_url: "", points_from_votes: 0, is_submitted, nudged_at: null,
  nudge_again_at: null, win_multiplier: 1, loss_multiplier: 1, tie_multiplier: 1, rival_bonus: 0,
});

function html(startedDaysAgo: number) {
  const duel = {
    id: 7, task_id: 5, status: "active", forfeited_by_character_id: null,
    cast_clock_started_at: new Date(NOW - startedDaysAgo * 86_400_000).toISOString(),
    challenger: side(1, "Wren", true),
    opponent: side(2, "Rax", false),
    winner_character_id: null, challenger_final_points: null, opponent_final_points: null,
  } as unknown as DuelDetailOut;
  const praxis = {
    id: 1, task_id: 5, task_title: "T", task_point_value: 12, task_faction_slug: "coven",
    type: "solo", status: "submitted", duel_id: 7, submitted_at: "2026-11-01T00:00:00Z",
    members: [{ id: 1, praxis_id: 1, character_id: 1, character_display_name: "Wren",
      character_avatar_url: "", has_approved: true, is_done: false,
      joined_at: "2026-11-01T00:00:00Z", nudged_at: null, approved_at: null, nudge_again_at: null }],
    invites: [], media_items: [], applied_metatasks: [],
  } as unknown as PraxisOut;
  return renderToStaticMarkup(
    <MemoryRouter>
      <PraxisWaitingSurface
        {...anEditPraxisState({ praxis, duel, currentCharacterId: 1, title: "x", body: "y" })}
        now={NOW}
        dress={DEFAULT_COMPOSER_DRESS}
      />
    </MemoryRouter>,
  );
}

describe("duel waiting surface cast clock", () => {
  it("shows the days Rax has left, not the full window", () => {
    expect(html(2)).toContain("Rax has 5 days to submit, or forfeits.");
  });

  it("says nothing once the clock has run out", () => {
    expect(html(8)).not.toContain("to submit, or forfeits");
  });
});
