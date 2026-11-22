/**
 * Challenge (duel) and Invite (collab) on a player's profile (#3772). Each opens
 * a sheet of the viewer's in-progress praxes; picking one lands in its composer
 * with the player staged for a one-tap send (`useEditPraxis` reads `?mode`/`?with=<id>`).
 * The send, and its errors, stay the composer's.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listPraxes, type PraxisCardOut } from "../../api/praxis";
import BottomSheet from "../../components/ui/BottomSheet";
import { factionFill } from "../../utils/factions";
import { BUTTON_BASE } from "./AddRelationshipButtons";

type Mode = "duel" | "collab";

/** A duel side is a solo praxis (ADR-0011) that is not already in a duel. */
export function eligiblePraxes(praxes: PraxisCardOut[], mode: Mode) {
  return praxes.filter(
    (p) =>
      p.status === "in_progress" &&
      p.duel_id == null &&
      (mode === "duel" ? p.type === "solo" : p.type !== "duel"),
  );
}

export default function ChallengeInviteButtons({
  viewerCharacterId,
  targetCharacterId,
  blocked,
  viewerLevel,
  duelLevelRequired,
  collabLevelRequired,
  targetDisplayName,
  factionSlug,
}: {
  viewerCharacterId: number;
  targetCharacterId: number;
  /** The viewer blocked them. */
  blocked: boolean;
  viewerLevel: number;
  /** `null` until the game config loads, or when the era never lists it: hidden. */
  duelLevelRequired: number | null;
  collabLevelRequired: number | null;
  targetDisplayName: string;
  factionSlug: string | null | undefined;
}) {
  const { t } = useTranslation("common");
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode | null>(null);
  const [praxes, setPraxes] = useState<PraxisCardOut[] | null>(null);

  const open = (next: Mode) => {
    setMode(next);
    setPraxes(null);
    listPraxes({ character_id: viewerCharacterId, status: "in_progress" })
      .then(setPraxes)
      .catch(() => setPraxes([]));
  };

  const can = (required: number | null) =>
    required != null && viewerLevel >= required;
  const buttons: [Mode, number | null, string][] = [
    ["duel", duelLevelRequired, t("relationships.challenge")],
    ["collab", collabLevelRequired, t("relationships.invite")],
  ];
  if (blocked || viewerCharacterId === targetCharacterId) return null;
  const list = mode && praxes ? eligiblePraxes(praxes, mode) : null;
  const title = mode
    ? t(
        mode === "duel"
          ? "relationships.pickChallenge"
          : "relationships.pickInvite",
        { name: targetDisplayName },
      )
    : "";

  return (
    <>
      {buttons.map(([m, required, label]) =>
        can(required) ? (
          <button
            key={m}
            onClick={() => open(m)}
            className="control-off"
            style={{ ...BUTTON_BASE, ...factionFill(factionSlug, "pill") }}
          >
            {label}
          </button>
        ) : null,
      )}
      {mode && (
        <BottomSheet
          label={title}
          scrimLabel={t("relationships.pickClose")}
          onClose={() => setMode(null)}
        >
          <p className="font-body mb-3">
            {title}
          </p>
          {list?.length === 0 && (
            <p className="font-body">
              {t(
                mode === "duel"
                  ? "relationships.pickNoneChallenge"
                  : "relationships.pickNone",
              )}{" "}
              <Link to="/tasks" className="underline">
                {t("relationships.pickNoneLink")}
              </Link>
            </p>
          )}
          {list?.map((p) => (
            <button
              key={p.id}
              className="font-body block w-full cursor-pointer border-0 border-b border-solid border-[var(--color-border)] bg-transparent py-2 text-left"
              onClick={() =>
                navigate(
                  `/praxis/${p.id}/edit?${new URLSearchParams({ mode, with: String(targetCharacterId) })}`,
                )
              }
            >
              {p.title || p.task_title}
            </button>
          ))}
        </BottomSheet>
      )}
    </>
  );
}
