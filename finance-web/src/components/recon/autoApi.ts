export async function fetchReconAutoApi(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const candidates = [`/api/recon${normalizedPath}`, `/api/api/recon${normalizedPath}`];

  let fallbackResponse: Response | null = null;

  for (const candidate of candidates) {
    const response = await fetch(candidate, init);
    if (response.status !== 404) {
      return response;
    }
    fallbackResponse = response;
  }

  return fallbackResponse ?? fetch(candidates[0], init);
}
