/**
 * A repaint on a short leash.
 *
 * Streamed gates arrive in bursts, and each one is a reason to rebuild the tree.
 * A 40-gate run must not mean 40 full re-renders back to back, so the first
 * request paints and the rest fold into one that follows it.
 */

/** Quiet period between repaints, in milliseconds. */
const LEASH_MS = 250;

export class Coalescer {
  private at = 0;
  private timer: NodeJS.Timeout | undefined;

  constructor(private readonly render: () => void) {}

  soon(): void {
    if (this.timer) return;
    const wait = Math.max(0, this.at + LEASH_MS - Date.now());
    this.timer = setTimeout(() => {
      this.timer = undefined;
      this.at = Date.now();
      this.render();
    }, wait);
  }

  cancel(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
  }
}
