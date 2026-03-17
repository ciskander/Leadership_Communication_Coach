/**
 * Shared style constants for consistent UI across all pages.
 *
 * Usage:  import { S } from '@/config/styles';
 *         <h1 className={S.pageHeading}>…</h1>
 *
 * These are plain Tailwind class strings — they work anywhere a className is accepted.
 * Keep entries alphabetized within each section for easy scanning.
 */

export const S = {
  // ── Typography ──────────────────────────────────────────────────────────────

  /** Main page heading (h1) — serif, 2xl, no bold */
  pageHeading: 'font-serif text-2xl text-cv-stone-900',

  /** Page subtitle beneath heading */
  pageSubtitle: 'text-sm text-cv-stone-500 mt-1',

  /** Uppercase section label (e.g. "Current Experiment", "Your Baseline") */
  sectionHeading: 'text-2xs font-medium text-cv-stone-400 uppercase tracking-widest',

  /** Field label for form inputs */
  fieldLabel: 'text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400',

  /** Pattern label — teal accent */
  patternLabel: 'text-2xs font-semibold uppercase tracking-[0.14em] text-cv-teal-600',

  // ── Cards & containers ──────────────────────────────────────────────────────

  /** Standard card with warm border */
  card: 'bg-white rounded border border-cv-warm-200',

  // ── Buttons ─────────────────────────────────────────────────────────────────

  /** Primary navy CTA button (large) */
  btnNavy: 'bg-cv-navy-600 text-white rounded font-medium hover:bg-cv-navy-700 transition-colors',

  /** Primary teal CTA button */
  btnTeal: 'bg-cv-teal-600 text-white rounded font-medium hover:bg-cv-teal-700 transition-colors',

  /** Ghost / secondary button */
  btnGhost: 'bg-white border border-cv-warm-300 text-cv-stone-700 rounded font-medium hover:bg-cv-warm-50 transition-colors',

  // ── Chart hex colors ────────────────────────────────────────────────────────
  // Recharts requires raw hex strings. These match the cv-* palette where
  // possible, with a harmonious accent set for additional data series.

  /** Sparkline / single-series: maps to cv-teal-600 */
  chartTeal: '#0F6E56',
  /** Warning accent: maps to cv-amber-600 */
  chartAmber: '#D97706',
  /** Error accent: maps to cv-red-400 */
  chartRed: '#E24B4A',
  /** Axis tick text: maps to cv-stone-400 */
  chartAxisFill: '#A8A29E',
  /** Grid stroke: maps to cv-warm-200 */
  chartGrid: '#EDE8E3',
  /** Tooltip cursor: maps to cv-warm-50 */
  chartCursor: '#F7F4F0',
} as const;

/**
 * Extended chart color palette for multi-series charts.
 * First two entries align with cv-teal-600 and cv-amber-600.
 */
export const CHART_COLORS = [
  '#0F6E56', // cv-teal-600
  '#D97706', // cv-amber-600
  '#2563EB', // blue-600 (accent)
  '#7C3AED', // violet-600 (accent)
  '#0891B2', // cyan-600 (accent)
  '#DB2777', // pink-600 (accent)
  '#65A30D', // lime-600 (accent)
  '#EA580C', // orange-600 (accent)
  '#888780', // cv-stone-400
  '#16A34A', // green-600 (accent)
] as const;
