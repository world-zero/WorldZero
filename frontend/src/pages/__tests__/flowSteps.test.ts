import { describe, it, expect } from 'vitest'
import { back, decline, initialFlow, next, onboardingState, skip, STATE_EXIT, toArrival, toCharacter, toSignIn, type Flow, type Step, type StateInputs } from '../onboarding/flowSteps'

const times = (f: Flow, n: number) => Array.from({ length: n }).reduce<Flow>((acc) => next(acc), f)

describe('flowSteps', () => {
  it('walks title, 1 to 7, then the contract', () => {
    expect(times(initialFlow(false), 1).step).toBe(1)
    expect(times(initialFlow(false), 7).step).toBe(7)
    expect(times(initialFlow(false), 8).step).toBe('contract')
    expect(next(times(initialFlow(false), 8)).step).toBe('signin')
  })

  it('Back retraces the same path to the title', () => {
    let f = times(initialFlow(false), 8)
    const seen = [f.step]
    for (let i = 0; i < 8; i++) seen.push((f = back(f)).step)
    expect(seen).toEqual(['contract', 7, 6, 5, 4, 3, 2, 1, 'title'])
    expect(back(f)).toBe(f)
  })

  it('Back after Skip returns to the beat it was pressed on', () => {
    const f = skip(times(initialFlow(false), 3))
    expect(f.step).toBe('contract')
    expect(back(f).step).toBe(3)
  })

  it('Back after the header Sign in returns to where the player was', () => {
    expect(back(toSignIn(times(initialFlow(false), 2))).step).toBe(2)
  })

  it('an OAuth resume starts at the contract', () => {
    expect(initialFlow(true).step).toBe('contract')
    expect(initialFlow(false, true).step).toBe('returning')
    // A failed OAuth (resume mark + ?login) reopens the sign-in card with the contract behind it (O2).
    expect(initialFlow(true, true)).toEqual({ step: 'signin', history: ['contract'] })
    expect(back(initialFlow(true, true)).step).toBe('contract')
  })

  it('the contract comes before sign-in, and Back from sign-in returns to it', () => {
    const f = next(times(initialFlow(false), 8))
    expect(back(f).step).toBe('contract')
  })

  it('declining goes to Declined; Back (Reconsider) returns to the contract', () => {
    const f = decline(times(initialFlow(false), 8))
    expect(f.step).toBe('declined')
    expect(back(f).step).toBe('contract')
  })

  it('with a character, Back from arrival skips the creation form to the contract', () => {
    const f = toArrival(toCharacter(times(initialFlow(false), 8)))
    expect(back(f).step).toBe('character')
    const b = back(f, true)
    expect(b.step).toBe('contract')
    expect(b.history).not.toContain('character')
  })

  it('the creation form is unreachable once a character exists', () => {
    const f = times(initialFlow(false), 8)
    expect(toCharacter(f, true)).toBe(f)
  })
})

const STEPS: Step[] = ['title', 1, 4, 7, 'contract', 'declined', 'signin', 'returning', 'character', 'arrival']
const BOOLS = [false, true]

describe('onboardingState', () => {
  it('every input combination maps to a state with an exit', () => {
    let count = 0
    for (const step of STEPS)
      for (const stepsLoaded of BOOLS)
        for (const stepsFailed of BOOLS)
          for (const authLoading of BOOLS)
            for (const recording of BOOLS)
              for (const signedIn of BOOLS)
                for (const termsOnFile of BOOLS)
                  for (const creationBanned of BOOLS) {
                    const i: StateInputs = { step, stepsLoaded, stepsFailed, authLoading, recording, signedIn, termsOnFile, creationBanned }
                    const s = onboardingState(i)
                    count++
                    expect(STATE_EXIT[s], JSON.stringify(i)).toBeTruthy()
                    // The two pending states can only be produced while something is pending that will clear them.
                    if (s === 'RECORDING_TERMS') expect(recording).toBe(true)
                    if (s === 'CONTRACT_ON_FILE') expect(signedIn && termsOnFile).toBe(true)
                  }
    expect(count).toBe(STEPS.length * 128)
  })

  it('a finished recording on a contract with terms on file is the auto hand-off, never a stuck card (#4187)', () => {
    const base = { step: 'contract', stepsLoaded: true, stepsFailed: false, authLoading: false, signedIn: true, termsOnFile: true, creationBanned: false } as const
    expect(onboardingState({ ...base, recording: true })).toBe('RECORDING_TERMS')
    expect(onboardingState({ ...base, recording: false })).toBe('CONTRACT_ON_FILE')
  })
})
