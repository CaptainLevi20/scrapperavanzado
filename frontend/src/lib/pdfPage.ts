// Given how much of each page is currently visible in the viewport (its
// IntersectionObserver ratio, keyed by page number), pick the page that
// dominates the view — that's the "current" page shown in the "Página X de N"
// indicator. Ties break toward the lower page number (the one you reach first
// scrolling down), and an empty/all-zero map returns page 1.
export function pickCurrentPage(ratios: Map<number, number>): number {
  let best = 1;
  let bestRatio = -1;
  for (const [page, ratio] of ratios) {
    if (ratio > bestRatio || (ratio === bestRatio && page < best)) {
      bestRatio = ratio;
      best = page;
    }
  }
  return best;
}
