/** #3111: each blank line in the S.N.I.D.E. blurb starts a new paragraph on its tile. */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";

import i18n from "../../../i18n";

import SnideSelectCard from "../SnideSelectCard";

describe("the S.N.I.D.E. select tile", () => {
  it("draws one paragraph per blank-line block of its blurb", () => {
    const blocks = i18n.t("feed:factionSelect.snide.blurb").split(/\n\s*\n/).filter((b) => b.trim());
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <SnideSelectCard state="locked" members={3} onVisit={() => {}} />
      </MemoryRouter>,
    );
    const pitch = markup.split('data-select-slot="pitch"')[1].split("</div>")[0];
    expect(pitch.match(/<p[ >]/g)).toHaveLength(blocks.length);
  });
});
