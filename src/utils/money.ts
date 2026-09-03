/**
 * SoftMarket Kenya — Currency & Money Arithmetic Utilities
 *
 * Implements strict integer-cent arithmetic for Kenyan Shillings (KES).
 * 1 KES = 100 Cents.
 *
 * Prevents IEEE 754 floating-point inaccuracies (e.g. 0.1 + 0.2 !== 0.3)
 * in financial calculations, cart totals, discounts, taxes, and commission splits.
 */

export interface FormatKesOptions {
  showCents?: boolean;
  symbol?: string; // "KSh", "KES", etc.
  locale?: string;
}

export class Money {
  readonly cents: number;

  constructor(cents: number) {
    if (!Number.isInteger(cents)) {
      this.cents = Math.round(cents);
    } else {
      this.cents = cents;
    }
  }

  static fromKes(kes: number): Money {
    return new Money(Math.round(kes * 100));
  }

  static fromCents(cents: number): Money {
    return new Money(cents);
  }

  static zero(): Money {
    return new Money(0);
  }

  toKes(): number {
    return this.cents / 100;
  }

  add(other: Money | number): Money {
    const addCents = typeof other === "number" ? other : other.cents;
    return new Money(this.cents + addCents);
  }

  subtract(other: Money | number): Money {
    const subCents = typeof other === "number" ? other : other.cents;
    return new Money(this.cents - subCents);
  }

  multiply(factor: number): Money {
    return new Money(Math.round(this.cents * factor));
  }

  divide(divisor: number): Money {
    if (divisor === 0) {
      throw new Error("Division by zero in Money calculation");
    }
    return new Money(Math.round(this.cents / divisor));
  }

  percentage(rate: number): Money {
    return new Money(Math.round((this.cents * rate) / 100));
  }

  isZero(): boolean {
    return this.cents === 0;
  }

  isPositive(): boolean {
    return this.cents > 0;
  }

  isNegative(): boolean {
    return this.cents < 0;
  }

  equals(other: Money): boolean {
    return this.cents === other.cents;
  }

  greaterThan(other: Money): boolean {
    return this.cents > other.cents;
  }

  greaterThanOrEqual(other: Money): boolean {
    return this.cents >= other.cents;
  }

  lessThan(other: Money): boolean {
    return this.cents < other.cents;
  }

  lessThanOrEqual(other: Money): boolean {
    return this.cents <= other.cents;
  }

  format(options?: FormatKesOptions): string {
    return formatKES(this.cents, options);
  }

  toJSON(): { cents: number; kes: number; formatted: string } {
    return {
      cents: this.cents,
      kes: this.toKes(),
      formatted: this.format(),
    };
  }
}

/**
 * Converts KES floating/integer number to integer cents.
 */
export function kesToCents(kes: number): number {
  if (typeof kes !== "number" || isNaN(kes)) return 0;
  return Math.round(kes * 100);
}

/**
 * Converts integer cents to KES float.
 */
export function centsToKes(cents: number): number {
  if (typeof cents !== "number" || isNaN(cents)) return 0;
  return Math.round(cents) / 100;
}

/**
 * Adds multiple cent values safely.
 */
export function addCents(...amounts: number[]): number {
  return amounts.reduce((acc, curr) => acc + (Math.round(curr) || 0), 0);
}

/**
 * Subtracts b from a in cents safely.
 */
export function subtractCents(a: number, b: number): number {
  return (Math.round(a) || 0) - (Math.round(b) || 0);
}

/**
 * Multiplies cents by a factor with bankers/standard rounding.
 */
export function multiplyCents(cents: number, factor: number): number {
  return Math.round((Math.round(cents) || 0) * factor);
}

/**
 * Divides cents by a divisor with rounding.
 */
export function divideCents(cents: number, divisor: number): number {
  if (divisor === 0) {
    throw new Error("Division by zero in cents arithmetic");
  }
  return Math.round((Math.round(cents) || 0) / divisor);
}

/**
 * Calculates a percentage of cent amount (e.g. 16 for 16% VAT).
 */
export function calculatePercentage(baseCents: number, percentage: number): number {
  return Math.round(((Math.round(baseCents) || 0) * percentage) / 100);
}

/**
 * Formats integer cents into Kenyan currency display string.
 * Example: 150000 -> "KSh 1,500.00" or "KSh 1,500"
 */
export function formatKES(cents: number, options: FormatKesOptions = {}): string {
  const { showCents = false, symbol = "KSh", locale = "en-KE" } = options;
  const kes = centsToKes(cents);

  const formatter = new Intl.NumberFormat(locale, {
    minimumFractionDigits: showCents ? 2 : 0,
    maximumFractionDigits: showCents ? 2 : 0,
  });

  const formattedNumber = formatter.format(kes);
  return symbol ? `${symbol} ${formattedNumber}` : formattedNumber;
}

/**
 * Splits an amount in cents into N parts, distributing remainder cents evenly.
 * Guarantees that sum(parts) === totalCents exactly (zero leakage).
 */
export function splitCentsEvenly(totalCents: number, partsCount: number): number[] {
  if (partsCount <= 0) return [];
  const basePart = Math.floor(totalCents / partsCount);
  let remainder = totalCents % partsCount;

  const result: number[] = [];
  for (let i = 0; i < partsCount; i++) {
    let part = basePart;
    if (remainder > 0) {
      part += 1;
      remainder -= 1;
    } else if (remainder < 0) {
      part -= 1;
      remainder += 1;
    }
    result.push(part);
  }
  return result;
}

/**
 * Allocates an amount proportionally across ratios (e.g. tax distribution).
 * Guarantees zero leakage: sum of allocated parts equals totalCents.
 */
export function allocateCentsByRatios(totalCents: number, ratios: number[]): number[] {
  const totalRatio = ratios.reduce((acc, r) => acc + r, 0);
  if (totalRatio === 0) {
    return splitCentsEvenly(totalCents, ratios.length);
  }

  let remainder = totalCents;
  const results: number[] = [];

  for (let i = 0; i < ratios.length; i++) {
    const share = Math.floor((totalCents * ratios[i]) / totalRatio);
    results.push(share);
    remainder -= share;
  }

  // Distribute any remainder 1 cent at a time
  for (let i = 0; i < remainder; i++) {
    results[i % results.length] += 1;
  }

  return results;
}
