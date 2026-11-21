export const ff: { current: 'mobile' | 'desktop' } = { current: 'desktop' }
export const mockModule = { useFormFactor: () => ff.current }
