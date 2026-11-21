import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { getAdmins, revokeAdmin, setAdminPermission } from "../../api/admin";
import type { AdminRow, Permission } from "../../api/admin";
import { extractError } from "../../utils/errors";
import AdminConfirm from "./AdminConfirm";

/**
 * The owner-only admin roster (#3258). The server says who the owner is
 * (`is_owner` on `/auth/me`); this component never guesses from a username, and
 * every route behind it is `require_owner` regardless of what renders here.
 */
const PERMISSIONS: readonly Permission[] = [
  "handle_reports",
  "ban_suspend",
  "review_proposals",
  "manage_tasks",
  "delete_import_tasks",
  "read_messages",
  "edit_copy",
  "small_world",
  "roll_era",
];

export default function AdminRosterSection({ isOwner }: { isOwner: boolean }) {
  return isOwner ? <AdminRoster /> : null;
}

function AdminRoster() {
  const { t } = useTranslation("admin");
  const [admins, setAdmins] = useState<AdminRow[] | null>(null);
  const [username, setUsername] = useState("");
  const [firstPermission, setFirstPermission] = useState<Permission>(PERMISSIONS[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<AdminRow | null>(null);

  const refresh = () =>
    getAdmins()
      .then(setAdmins)
      .catch((err) => setError(extractError(err, t("admins.loadError"))));

  useEffect(() => {
    void refresh();
  }, []);

  const handleGrant = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await setAdminPermission(username.trim(), firstPermission, true);
      setUsername("");
      await refresh();
    } catch (err) {
      setError(extractError(err, t("admins.grantError")));
    } finally {
      setBusy(false);
    }
  };

  // Flip only the one box on rollback, so a second toggle in flight is not undone.
  const flip = (name: string, permission: Permission, on: boolean) =>
    setAdmins((rows) =>
      rows &&
      rows.map((row) =>
        row.username !== name
          ? row
          : {
              ...row,
              permissions: on
                ? [...row.permissions, permission]
                : row.permissions.filter((p) => p !== permission),
            },
      ),
    );

  const handleToggle = async (row: AdminRow, permission: Permission, on: boolean) => {
    setError(null);
    flip(row.username, permission, on);
    try {
      await setAdminPermission(row.username, permission, on);
    } catch (err) {
      flip(row.username, permission, !on);
      setError(extractError(err, t("admins.toggleError")));
    }
  };

  const handleRevoke = async (row: AdminRow) => {
    setBusy(true);
    setError(null);
    try {
      await revokeAdmin(row.username);
      setRevoking(null);
      await refresh();
    } catch (err) {
      setError(extractError(err, t("admins.revokeError")));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card px-4 py-3 mb-6">
      <h2 className="label-heading">{t("admins.heading")}</h2>
      <p className="font-body content-text text-muted mb-3">{t("admins.lead")}</p>
      {error && !revoking && (
        <p role="alert" className="font-body content-text danger-text mb-3">
          {error}
        </p>
      )}
      {admins === null ? (
        <p className="font-body content-text text-muted">{t("admins.loading")}</p>
      ) : admins.length === 0 ? (
        <p className="font-body content-text text-muted">{t("admins.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2 mb-3">
          {admins.map((row) =>
            revoking?.username === row.username ? (
              <li key={row.username}>
                <AdminConfirm
                  heading={t("admins.revokeConfirm.heading")}
                  lead={t("admins.revokeConfirm.lead", {
                    name: row.display_name,
                    username: row.username,
                  })}
                  confirmLabel={t("admins.revokeConfirm.submit")}
                  busyLabel={t("admins.revokeConfirm.working")}
                  cancelLabel={t("admins.revokeConfirm.cancel")}
                  busy={busy}
                  error={error}
                  onConfirm={() => void handleRevoke(row)}
                  onCancel={() => {
                    setRevoking(null);
                    setError(null);
                  }}
                />
              </li>
            ) : (
              <li key={row.username} className="flex flex-col gap-2 border-b border-border pb-2">
                <div className="flex items-center gap-3">
                  <span className="flex-1 font-body text-sm">
                    <span className="font-bold">{row.display_name}</span>
                    <span className="text-xs text-muted ml-2">@{row.username}</span>
                    {row.suspended && (
                      <span className="text-xs danger-text ml-2">{t("admins.suspendedBadge")}</span>
                    )}
                  </span>
                  {!row.is_owner && (
                    <button
                      type="button"
                      onClick={() => {
                        setError(null);
                        setRevoking(row);
                      }}
                      className="btn-outline text-xs shrink-0"
                      style={{
                        borderColor: "var(--color-danger-ring)",
                        color: "var(--color-danger)",
                      }}
                    >
                      {t("admins.revoke")}
                    </button>
                  )}
                </div>
                {row.is_owner ? (
                  <p className="font-body text-xs text-muted">{t("admins.ownerAll")}</p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-3 gap-y-1">
                    {PERMISSIONS.map((permission) => (
                      <label key={permission} className="flex items-center gap-2 font-body text-xs">
                        <input
                          type="checkbox"
                          checked={row.permissions.includes(permission)}
                          onChange={(event) =>
                            void handleToggle(row, permission, event.target.checked)
                          }
                        />
                        {t(`admins.permissions.${permission}`)}
                      </label>
                    ))}
                  </div>
                )}
              </li>
            ),
          )}
        </ul>
      )}
      <form onSubmit={(event) => void handleGrant(event)} className="flex gap-2 flex-wrap">
        <input
          type="text"
          aria-label={t("admins.grantLabel")}
          placeholder={t("admins.grantPlaceholder")}
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          className="border-2 border-border bg-card px-3 py-2 font-body content-text focus:outline-hidden focus:border-ink flex-1"
        />
        <select
          aria-label={t("admins.grantPermissionLabel")}
          value={firstPermission}
          onChange={(event) => setFirstPermission(event.target.value as Permission)}
          className="border-2 border-border bg-card px-3 py-2 font-body content-text focus:outline-hidden focus:border-ink"
        >
          {PERMISSIONS.map((permission) => (
            <option key={permission} value={permission}>
              {t(`admins.permissions.${permission}`)}
            </option>
          ))}
        </select>
        <button type="submit" disabled={busy || !username.trim()} className="btn-primary text-xs control-off">
          {busy ? t("admins.granting") : t("admins.grantSubmit")}
        </button>
      </form>
    </section>
  );
}
