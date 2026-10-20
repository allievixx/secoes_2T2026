/** Busca um elemento por id; lança se não existir, pois o HTML é parte do contrato da aplicação. */
export function $<T extends HTMLElement = HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Elemento #${id} não encontrado no HTML.`);
  return el as T;
}

export const $maybe = <T extends HTMLElement = HTMLElement>(id: string): T | null =>
  document.getElementById(id) as T | null;

/** Decodifica entidades HTML de textos que a camada de dados já escapou. */
export function unescapeHTML(value: string): string {
  const el = document.createElement("textarea");
  el.innerHTML = value;
  return el.value;
}
