/** The inline style of the element whose own text is `bonus` (Singularity brackets it); static markup has no DOM to query. */
export function bonusStyle(html: string, bonus: string): string {
  const escaped = bonus.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = html.match(new RegExp(`<[^>]*style="([^"]*)"[^>]*>\\[?${escaped}\\]?<`));
  if (!m) throw new Error(`no element holds the bonus text "${bonus}"`);
  return m[1];
}
