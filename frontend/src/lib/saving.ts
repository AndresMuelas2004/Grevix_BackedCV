import { useCallback, useState } from 'react'

// The requests one screen has in flight. Every control that sends a request is disabled while
// `busy` is true, so two requests on the same analysis do not collide.
export interface Saving {
  busy: boolean
  // Runs one request and counts it as in flight until it settles.
  track: <T>(request: () => Promise<T>) => Promise<T>
}

// One shared state per screen: call it once in the screen and pass the result to its controls.
export function useSaving(): Saving {
  const [inFlight, setInFlight] = useState(0)
  const track = useCallback(async <T>(request: () => Promise<T>): Promise<T> => {
    setInFlight((count) => count + 1)
    try {
      return await request()
    } finally {
      setInFlight((count) => count - 1)
    }
  }, [])
  return { busy: inFlight > 0, track }
}
