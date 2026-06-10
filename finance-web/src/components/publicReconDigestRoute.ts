export type PublicReconDigestView = 'boss' | 'finance';

export interface PublicReconDigestRoute {
  token: string;
  view: PublicReconDigestView | '';
}

export function parsePublicReconDigestPath(pathname: string): PublicReconDigestRoute {
  const match = pathname.match(/^\/recon\/digests\/([^/]+)\/(boss|finance)\/?$/);
  if (!match) {
    return { token: '', view: '' };
  }

  try {
    return {
      token: decodeURIComponent(match[1]),
      view: match[2] as PublicReconDigestView,
    };
  } catch {
    return { token: '', view: '' };
  }
}

export function isPublicReconDigestPath(pathname: string = window.location.pathname): boolean {
  const route = parsePublicReconDigestPath(pathname);
  return Boolean(route.token && route.view);
}
