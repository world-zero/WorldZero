import { ErrorCode, extractErrorCode } from '../../utils/errors'

/** Did accepting fail because the praxis was already submitted? Matches the code, never the prose. */
export function isInvitePraxisSubmitted(err: unknown): boolean {
  return extractErrorCode(err) === ErrorCode.invitePraxisSubmitted
}
