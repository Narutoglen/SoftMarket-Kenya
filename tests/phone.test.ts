import { describe, it, expect } from "vitest";
import {
  normalizeKenyanPhone,
  isValidKenyanPhone,
  formatE164,
  formatNational,
  formatMpesa,
  formatTelUri,
  getCarrier,
  validateAndSanitizePhone,
} from "../src/utils/phone.js";

describe("Kenyan Phone Number Normalization & Validation", () => {
  describe("normalizeKenyanPhone", () => {
    it("normalizes Safaricom 07xx numbers (0712345678 -> 254712345678)", () => {
      expect(normalizeKenyanPhone("0712345678")).toBe("254712345678");
      expect(normalizeKenyanPhone("0722000000")).toBe("254722000000");
      expect(normalizeKenyanPhone("0799123456")).toBe("254799123456");
      expect(normalizeKenyanPhone("0701234567")).toBe("254701234567");
    });

    it("normalizes new Safaricom 011x numbers (0110123456 -> 254110123456)", () => {
      expect(normalizeKenyanPhone("0110123456")).toBe("254110123456");
      expect(normalizeKenyanPhone("0111222333")).toBe("254111222333");
      expect(normalizeKenyanPhone("0115999888")).toBe("254115999888");
    });

    it("normalizes Airtel 073x, 075x, 078x numbers", () => {
      expect(normalizeKenyanPhone("0733123456")).toBe("254733123456");
      expect(normalizeKenyanPhone("0750123456")).toBe("254750123456");
      expect(normalizeKenyanPhone("0780123456")).toBe("254780123456");
    });

    it("normalizes new Airtel 010x numbers (0100123456 -> 254100123456)", () => {
      expect(normalizeKenyanPhone("0100123456")).toBe("254100123456");
      expect(normalizeKenyanPhone("0105654321")).toBe("254105654321");
    });

    it("normalizes Telkom 077x numbers", () => {
      expect(normalizeKenyanPhone("0770123456")).toBe("254770123456");
      expect(normalizeKenyanPhone("0775987654")).toBe("254775987654");
    });

    it("normalizes Equitel 076x and Faiba 0747 numbers", () => {
      expect(normalizeKenyanPhone("0763123456")).toBe("254763123456");
      expect(normalizeKenyanPhone("0747123456")).toBe("254747123456");
    });

    it("normalizes numbers already starting with +254 or 254", () => {
      expect(normalizeKenyanPhone("+254712345678")).toBe("254712345678");
      expect(normalizeKenyanPhone("254712345678")).toBe("254712345678");
      expect(normalizeKenyanPhone("+254110123456")).toBe("254110123456");
      expect(normalizeKenyanPhone("254110123456")).toBe("254110123456");
    });

    it("normalizes 9-digit numbers missing the leading 0 (712345678 -> 254712345678)", () => {
      expect(normalizeKenyanPhone("712345678")).toBe("254712345678");
      expect(normalizeKenyanPhone("110123456")).toBe("254110123456");
    });

    it("strips spaces, dashes, brackets, and special characters", () => {
      expect(normalizeKenyanPhone("+254 712 345 678")).toBe("254712345678");
      expect(normalizeKenyanPhone("(0712) 345-678")).toBe("254712345678");
      expect(normalizeKenyanPhone("0712-345-678")).toBe("254712345678");
      expect(normalizeKenyanPhone("  +254-712-345-678  ")).toBe("254712345678");
      expect(normalizeKenyanPhone("+254 (0110) 123 456")).toBe("254110123456");
    });

    it("returns null for invalid or non-Kenyan phone numbers", () => {
      expect(normalizeKenyanPhone("")).toBeNull();
      expect(normalizeKenyanPhone("12345")).toBeNull(); // Too short
      expect(normalizeKenyanPhone("07123456789999")).toBeNull(); // Too long
      expect(normalizeKenyanPhone("+255712345678")).toBeNull(); // Tanzania
      expect(normalizeKenyanPhone("+256712345678")).toBeNull(); // Uganda
      expect(normalizeKenyanPhone("+14155552671")).toBeNull(); // US
      expect(normalizeKenyanPhone("0812345678")).toBeNull(); // Invalid prefix 08
      expect(normalizeKenyanPhone("0612345678")).toBeNull(); // Invalid prefix 06
      expect(normalizeKenyanPhone("abc-def-ghij")).toBeNull();
      expect(normalizeKenyanPhone(null as any)).toBeNull();
      expect(normalizeKenyanPhone(undefined as any)).toBeNull();
    });
  });

  describe("isValidKenyanPhone", () => {
    it("returns true for valid Kenyan numbers across all formats", () => {
      expect(isValidKenyanPhone("0716343561")).toBe(true);
      expect(isValidKenyanPhone("+254716343561")).toBe(true);
      expect(isValidKenyanPhone("0110123456")).toBe(true);
      expect(isValidKenyanPhone("+254110123456")).toBe(true);
      expect(isValidKenyanPhone("254722000000")).toBe(true);
    });

    it("returns false for invalid numbers", () => {
      expect(isValidKenyanPhone("07123")).toBe(false);
      expect(isValidKenyanPhone("0912345678")).toBe(false);
      expect(isValidKenyanPhone("+447911123456")).toBe(false);
    });
  });

  describe("Formatting Helpers", () => {
    it("formatE164 adds plus prefix (+254...)", () => {
      expect(formatE164("0712345678")).toBe("+254712345678");
      expect(formatE164("0110123456")).toBe("+254110123456");
      expect(formatE164("invalid")).toBeNull();
    });

    it("formatMpesa returns 12-digit 254... format", () => {
      expect(formatMpesa("+254712345678")).toBe("254712345678");
      expect(formatMpesa("0712345678")).toBe("254712345678");
    });

    it("formatNational returns formatted local representation", () => {
      expect(formatNational("254712345678")).toBe("0712 345 678");
      expect(formatNational("+254110123456")).toBe("0110 123 456");
      expect(formatNational("invalid")).toBeNull();
    });

    it("formatTelUri returns tel: scheme link", () => {
      expect(formatTelUri("0712345678")).toBe("tel:+254712345678");
      expect(formatTelUri("0110123456")).toBe("tel:+254110123456");
      expect(formatTelUri("bad")).toBeNull();
    });
  });

  describe("Carrier Detection", () => {
    it("detects Safaricom for 070x, 071x, 072x, 079x, and 011x", () => {
      expect(getCarrier("0701123456")).toBe("Safaricom");
      expect(getCarrier("0716343561")).toBe("Safaricom");
      expect(getCarrier("0722123456")).toBe("Safaricom");
      expect(getCarrier("0799123456")).toBe("Safaricom");
      expect(getCarrier("0110123456")).toBe("Safaricom");
      expect(getCarrier("0115123456")).toBe("Safaricom");
    });

    it("detects Airtel for 073x, 075x, 078x, and 010x", () => {
      expect(getCarrier("0733123456")).toBe("Airtel");
      expect(getCarrier("0750123456")).toBe("Airtel");
      expect(getCarrier("0780123456")).toBe("Airtel");
      expect(getCarrier("0100123456")).toBe("Airtel");
      expect(getCarrier("0106123456")).toBe("Airtel");
    });

    it("detects Telkom, Equitel, Faiba, and Unknown", () => {
      expect(getCarrier("0770123456")).toBe("Telkom");
      expect(getCarrier("0763123456")).toBe("Equitel");
      expect(getCarrier("0747123456")).toBe("Faiba");
      expect(getCarrier("invalid")).toBe("Unknown");
    });
  });

  describe("validateAndSanitizePhone", () => {
    it("returns enriched object for valid numbers", () => {
      const result = validateAndSanitizePhone("+254 716 343 561");
      expect(result.valid).toBe(true);
      expect(result.normalized).toBe("254716343561");
      expect(result.e164).toBe("+254716343561");
      expect(result.national).toBe("0716 343 561");
      expect(result.carrier).toBe("Safaricom");
      expect(result.error).toBeUndefined();
    });

    it("returns descriptive error for empty or invalid input", () => {
      expect(validateAndSanitizePhone("").valid).toBe(false);
      expect(validateAndSanitizePhone("").error).toContain("required");

      const shortRes = validateAndSanitizePhone("07123");
      expect(shortRes.valid).toBe(false);
      expect(shortRes.error).toContain("too short");

      const longRes = validateAndSanitizePhone("07123456789999");
      expect(longRes.valid).toBe(false);
      expect(longRes.error).toContain("too long");

      const foreignRes = validateAndSanitizePhone("+14155552671");
      expect(foreignRes.valid).toBe(false);
      expect(foreignRes.error).toContain("Invalid Kenyan");
    });
  });
});
