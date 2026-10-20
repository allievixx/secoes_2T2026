export async function fetchJSON<T = unknown>(url: string | URL, fresh = false): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(url, { signal: controller.signal, cache: fresh ? "no-store" : "default" });
    if (!response.ok) {
      throw new Error(`Não foi possível buscar ${new URL(url, location.href).pathname} (HTTP ${response.status}).`);
    }
    return await response.json() as T;
  } finally {
    clearTimeout(timer);
  }
}
