export type DateLike = string | number | Date | null | undefined;

const TIMEZONE_REGEX = /([zZ]|[+-]\d{2}:\d{2})$/;
const DEFAULT_TIME_ZONE = "America/Toronto";

const parseDate = (value: DateLike): Date | null => {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  let input = value;
  if (typeof input === "string") {
    const trimmed = input.trim();
    if (!trimmed) {
      return null;
    }
    input = trimmed;
    if (/^\d{4}-\d{2}-\d{2} /.test(trimmed)) {
      input = trimmed.replace(" ", "T");
    }
    if (typeof input === "string" && input.includes(".")) {
      input = input.replace(/(\.\d{3})\d+/, "$1");
    }
    if (!TIMEZONE_REGEX.test(String(input))) {
      input = `${input}Z`;
    }
  }
  const date = new Date(input);
  return Number.isNaN(date.getTime()) ? null : date;
};

export const formatLocalDateTime = (value: DateLike, timeZone?: string): string => {
  const date = parseDate(value);
  if (!date) {
    return value ? String(value) : "-";
  }
  const zone = timeZone ?? DEFAULT_TIME_ZONE;
  return date.toLocaleString("en-CA", { timeZone: zone });
};

export const toDateTimeLocalInput = (value: DateLike): string => {
  const date = parseDate(value);
  if (!date) {
    return "";
  }
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
};
