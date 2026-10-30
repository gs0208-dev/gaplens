import { QueryClient } from '@tanstack/react-query'

// One shared client, so code outside React (the session refresh) can seed the same cache that
// the components read. Retries are off because the API client already handles the one case that
// is worth a second try, an expired access token.
export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})
