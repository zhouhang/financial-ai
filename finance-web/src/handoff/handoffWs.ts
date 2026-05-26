export function buildHandoffWsUrl(token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/handoff/ws?t=${encodeURIComponent(token)}`;
}

export function parseHandoffToken(): string {
  return new URLSearchParams(window.location.search).get('t') || '';
}
