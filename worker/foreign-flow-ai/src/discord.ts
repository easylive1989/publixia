/** Split a markdown blob into <2000-char Discord webhook messages.
 *
 * Splits on line breaks so we don't slice through a table row when we
 * can avoid it. Lines that are themselves longer than the limit get
 * hard-sliced rather than dropped. ``maxLen`` defaults to 1900 leaving
 * room for a small overhead margin under Discord's 2000-char limit.
 */
export function chunkForDiscord(md: string, maxLen = 1900): string[] {
  const chunks: string[] = [];
  let buf = "";
  for (const line of md.split("\n")) {
    if (line.length > maxLen) {
      if (buf) {
        chunks.push(buf);
        buf = "";
      }
      for (let i = 0; i < line.length; i += maxLen) {
        chunks.push(line.slice(i, i + maxLen));
      }
      continue;
    }
    const next = buf ? buf + "\n" + line : line;
    if (next.length > maxLen) {
      chunks.push(buf);
      buf = line;
    } else {
      buf = next;
    }
  }
  if (buf) chunks.push(buf);
  return chunks;
}

export async function postDiscord(
  webhookUrl: string,
  content: string,
): Promise<void> {
  const resp = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!resp.ok) {
    // Discord failures shouldn't sink the whole job — log and move on.
    const body = await resp.text().catch(() => "");
    console.error(
      "discord_post_failed",
      resp.status,
      body.slice(0, 200),
    );
  }
}
