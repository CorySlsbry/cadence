/** Two-character dialogue helpers for the Faceless studio. */

export type DialogueLine = { speaker: "A" | "B"; text: string };

/**
 * Parse a dialogue script into ordered speaker lines. Accepts "A:" / "B:" prefixes
 * (case-insensitive, optional bold/whitespace). Unprefixed lines continue the
 * previous speaker, so the LLM drifting from strict formatting never drops words.
 */
export function parseDialogueLines(script: string): DialogueLine[] {
  const out: DialogueLine[] = [];
  let current: "A" | "B" = "A";
  for (const raw of script.split(/\r?\n/)) {
    const line = raw.replace(/\*\*/g, "").trim();
    if (!line) continue;
    const m = /^([AB])\s*[:.\-–]\s*(.*)$/i.exec(line);
    if (m) {
      current = m[1].toUpperCase() as "A" | "B";
      if (m[2].trim()) out.push({ speaker: current, text: m[2].trim() });
    } else if (out.length > 0 && out[out.length - 1].speaker === current) {
      out[out.length - 1].text += ` ${line}`;
    } else {
      out.push({ speaker: current, text: line });
    }
  }
  return out;
}

/** The scene-direction block that puts both cast members in every generated scene. */
export function buildCastDirection(
  a: { description: string },
  b: { description: string },
  userDirection: string,
): string {
  const cast =
    `TWO RECURRING CHARACTERS appear together in every scene, interacting as the story implies — ` +
    `Character A: ${a.description.trim()}. Character B: ${b.description.trim()}. ` +
    `Keep both characters visually consistent across all scenes.`;
  return userDirection.trim() ? `${cast} ${userDirection.trim()}` : cast;
}

/** Rough seconds-per-line pacing guard so the dialogue script targets the length. */
export function dialogueWordTarget(lengthSec: number): number {
  return Math.round((lengthSec / 60) * 140); // dialogue runs slightly slower than narration
}
