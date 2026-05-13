export function parsePublicReconRunExceptionsRunId(pathname: string): string {
  const match = pathname.match(/^\/recon\/runs\/([^/]+)\/exceptions\/?$/);
  return match ? decodeURIComponent(match[1]) : '';
}

export function isPublicReconRunExceptionsPath(pathname: string = window.location.pathname): boolean {
  return Boolean(parsePublicReconRunExceptionsRunId(pathname));
}
