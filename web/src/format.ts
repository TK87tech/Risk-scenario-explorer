import type { RiskClass } from "./api";

export const fmt = new Intl.NumberFormat("en-US");
export const signed = (n: number) => `${n >= 0 ? "+" : "−"}${fmt.format(Math.abs(n))}`;

// One hue, light to dark, for an ordered scale. Class names are always shown next to the colour,
// so the map is readable without relying on colour alone.
export const RISK_COLORS: Record<RiskClass, string> = {
  low: "#9ec5f4",
  moderate: "#5598e7",
  high: "#256abf",
  "very high": "#104281",
};
export const RISK_ORDER: RiskClass[] = ["low", "moderate", "high", "very high"];
