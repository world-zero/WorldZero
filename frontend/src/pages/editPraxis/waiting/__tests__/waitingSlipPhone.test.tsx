import { renderToStaticMarkup } from "react-dom/server";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import "../../../../i18n";
import type { PraxisOut } from "../../../../api/praxis";
import type { TaskOut } from "../../../../api/tasks";
import { collabCopy } from "../../../../components/collab/collabCopy";
import { anEditPraxisState } from "../../../../test/fixtures";
import { DEFAULT_COMPOSER_DRESS } from "../../archetypes/DefaultEditPraxis";
import { TaskSlip } from "../../archetypes/shared";
import PraxisWaitingSurface from "../PraxisWaitingSurface";

vi.mock("../../../../hooks/useFormFactor", () => ({ useFormFactor: () => "mobile" }));

const task = { id: 5, title: "Walk", description: "Full recap text", level_required: 1 } as unknown as TaskOut;
const praxis = {
  id: 1, task_id: 5, task_title: "Walk", task_point_value: 12, task_faction_slug: "coven",
  type: "collab", status: "in_progress", moderation_status: "visible", created_by_id: 1,
  duel_id: null, members: [], invites: [], media_items: [], applied_metatasks: [],
  score: 12, metatask_points: 0, display_multiplier: 1, points_from_votes: 0,
} as unknown as PraxisOut;

describe("task slip on a phone (#3957)", () => {
  it("waiting surface shows eyebrow and stamp without a tap", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PraxisWaitingSurface
          {...anEditPraxisState({ praxis, task, currentCharacterId: 1 })}
          dress={DEFAULT_COMPOSER_DRESS}
        />
      </MemoryRouter>,
    );
    expect(html).toContain(collabCopy("coven", "awaitingTaskLabel"));
    expect(html).toContain("composer-stamp");
    expect(html).not.toContain("aria-expanded");
  });

  it("a composer slip still collapses", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter><TaskSlip praxis={praxis} task={task} /></MemoryRouter>,
    );
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("composer-stamp");
  });
});
