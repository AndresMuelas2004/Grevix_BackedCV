// Resolves after `ms` milliseconds. Rejects with an AbortError when `signal` aborts first.
export function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('The wait was cancelled.', 'AbortError'))
      return
    }
    const timer = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    function onAbort() {
      window.clearTimeout(timer)
      reject(new DOMException('The wait was cancelled.', 'AbortError'))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}
