import { describe, it, expect } from "vitest";
import {
  calculateOrderPayoutSplits,
  getMpesaB2cDisbursementFeeCents,
  DEFAULT_COMMISSION_RULES,
} from "../src/services/payouts/index.js";
import { centsToKes, kesToCents } from "../src/utils/money.js";

describe("Vendor Commission Splitting & Payout Engine", () => {
  describe("M-Pesa B2C Tariff Deduction Table", () => {
    it("returns correct Safaricom B2C fee across transaction bands", () => {
      // Under 10 KES -> 0
      expect(getMpesaB2cDisbursementFeeCents(kesToCents(5))).toBe(0);

      // 10 - 100 KES -> 0 KES
      expect(getMpesaB2cDisbursementFeeCents(kesToCents(100))).toBe(0);

      // 101 - 500 KES -> 15.66 KES
      expect(getMpesaB2cDisbursementFeeCents(kesToCents(250))).toBe(kesToCents(15.66));

      // 501 - 1000 KES -> 22.40 KES
      expect(getMpesaB2cDisbursementFeeCents(kesToCents(750))).toBe(kesToCents(22.40));

      // 10,001 - 15,000 KES -> 75.00 KES
      expect(getMpesaB2cDisbursementFeeCents(kesToCents(12000))).toBe(kesToCents(75.00));

      // 50,001 - 250,000 KES -> 120.00 KES
      expect(getMpesaB2cDisbursementFeeCents(kesToCents(100000))).toBe(kesToCents(120.00));
    });
  });

  describe("Single Vendor Order Payout Calculation", () => {
    it("calculates 8% software commission and 5% WHT for software sales", () => {
      const order = {
        orderId: "ORD-VEND-1",
        items: [
          {
            productId: "prod-sw-1",
            vendorId: "vendor-soft-corp",
            vendorName: "SoftCorp Ltd",
            category: "software",
            title: "ERP License",
            grossAmountCents: 10000000, // KES 100,000
            quantity: 1,
          },
        ],
        deliveryFeeCents: 0,
      };

      const res = calculateOrderPayoutSplits(order);

      // 8% of 100,000 = 8,000 KES (800,000 cents) platform commission
      // 5% WHT on 8,000 commission = 400 KES (40,000 cents) WHT
      // Total platform fees = 8,000 + 400 = 8,400 KES
      // Gross vendor payout before B2C fee = 100,000 - 8,400 = 91,600 KES
      // B2C fee for 91,600 KES (50,001 - 250,000 band) = 120 KES (12,000 cents)
      // Net Merchant Payout = 91,600 - 120 = 91,480 KES (9,148,000 cents)
      expect(res.vendors.length).toBe(1);
      const v = res.vendors[0];
      expect(v.grossSalesCents).toBe(10000000);
      expect(v.platformCommissionCents).toBe(800000);
      expect(v.withholdingTaxCents).toBe(40000);
      expect(v.mpesaB2cDisbursementFeeCents).toBe(12000);
      expect(v.netMerchantPayoutCents).toBe(9148000);
      expect(v.netMerchantPayoutKes).toBe(91480);
      expect(res.zeroLeakageCheck.isValid).toBe(true);
    });
  });

  describe("Multi-Vendor Order Splitting & Zero-Leakage Invariant", () => {
    it("splits multi-vendor order across 3 vendors with different categories and preserves balance invariant", () => {
      const order = {
        orderId: "ORD-MULTI-999",
        items: [
          // Vendor A: Software (8% commission + 5% WHT)
          {
            productId: "p-crm",
            vendorId: "vendor-A",
            vendorName: "SaaS Devs",
            category: "software",
            title: "CRM Custom Module",
            grossAmountCents: 5000000, // KES 50,000
            quantity: 1,
          },
          // Vendor B: Hardware (12% commission, 0% WHT)
          {
            productId: "p-hw",
            vendorId: "vendor-B",
            vendorName: "Hardware Shop",
            category: "hardware",
            title: "Barcode Scanner",
            grossAmountCents: 1500000, // KES 15,000
            quantity: 1,
          },
          // Vendor C: Services / Consulting (15% commission + 5% WHT)
          {
            productId: "p-svc",
            vendorId: "vendor-C",
            vendorName: "Dan Advisory",
            category: "services",
            title: "Security Audit",
            grossAmountCents: 3500000, // KES 35,000
            quantity: 1,
          },
        ],
        deliveryFeeCents: 50000, // KES 500 delivery fee
      };

      const res = calculateOrderPayoutSplits(order);

      // Customer Total: 50,000 + 15,000 + 35,000 + 500 = 100,500 KES (10,050,000 cents)
      expect(res.customerTotalCents).toBe(10050000);
      expect(res.vendors.length).toBe(3);

      // Verify zero-leakage check: Customer Total === Sum(Merchant Payouts) + Sum(Commissions) + Sum(WHT) + Sum(Disbursement Fees) + Delivery Fee
      expect(res.zeroLeakageCheck.isValid).toBe(true);
      expect(res.zeroLeakageCheck.difference).toBe(0);
      expect(res.zeroLeakageCheck.accountedTotal).toBe(res.customerTotalCents);
    });

    it("enforces minimum platform commission fee on small transactions", () => {
      const order = {
        orderId: "ORD-MIN-FEE",
        items: [
          {
            productId: "p-small",
            vendorId: "vendor-small",
            vendorName: "Small Shop",
            category: "default",
            title: "Cable Adapter",
            grossAmountCents: 20000, // KES 200 (10% would be KES 20, but min fee is KES 50)
            quantity: 1,
          },
        ],
      };

      const res = calculateOrderPayoutSplits(order);
      const v = res.vendors[0];
      // Min fee is KES 50 = 5,000 cents
      expect(v.platformCommissionCents).toBe(5000);
      expect(res.zeroLeakageCheck.isValid).toBe(true);
    });
  });
});
