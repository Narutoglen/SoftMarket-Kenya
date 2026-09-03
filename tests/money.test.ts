import { describe, it, expect } from "vitest";
import {
  Money,
  kesToCents,
  centsToKes,
  addCents,
  subtractCents,
  multiplyCents,
  divideCents,
  calculatePercentage,
  formatKES,
  splitCentsEvenly,
  allocateCentsByRatios,
} from "../src/utils/money.js";

describe("Integer-Cent KES Currency Arithmetic", () => {
  describe("Conversions (KES <-> Cents)", () => {
    it("converts KES float to integer cents accurately", () => {
      expect(kesToCents(100)).toBe(10000);
      expect(kesToCents(12.5)).toBe(1250);
      expect(kesToCents(0.01)).toBe(1);
      expect(kesToCents(0.99)).toBe(99);
      expect(kesToCents(1500000.75)).toBe(150000075);
    });

    it("handles floating point round-trip edge cases without precision loss", () => {
      // Classic JS float bug: 0.1 + 0.2 = 0.30000000000000004
      const sumKes = 0.1 + 0.2;
      expect(kesToCents(sumKes)).toBe(30);

      const centSum = addCents(kesToCents(0.1), kesToCents(0.2));
      expect(centSum).toBe(30);
      expect(centsToKes(centSum)).toBe(0.3);
    });

    it("converts integer cents back to KES", () => {
      expect(centsToKes(10000)).toBe(100);
      expect(centsToKes(1250)).toBe(12.5);
      expect(centsToKes(99)).toBe(0.99);
      expect(centsToKes(0)).toBe(0);
    });
  });

  describe("Arithmetic Utilities", () => {
    it("addCents sums multiple cent values", () => {
      expect(addCents(1000, 2500, 300)).toBe(3800);
      expect(addCents(0, 0)).toBe(0);
      expect(addCents()).toBe(0);
    });

    it("subtractCents subtracts values safely", () => {
      expect(subtractCents(5000, 1500)).toBe(3500);
      expect(subtractCents(1000, 2000)).toBe(-1000);
    });

    it("multiplyCents multiplies and rounds correctly", () => {
      expect(multiplyCents(1000, 1.5)).toBe(1500);
      expect(multiplyCents(1000, 0.16)).toBe(160); // 16% VAT on 10 KES
      expect(multiplyCents(333, 2.5)).toBe(833); // 832.5 rounded to 833
    });

    it("divideCents divides and throws on zero divisor", () => {
      expect(divideCents(1000, 3)).toBe(333);
      expect(divideCents(1000, 2)).toBe(500);
      expect(() => divideCents(1000, 0)).toThrow("Division by zero");
    });

    it("calculatePercentage calculates percentages in cents", () => {
      expect(calculatePercentage(100000, 16)).toBe(16000); // 16% of KES 1,000 = KES 160
      expect(calculatePercentage(50000, 10)).toBe(5000); // 10% of KES 500 = KES 50
      expect(calculatePercentage(12345, 5)).toBe(617); // 5% of 123.45 KES = 6.17 KES
    });
  });

  describe("Formatting KES Currency", () => {
    it("formats integer cents to KES display strings", () => {
      expect(formatKES(150000)).toContain("1,500");
      expect(formatKES(150000, { showCents: true })).toContain("1,500.00");
      expect(formatKES(0)).toContain("0");
    });

    it("supports custom currency symbols and options", () => {
      expect(formatKES(250000, { symbol: "KES" })).toBe("KES 2,500");
      expect(formatKES(250000, { symbol: "" })).toBe("2,500");
    });
  });

  describe("Zero-Leakage Splitting & Proportional Allocation", () => {
    it("splitCentsEvenly splits total into N parts with sum(parts) === total exactly", () => {
      const parts3 = splitCentsEvenly(100, 3); // 100 cents into 3 parts
      expect(parts3).toEqual([34, 33, 33]);
      expect(parts3.reduce((a, b) => a + b, 0)).toBe(100);

      const parts7 = splitCentsEvenly(1000, 7);
      expect(parts7.reduce((a, b) => a + b, 0)).toBe(1000);

      const parts1 = splitCentsEvenly(500, 1);
      expect(parts1).toEqual([500]);
      expect(splitCentsEvenly(500, 0)).toEqual([]);
    });

    it("allocateCentsByRatios allocates proportionally with zero cent loss", () => {
      // Allocate 1000 cents across ratios [50, 30, 20]
      const allocated = allocateCentsByRatios(1000, [50, 30, 20]);
      expect(allocated).toEqual([500, 300, 200]);
      expect(allocated.reduce((a, b) => a + b, 0)).toBe(1000);

      // Allocate 100 cents across ratios [1, 1, 1]
      const allocated3 = allocateCentsByRatios(100, [1, 1, 1]);
      expect(allocated3.reduce((a, b) => a + b, 0)).toBe(100);

      // Complex ratios with remainders
      const allocatedComplex = allocateCentsByRatios(9999, [33, 44, 23]);
      expect(allocatedComplex.reduce((a, b) => a + b, 0)).toBe(9999);
    });
  });

  describe("Money Class Methods", () => {
    it("constructs and performs fluent operations", () => {
      const price = Money.fromKes(1500); // 150,000 cents
      const tax = price.percentage(16); // 24,000 cents (16%)
      const total = price.add(tax);

      expect(total.toKes()).toBe(1740);
      expect(total.cents).toBe(174000);
      expect(total.format()).toContain("1,740");
    });

    it("performs comparisons accurately", () => {
      const a = Money.fromKes(100);
      const b = Money.fromKes(200);
      const c = Money.fromKes(100);

      expect(a.lessThan(b)).toBe(true);
      expect(b.greaterThan(a)).toBe(true);
      expect(a.equals(c)).toBe(true);
      expect(a.greaterThanOrEqual(c)).toBe(true);
      expect(a.isPositive()).toBe(true);
      expect(Money.zero().isZero()).toBe(true);
    });

    it("toJSON serializes structured money object", () => {
      const m = Money.fromKes(500);
      const json = m.toJSON();
      expect(json.cents).toBe(50000);
      expect(json.kes).toBe(500);
      expect(json.formatted).toContain("500");
    });
  });
});
