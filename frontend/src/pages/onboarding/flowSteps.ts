/** Title, beats, `contract` (or `declined`), then `signin` (skipped with a session), then `character` and `arrival` for a player with none; `returning` is the sign-in view for a header sign-in. */
export type Step = 'title' | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 'contract' | 'declined' | 'signin' | 'returning' | 'character' | 'arrival'

export const BEAT_COUNT = 7

export interface Flow {
  step: Step
  /** Every step the player left, oldest first: Back pops it, so it retraces the real path. */
  history: Step[]
}

/** A failed OAuth (`signIn` with the resume mark) reopens the sign-in card with the contract behind it; a held click survives for the retry. */
export const initialFlow = (resumed: boolean, signIn = false): Flow =>
  resumed && signIn ? { step: 'signin', history: ['contract'] } : { step: resumed ? 'contract' : signIn ? 'returning' : 'title', history: [] }

export const isBeat = (s: Step): s is 1 | 2 | 3 | 4 | 5 | 6 | 7 => typeof s === 'number'

const moveTo = (f: Flow, step: Step): Flow => ({ step, history: [...f.history, f.step] })

export function next(f: Flow): Flow {
  if (f.step === 'title') return moveTo(f, 1)
  if (isBeat(f.step)) return moveTo(f, f.step === BEAT_COUNT ? 'contract' : ((f.step + 1) as Step))
  if (f.step === 'contract') return moveTo(f, 'signin')
  return f
}

export const decline = (f: Flow): Flow => moveTo(f, 'declined')

export const skip = (f: Flow): Flow => moveTo(f, 'contract')

export const toSignIn = (f: Flow): Flow => moveTo(f, 'returning')

export const toCharacter = (f: Flow, hasCharacter = false): Flow => (hasCharacter ? f : moveTo(f, 'character'))

/** The contract is passed, not visited: Back from `character` must not land on a card that bounces forward again. A no-op off the contract, so two hand-offs cannot stack. */
export const passContract = (f: Flow): Flow => (f.step === 'contract' ? { step: 'character', history: f.history } : f)

export const toArrival = (f: Flow): Flow => moveTo(f, 'arrival')

/** With a character, Back steps over `character`: the form must not be reachable a second time. */
export function back(f: Flow, hasCharacter = false): Flow {
  const history = [...f.history]
  let prev = history.pop()
  while (hasCharacter && prev === 'character') prev = history.pop()
  return prev === undefined ? f : { step: prev, history }
}

/** What the flow draws. Every state has an exit (see `STATE_EXIT`); `onboardingState` is the only place that decides. */
export type OnboardingState =
  | 'TITLE'
  | `BEAT_${1 | 2 | 3 | 4 | 5 | 6 | 7}`
  | 'STEPS_LOADING'
  | 'STEPS_FAILED'
  | 'CONTRACT_LOADING'
  | 'RECORDING_TERMS'
  | 'CONTRACT_ON_FILE'
  | 'CONTRACT'
  | 'SIGN_IN'
  | 'RETURNING'
  | 'DECLINED'
  | 'CHARACTER'
  | 'CHARACTER_BANNED'
  | 'ARRIVAL'

/** The way out of each state: a control, or the effect/redirect that moves a state with no control. A new state fails to compile until it names one. */
export const STATE_EXIT: Record<OnboardingState, string> = {
  TITLE: 'start',
  BEAT_1: 'next',
  BEAT_2: 'next',
  BEAT_3: 'next',
  BEAT_4: 'next',
  BEAT_5: 'next',
  BEAT_6: 'next',
  BEAT_7: 'next',
  STEPS_LOADING: 'chunk load resolves or fails',
  STEPS_FAILED: 'retry',
  CONTRACT_LOADING: 'auth settles',
  RECORDING_TERMS: 'the write settles and clears recording',
  CONTRACT_ON_FILE: 'auto hand-off',
  CONTRACT: 'accept or decline',
  SIGN_IN: 'sign in or back',
  RETURNING: 'sign in or restart',
  DECLINED: 'reconsider',
  CHARACTER: 'create or back',
  CHARACTER_BANNED: 'the layout gate sends the account to the notice',
  ARRIVAL: 'continue',
}

export interface StateInputs {
  step: Step
  stepsLoaded: boolean
  stepsFailed: boolean
  authLoading: boolean
  recording: boolean
  signedIn: boolean
  termsOnFile: boolean
  creationBanned: boolean
}

export function onboardingState(i: StateInputs): OnboardingState {
  const { step } = i
  if (step === 'title') return 'TITLE'
  if (isBeat(step)) return `BEAT_${step}`
  if (!i.stepsLoaded) return i.stepsFailed ? 'STEPS_FAILED' : 'STEPS_LOADING'
  switch (step) {
    case 'contract':
      if (i.authLoading) return 'CONTRACT_LOADING'
      if (i.recording) return 'RECORDING_TERMS'
      return i.signedIn && i.termsOnFile ? 'CONTRACT_ON_FILE' : 'CONTRACT'
    case 'signin':
      return 'SIGN_IN'
    case 'returning':
      return 'RETURNING'
    case 'declined':
      return 'DECLINED'
    case 'character':
      return i.creationBanned ? 'CHARACTER_BANNED' : 'CHARACTER'
    case 'arrival':
      return 'ARRIVAL'
  }
}
