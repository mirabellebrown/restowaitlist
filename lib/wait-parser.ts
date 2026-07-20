import type { ObservationStatus } from "@/lib/types";

export type ParsedWait = {
  status: ObservationStatus;
  rawWaitText: string;
  waitMinMinutes: number | null;
  waitMaxMinutes: number | null;
  waitMidpointMinutes: number | null;
  errorMessage: string | null;
};

const CLOSED_MARKERS = [
  "waitlist is closed",
  "waitlist closed",
  "not accepting waitlist",
  "join the waitlist when the restaurant opens",
];

function visibleText(html: string): string {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&ndash;|&#8211;/gi, "–")
    .replace(/&mdash;|&#8212;/gi, "—")
    .replace(/\s+/g, " ")
    .trim();
}

export function parseWaitHtml(html: string): ParsedWait {
  const text = visibleText(html).slice(0, 200_000);
  const lower = text.toLowerCase();

  if (CLOSED_MARKERS.some((marker) => lower.includes(marker))) {
    return {
      status: "waitlist_closed",
      rawWaitText: "Waitlist closed",
      waitMinMinutes: null,
      waitMaxMinutes: null,
      waitMidpointMinutes: null,
      errorMessage: null,
    };
  }

  const noWait = lower.match(
    /(?:current\s+)?wait(?:\s+time)?[^.]{0,30}(?:no wait|(?<!\d)0(?!\d)\s*(?:min|minute))/i,
  );
  if (noWait) {
    return {
      status: "no_wait",
      rawWaitText: noWait[0].slice(0, 160),
      waitMinMinutes: 0,
      waitMaxMinutes: 0,
      waitMidpointMinutes: 0,
      errorMessage: null,
    };
  }

  const range = text.match(
    /(?:current\s+)?wait(?:\s+time)?[^\d]{0,30}(\d{1,3})\s*(?:-|–|—|to)\s*(\d{1,3})\s*(?:min|minute)s?/i,
  );
  if (range) {
    const minimum = Number(range[1]);
    const maximum = Number(range[2]);
    if (maximum >= minimum && maximum <= 360) {
      return {
        status: "wait_available",
        rawWaitText: range[0].slice(0, 160),
        waitMinMinutes: minimum,
        waitMaxMinutes: maximum,
        waitMidpointMinutes: (minimum + maximum) / 2,
        errorMessage: null,
      };
    }
  }

  const single = text.match(
    /(?:current\s+)?wait(?:\s+time)?[^\d]{0,30}(\d{1,3})\s*\+?\s*(?:min|minute)s?/i,
  );
  if (single) {
    const minutes = Number(single[1]);
    if (minutes <= 360) {
      return {
        status: "wait_available",
        rawWaitText: single[0].slice(0, 160),
        waitMinMinutes: minutes,
        waitMaxMinutes: minutes,
        waitMidpointMinutes: minutes,
        errorMessage: null,
      };
    }
  }

  return {
    status: "parse_error",
    rawWaitText: "",
    waitMinMinutes: null,
    waitMaxMinutes: null,
    waitMidpointMinutes: null,
    errorMessage:
      "The page loaded, but no unambiguous public wait estimate was found. The source needs review.",
  };
}
