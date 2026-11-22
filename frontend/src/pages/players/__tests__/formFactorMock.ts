export const ff: { current: 'mobile' | 'desktop' } = { current: 'desktop' }
/** Phone width with a mouse: width hook true, form factor stays desktop. */
export const finePointer = { current: false }
export const mockModule = {
  useFormFactor: () => (finePointer.current ? 'desktop' : ff.current),
  usePhoneWidth: () => ff.current === 'mobile',
}
