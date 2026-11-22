/**
 * The Google Photos pick as a state machine (#559).
 *
 *   start -> [authorization_needed -> authorize popup -> start again; ready
 *             carries on in the same popup, else "authorized": press again]
 *         -> ready -> picker popup -> poll until picked | expired
 *         -> ingest.   Cancel at any point after a session exists -> DELETE.
 *
 * Every side effect comes in through `PickDeps`, so the flow is pinned in
 * `__tests__/googlePhotosPick.test.ts` without a browser. The real consent ->
 * pick -> ingest path cannot run in CI; the owner checks it on dev.
 */
import {
  GOOGLE_PHOTOS_AUTHORIZE_URL,
  abandonPhotosSession,
  ingestPhotosSession,
  pollPhotosSession,
  startPhotosSession,
  type MediaUploadResult,
  type PickerSessionStart,
} from "../../api/googlePhotos";
import { API_BASE_URL } from "../../api/baseUrl";

export interface PickPopup {
  readonly closed: boolean;
  navigate(url: string): void;
  close(): void;
}

export interface PickDeps {
  /** Must be called synchronously from the click, or browsers block it. */
  openPopup(): PickPopup | null;
  start(): Promise<PickerSessionStart>;
  poll(sessionId: string): Promise<"waiting" | "picked" | "expired">;
  abandon(sessionId: string): Promise<void>;
  ingest(sessionId: string): Promise<MediaUploadResult[]>;
  /** Resolves when the authorize popup reports back, or is closed. */
  awaitAuthorization(
    popup: PickPopup,
    signal: AbortSignal,
  ): Promise<"ok" | "failed" | "closed">;
  sleep(ms: number, signal: AbortSignal): Promise<void>;
}

export type PickOutcome =
  | { kind: "ingested"; results: MediaUploadResult[] }
  | { kind: "expired" }
  | { kind: "abandoned" }
  | { kind: "authFailed" }
  | { kind: "authorized" }
  | { kind: "popupBlocked" };

// `popup.closed` lies under Cross-Origin-Opener-Policy, so it never ends a pick.
const NEEDS_AUTH = { status: "authorization_needed" } as PickerSessionStart;

export async function runPick(
  deps: PickDeps,
  signal: AbortSignal,
): Promise<PickOutcome> {
  const popup = deps.openPopup();
  if (!popup) return { kind: "popupBlocked" };

  let sessionId: string | null = null;
  try {
    let started = await deps.start();
    if (started.status === "authorization_needed") {
      popup.navigate(GOOGLE_PHOTOS_AUTHORIZE_URL);
      const auth = await deps.awaitAuthorization(popup, signal);
      if (auth === "closed" || signal.aborted) {
        popup.close();
        return { kind: "abandoned" };
      }
      if (auth === "failed") {
        popup.close();
        return { kind: "authFailed" };
      }
      // The callback page leaves its window open, so this one press can go on
      // to the picker; a second window.open would have no click left.
      started = popup.closed ? NEEDS_AUTH : await deps.start();
      if (started.status === "authorization_needed") {
        popup.close();
        return { kind: "authorized" };
      }
    }
    if (started.status !== "ready" || !started.session_id || !started.picker_uri) {
      popup.close();
      return { kind: "authFailed" };
    }
    sessionId = started.session_id;
    popup.navigate(started.picker_uri);

    const interval = (started.poll_interval_seconds ?? 2) * 1000;
    for (;;) {
      await deps.sleep(interval, signal);
      if (signal.aborted) break;
      const state = await deps.poll(sessionId);
      if (state === "expired") return { kind: "expired" };
      if (state === "picked") {
        const id = sessionId;
        sessionId = null; // ingest drops the session, success or not
        return { kind: "ingested", results: await deps.ingest(id) };
      }
    }
    popup.close();
    return { kind: "abandoned" };
  } finally {
    // Anything still holding a session (abandon, or a throw) lets Google's go.
    if (sessionId) await deps.abandon(sessionId).catch(() => undefined);
  }
}

// ---- Real deps -------------------------------------------------------------

const POPUP_FEATURES = "popup,width=520,height=720";

function wrap(win: Window): PickPopup {
  return {
    get closed() {
      return win.closed;
    },
    navigate: (url) => {
      win.location.href = url;
    },
    close: () => win.close(),
  };
}

export const realDeps: Omit<PickDeps, "ingest"> = {
  openPopup: () => {
    // Not `noopener`: the callback page hands back through `window.opener`.
    const win = window.open("about:blank", "wz-google-photos", POPUP_FEATURES);
    return win ? wrap(win) : null;
  },
  start: startPhotosSession,
  poll: pollPhotosSession,
  abandon: abandonPhotosSession,
  awaitAuthorization: (popup, signal) =>
    new Promise((resolve) => {
      const done = (result: "ok" | "failed" | "closed") => {
        window.removeEventListener("message", onMessage);
        clearInterval(timer);
        signal.removeEventListener("abort", onAbort);
        resolve(result);
      };
      const onMessage = (event: MessageEvent) => {
        // The callback page is served by the API, so only its origin counts.
        if (event.origin !== new URL(API_BASE_URL, window.location.href).origin) return;
        const data = event.data as { source?: string; status?: string } | null;
        if (data?.source !== "wz-google-photos") return;
        done(data.status === "ok" ? "ok" : "failed");
      };
      const onAbort = () => done("closed");
      window.addEventListener("message", onMessage);
      signal.addEventListener("abort", onAbort);
      // Grace lets a message already in flight win over a closed window.
      const timer = setInterval(() => {
        if (!popup.closed) return;
        clearInterval(timer);
        setTimeout(() => done("closed"), 500);
      }, 500);
    }),
  sleep: (ms, signal) =>
    new Promise((resolve) => {
      const timer = setTimeout(resolve, ms);
      signal.addEventListener("abort", () => {
        clearTimeout(timer);
        resolve();
      });
    }),
};

export const depsForPraxis = (praxisId: number): PickDeps => ({
  ...realDeps,
  ingest: (sessionId) => ingestPhotosSession(praxisId, sessionId),
});
