import { describe, it, expect } from "vitest";
import {
  calculateCartTotals,
  validateCoupon,
  KENYA_STANDARD_VAT_RATE,
} from "../src/services/cart/index.js";
import { CouponValidationError } from "../src/utils/errors.js";

describe("Cart Subtotal, Kenya 16% VAT & Coupon Calculator", () => {
  const sampleItems = [
    {
      id: "item-1",
      productId: "prod-web-dev",
      vendorId: "vendor-tech-1",
      title: "Custom Web Application",
      unitPriceCents: 5000000, // KES 50,000
      quantity: 1,
      taxable: true,
    },
    {
      id: "item-2",
      productId: "prod-cloud-hosting",
      vendorId: "vendor-cloud-2",
      title: "Cloud Infrastructure Setup",
      unitPriceCents: 1500000, // KES 15,000
      quantity: 2, // Total KES 30,000
      taxable: true,
    },
  ];

  describe("Cart Subtotal & Multi-Item Calculation", () => {
    it("calculates subtotal and item totals accurately in integer cents", () => {
      const res = calculateCartTotals({ items: sampleItems });

      // Subtotal: 50,000 + 30,000 = KES 80,000 (8,000,000 cents)
      expect(res.subtotalCents).toBe(8000000);
      expect(res.totalQuantity).toBe(3);
      expect(res.formattedSubtotal).toContain("80,000");
    });

    it("handles single item and empty cart gracefully", () => {
      const empty = calculateCartTotals({ items: [] });
      expect(empty.subtotalCents).toBe(0);
      expect(empty.grandTotalCents).toBe(0);

      const single = calculateCartTotals({
        items: [
          {
            id: "single-1",
            productId: "p1",
            vendorId: "v1",
            title: "Domain Registration",
            unitPriceCents: 120000, // KES 1,200
            quantity: 1,
          },
        ],
      });
      expect(single.subtotalCents).toBe(120000);
    });

    it("throws error for invalid quantities or negative unit prices", () => {
      expect(() =>
        calculateCartTotals({
          items: [
            {
              id: "bad-1",
              productId: "p1",
              vendorId: "v1",
              title: "Test",
              unitPriceCents: 100,
              quantity: 0,
            },
          ],
        })
      ).toThrow("Invalid item quantity");

      expect(() =>
        calculateCartTotals({
          items: [
            {
              id: "bad-2",
              productId: "p1",
              vendorId: "v1",
              title: "Test",
              unitPriceCents: -500,
              quantity: 1,
            },
          ],
        })
      ).toThrow("Invalid unit price");
    });
  });

  describe("Kenya 16% VAT Calculation", () => {
    it("calculates 16% standard VAT on taxable items (VAT-exclusive mode)", () => {
      const res = calculateCartTotals({
        items: sampleItems,
        pricesIncludeVat: false, // VAT added on top
      });

      // Subtotal: 8,000,000 cents (KES 80,000)
      // 16% VAT = 1,280,000 cents (KES 12,800)
      // Grand Total = 8,000,000 + 1,280,000 = 9,280,000 cents (KES 92,800)
      expect(res.vatAmountCents).toBe(1280000);
      expect(res.grandTotalCents).toBe(9280000);
      expect(res.formattedVat).toContain("12,800");
    });

    it("extracts 16% VAT correctly when prices are VAT-inclusive", () => {
      const res = calculateCartTotals({
        items: [
          {
            id: "inc-1",
            productId: "p1",
            vendorId: "v1",
            title: "POS Terminal",
            unitPriceCents: 1160000, // KES 11,600 (inclusive of 16% VAT -> Net 10,000, VAT 1,600)
            quantity: 1,
            taxable: true,
          },
        ],
        pricesIncludeVat: true,
      });

      expect(res.subtotalCents).toBe(1160000);
      expect(res.vatAmountCents).toBe(160000); // KES 1,600
      expect(res.grandTotalCents).toBe(1160000);
    });

    it("skips VAT calculation on non-taxable / zero-rated items", () => {
      const res = calculateCartTotals({
        items: [
          {
            id: "zero-1",
            productId: "p-export",
            vendorId: "v1",
            title: "Export Software License",
            unitPriceCents: 1000000, // KES 10,000
            quantity: 1,
            taxable: false, // Zero-rated
          },
        ],
        pricesIncludeVat: false,
      });

      expect(res.vatAmountCents).toBe(0);
      expect(res.grandTotalCents).toBe(1000000);
    });
  });

  describe("Coupon Discounts & Allocation", () => {
    it("applies fixed amount coupon discount", () => {
      const res = calculateCartTotals({
        items: sampleItems, // Subtotal 80,000 KES
        coupon: {
          code: "SAVE5K",
          type: "fixed_amount",
          value: 500000, // KES 5,000 discount
          isActive: true,
        },
        pricesIncludeVat: false,
      });

      expect(res.discountCents).toBe(500000);
      expect(res.netSubtotalCents).toBe(7500000); // 80,000 - 5,000 = 75,000 KES
      // 16% VAT on 75,000 = 12,000 KES (1,200,000 cents)
      expect(res.vatAmountCents).toBe(1200000);
      expect(res.grandTotalCents).toBe(8700000);
    });

    it("applies percentage coupon discount with max discount cap", () => {
      const res = calculateCartTotals({
        items: sampleItems, // Subtotal 80,000 KES
        coupon: {
          code: "DISCOUNT20",
          type: "percentage",
          value: 20, // 20% of 80,000 = 16,000 KES
          maxDiscountCents: 1000000, // Capped at KES 10,000
          isActive: true,
        },
        pricesIncludeVat: false,
      });

      expect(res.discountCents).toBe(1000000); // Capped at 10,000 KES
      expect(res.netSubtotalCents).toBe(7000000);
    });

    it("rejects inactive or expired coupons", () => {
      expect(() =>
        validateCoupon(
          {
            code: "EXPIRED10",
            type: "percentage",
            value: 10,
            expiresAt: Date.now() - 100000,
            isActive: true,
          },
          100000
        )
      ).toThrow(CouponValidationError);

      expect(() =>
        validateCoupon(
          {
            code: "DISABLED",
            type: "fixed_amount",
            value: 500,
            isActive: false,
          },
          100000
        )
      ).toThrow(CouponValidationError);
    });

    it("enforces minimum spend requirement on coupons", () => {
      expect(() =>
        validateCoupon(
          {
            code: "BIGSPENDER",
            type: "fixed_amount",
            value: 200000,
            minSpendCents: 10000000, // Requires KES 100,000
            isActive: true,
          },
          5000000 // Only KES 50,000 spent
        )
      ).toThrow(CouponValidationError);
    });

    it("allocates coupon discount proportionally across line items without cent loss", () => {
      const res = calculateCartTotals({
        items: sampleItems,
        coupon: {
          code: "PROMO3K",
          type: "fixed_amount",
          value: 300000, // KES 3,000
          isActive: true,
        },
      });

      const totalAllocated = res.items.reduce(
        (sum, item) => sum + item.discountAllocatedCents,
        0
      );
      expect(totalAllocated).toBe(300000);
    });
  });

  describe("Grand Total & Financial Integrity Invariants", () => {
    it("integrates items subtotal, coupon discount, VAT, and county delivery fee", () => {
      const res = calculateCartTotals({
        items: [
          {
            id: "it-1",
            productId: "p1",
            vendorId: "v1",
            title: "Software Suite",
            unitPriceCents: 200000, // KES 2,000
            quantity: 1,
            taxable: true,
          },
        ],
        coupon: {
          code: "SAVE200",
          type: "fixed_amount",
          value: 20000, // KES 200 discount
          isActive: true,
        },
        deliveryCounty: "Nairobi",
        deliverySpeed: "standard",
        pricesIncludeVat: false,
      });

      // Subtotal: 200,000 cents (KES 2,000)
      // Discount: 20,000 cents (KES 200)
      // Net Subtotal: 180,000 cents (KES 1,800)
      // 16% VAT on 1,800 = 28,800 cents (KES 288)
      // Delivery fee Nairobi under 5,000: 25,000 cents (KES 250)
      // Grand total = 180,000 + 28,800 + 25,000 = 233,800 cents (KES 2,338)
      expect(res.subtotalCents).toBe(200000);
      expect(res.discountCents).toBe(20000);
      expect(res.netSubtotalCents).toBe(180000);
      expect(res.vatAmountCents).toBe(28800);
      expect(res.deliveryFeeCents).toBe(25000);
      expect(res.grandTotalCents).toBe(233800);
      expect(res.grandTotalKes).toBe(2338);

      // Invariant check
      expect(res.netSubtotalCents + res.vatAmountCents + res.deliveryFeeCents).toBe(
        res.grandTotalCents
      );
    });
  });
});
