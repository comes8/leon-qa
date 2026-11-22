export const menuSchemaVersion = 'web3-area-batch1';

export function hasLegacyWeb3(rows: unknown[]): boolean {
  return rows.some((value) => {
    const row = value as {path?: unknown; children?: unknown} | null;
    return row?.path === '/api-automation/web3' || (Array.isArray(row?.children) && hasLegacyWeb3(row.children));
  });
}

export function validNavigationCache(rows: unknown, version: unknown): boolean {
  return Array.isArray(rows) && version === menuSchemaVersion && !hasLegacyWeb3(rows);
}
