/**
 * SoftMarket Kenya — Phone Number Normalization & Validation Utility
 *
 * Handles standard Kenyan telco formats:
 * - Safaricom: 070x, 071x, 072x, 074x, 079x, 0110, 0111, 0112, 0113, 0114, 0115
 * - Airtel: 073x, 075x, 078x, 0100, 0101, 0102, 0103, 0104, 0105, 0106
 * - Telkom: 077x
 * - Equitel: 076x
 * - Faiba (JTL): 0747
 *
 * Supports input formats:
 * - 0712345678, 0110123456
 * - +254712345678, +254110123456
 * - 254712345678, 254110123456
 * - 712345678, 110123456 (9 digits without leading 0)
 * - Formatted with punctuation: (0712) 345-678, +254 712 345 678, 0712 345 678
 */

export type TelcoCarrier =
  | "Safaricom"
  | "Airtel"
  | "Telkom"
  | "Equitel"
  | "Faiba"
  | "Unknown";

export interface PhoneValidationResult {
  valid: boolean;
  normalized?: string; // 2547XXXXXXXX or 2541XXXXXXXX (M-Pesa format)
  e164?: string; // +2547XXXXXXXX
  national?: string; // 0712 345 678
  carrier?: TelcoCarrier;
  error?: string;
}

/**
 * Strips all non-digit characters from a phone number string.
 */
export function extractDigits(phone: string): string {
  if (!phone || typeof phone !== "string") return "";
  return phone.replace(/\D/g, "");
}

/**
 * Normalizes any Kenyan phone number into the standard 12-digit format `254XXXXXXXXX`.
 * Returns null if the phone number is invalid.
 */
export function normalizeKenyanPhone(phone: string): string | null {
  if (!phone || typeof phone !== "string") return null;

  let digits = extractDigits(phone);
  if (!digits) return null;

  // Handle cases like +254 (07...) or 25407... where 0 is retained after 254
  if (digits.startsWith("2540") && digits.length === 13) {
    digits = `254${digits.substring(4)}`;
  }

  // Case 1: Already starts with country code 254
  if (digits.startsWith("254")) {
    if (digits.length === 12) {
      const nextDigit = digits.charAt(3);
      if (nextDigit === "7" || nextDigit === "1") {
        return digits;
      }
    }
    return null;
  }

  // Case 2: Starts with national trunk prefix 0 (e.g. 07... or 01...)
  if (digits.startsWith("0")) {
    if (digits.length === 10) {
      const secondDigit = digits.charAt(1);
      if (secondDigit === "7" || secondDigit === "1") {
        return `254${digits.substring(1)}`;
      }
    }
    return null;
  }

  // Case 3: 9-digit number omitting leading 0 (e.g. 712345678 or 110123456)
  if (digits.length === 9) {
    const firstDigit = digits.charAt(0);
    if (firstDigit === "7" || firstDigit === "1") {
      return `254${digits}`;
    }
    return null;
  }

  return null;
}

/**
 * Validates whether a given string is a valid Kenyan phone number.
 */
export function isValidKenyanPhone(phone: string): boolean {
  return normalizeKenyanPhone(phone) !== null;
}

/**
 * Formats a Kenyan phone number in International E.164 format (+2547XXXXXXXX).
 */
export function formatE164(phone: string): string | null {
  const normalized = normalizeKenyanPhone(phone);
  return normalized ? `+${normalized}` : null;
}

/**
 * Formats a Kenyan phone number in Safaricom M-Pesa format (2547XXXXXXXX).
 */
export function formatMpesa(phone: string): string | null {
  return normalizeKenyanPhone(phone);
}

/**
 * Formats a Kenyan phone number in Human-Readable National format (0712 345 678 or 0110 123 456).
 */
export function formatNational(phone: string): string | null {
  const normalized = normalizeKenyanPhone(phone);
  if (!normalized) return null;

  // normalized: 254 7XX XXX XXX or 254 1XX XXX XXX
  const local = `0${normalized.substring(3)}`;
  return `${local.substring(0, 4)} ${local.substring(4, 7)} ${local.substring(7)}`;
}

/**
 * Formats a Kenyan phone number for tel: links.
 */
export function formatTelUri(phone: string): string | null {
  const e164 = formatE164(phone);
  return e164 ? `tel:${e164}` : null;
}

/**
 * Identifies the telecommunications carrier from a normalized or raw phone number.
 */
export function getCarrier(phone: string): TelcoCarrier {
  const normalized = normalizeKenyanPhone(phone);
  if (!normalized) return "Unknown";

  // Prefix after 254: e.g. "712" or "110"
  const prefix3 = normalized.substring(3, 6);
  const prefix2 = normalized.substring(3, 5);

  // Faiba 4G (0747)
  if (prefix3 === "747") return "Faiba";

  // Safaricom prefixes:
  // 0700-0709, 0710-0719, 0720-0729, 0740-0743, 0745, 0746, 0748, 0790-0799
  // 0110-0115
  if (
    prefix2 === "70" ||
    prefix2 === "71" ||
    prefix2 === "72" ||
    prefix2 === "79" ||
    ["740", "741", "742", "743", "745", "746", "748"].includes(prefix3) ||
    ["110", "111", "112", "113", "114", "115"].includes(prefix3)
  ) {
    return "Safaricom";
  }

  // Airtel prefixes:
  // 0730-0739, 0750-0759, 0780-0789
  // 0100-0106
  if (
    prefix2 === "73" ||
    prefix2 === "75" ||
    prefix2 === "78" ||
    ["100", "101", "102", "103", "104", "105", "106"].includes(prefix3)
  ) {
    return "Airtel";
  }

  // Telkom prefixes: 0770-0779
  if (prefix2 === "77") return "Telkom";

  // Equitel: 0763-0766
  if (["763", "764", "765", "766"].includes(prefix3)) return "Equitel";

  return "Unknown";
}

/**
 * Full validation and enrichment of a phone number.
 */
export function validateAndSanitizePhone(phone: string): PhoneValidationResult {
  if (!phone || typeof phone !== "string" || !phone.trim()) {
    return { valid: false, error: "Phone number is required" };
  }

  const normalized = normalizeKenyanPhone(phone);
  if (!normalized) {
    const digits = extractDigits(phone);
    if (digits.length < 9) {
      return { valid: false, error: "Phone number is too short" };
    }
    if (digits.length > 12) {
      return { valid: false, error: "Phone number is too long" };
    }
    return {
      valid: false,
      error: "Invalid Kenyan phone number format. Must start with 07, 01, +2547, or +2541",
    };
  }

  return {
    valid: true,
    normalized,
    e164: `+${normalized}`,
    national: formatNational(normalized)!,
    carrier: getCarrier(normalized),
  };
}
