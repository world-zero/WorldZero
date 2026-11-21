// @vitest-environment jsdom
/**
 * The owner-only admin roster (#3258, #3847). Seams: the owner gate in the
 * markup, and the checkbox toggle against a mocked `api/admin` (PUT, then a
 * rollback when it fails). The server-side 403 is pinned in test_admin_roster.py.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, it, expect, vi } from "vitest";
import "../../../i18n";

const api = vi.hoisted(() => ({
  getAdmins: vi.fn(async () => [
    { username: "molly", display_name: "Molly", is_owner: true, suspended: false, permissions: [] },
    { username: "wren", display_name: "Wren", is_owner: false, suspended: true, permissions: ["edit_copy"] },
  ]),
  setAdminPermission: vi.fn(async () => undefined),
  revokeAdmin: vi.fn(),
}));
vi.mock("../../../api/admin", () => api);

import AdminRosterSection from "../AdminRosterSection";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AdminRosterSection", () => {
  it("renders for the owner", () => {
    const html = renderToStaticMarkup(<AdminRosterSection isOwner={true} />);
    expect(html).toContain("Admins");
    expect(html).toContain("grant admin");
  });

  it("renders nothing for a plain admin", () => {
    expect(renderToStaticMarkup(<AdminRosterSection isOwner={false} />)).toBe("");
  });

  it("shows the owner as every permission and marks a suspended holder", async () => {
    render(<AdminRosterSection isOwner={true} />);
    expect(await screen.findByText("Owner — every permission")).toBeTruthy();
    expect(screen.getByText("suspended")).toBeTruthy();
    expect(screen.getAllByRole("checkbox")).toHaveLength(9);
  });

  it("ticks a box through the PUT", async () => {
    render(<AdminRosterSection isOwner={true} />);
    const box = (await screen.findByLabelText("Roll the era")) as HTMLInputElement;
    fireEvent.click(box);
    expect(box.checked).toBe(true);
    expect(api.setAdminPermission).toHaveBeenCalledWith("wren", "roll_era", true);
  });

  it("rolls the box back when the PUT fails", async () => {
    api.setAdminPermission.mockRejectedValueOnce(new Error("nope"));
    render(<AdminRosterSection isOwner={true} />);
    const box = (await screen.findByLabelText("Edit site copy")) as HTMLInputElement;
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    expect(api.setAdminPermission).toHaveBeenCalledWith("wren", "edit_copy", false);
    await waitFor(() => expect(box.checked).toBe(true));
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});
