/**
 * SoftMarket Kenya — Vendor Commission Splitting & Payout Engine
 */

import {
  addCents,
  centsToKes,
  formatKES,
  kesToCents,
  subtractCents,
} from "../../utils/money.js";
import type {
  OrderPayoutSplitResult,
  VendorCommissionRule,
  VendorItemSale,
  VendorPayoutBreakdown,
} from "./types.js";

/**
 * Safaricom B2C (Business to Customer) tariff fee table for disbursements in KES.
 */
export function getMpesaB2cDisbursementFeeCents(amountCents: number): number {
  const amountKes = centsToKes(amountCents);

  if (amountKes < 10) return 0;
  if (amountKes <= 100) return kesToCents(0); // Free for <= 100
  if (amountKes <= 500) return kesToCents(15.66);
  if (amountKes <= 1000) return kesToCents(22.40);
  if (amountKes <= 1500) return kesToCents(25.75);
  if (amountKes <= 2500) return kesToCents(30.22);
  if (amountKes <= 3500) return kesToCents(35.82);
  if (amountKes <= 5000) return kesToCents(45.00);
  if (amountKes <= 7500) return kesToCents(55.00);
  if (amountKes <= 10000) return kesToCents(65.00);
  if (amountKes <= 15000) return kesToCents(75.00);
  if (amountKes <= 20000) return kesToCents(85.00);
  if (amountKes <= 50000) return kesToCents(105.00);
  return kesToCents(120.00); // 50,001 - 250,000
}

/**
 * Standard default commission rules for marketplace categories.
 */
export const DEFAULT_COMMISSION_RULES: Record<string, VendorCommissionRule> = {
  software: {
    category: "software",
    commissionRate: 8, // 8%
    minFeeCents: kesToCents(100),
    withholdingTaxRate: 5, // 5% WHT
    deductMpesaB2cFee: true,
  },
  hardware: {
    category: "hardware",
    commissionRate: 12, // 12%
    minFeeCents: kesToCents(50),
    withholdingTaxRate: 0,
    deductMpesaB2cFee: true,
  },
  services: {
    category: "services",
    commissionRate: 15, // 15%
    minFeeCents: kesToCents(200),
    withholdingTaxRate: 5,
    deductMpesaB2cFee: true,
  },
  default: {
    category: "default",
    commissionRate: 10, // 10%
    minFeeCents: kesToCents(50),
    withholdingTaxRate: 0,
    deductMpesaB2cFee: true,
  },
};

/**
 * Calculates multi-vendor commission splits and net payouts for an order.
 */
export function calculateOrderPayoutSplits(params: {
  orderId: string;
  items: VendorItemSale[];
  deliveryFeeCents?: number;
  customRules?: Record<string, VendorCommissionRule>;
}): OrderPayoutSplitResult {
  const { orderId, items } = params;
  const deliveryFeeCents = params.deliveryFeeCents || 0;
  const rules = { ...DEFAULT_COMMISSION_RULES, ...params.customRules };

  // Group items by vendorId
  const vendorGroups = new Map<string, VendorItemSale[]>();
  for (const item of items) {
    const list = vendorGroups.get(item.vendorId) || [];
    list.push(item);
    vendorGroups.set(item.vendorId, list);
  }

  const vendors: VendorPayoutBreakdown[] = [];
  let totalPlatformCommissionCents = 0;
  let totalWithholdingTaxCents = 0;
  let totalMpesaDisbursementFeesCents = 0;
  let totalMerchantPayoutsCents = 0;
  let totalItemSalesCents = 0;

  for (const [vendorId, vendorItems] of vendorGroups.entries()) {
    let grossVendorCents = 0;
    let vendorCommissionCents = 0;
    let vendorWhtCents = 0;
    const vendorName = vendorItems[0]?.vendorName || `Vendor-${vendorId}`;

    for (const item of vendorItems) {
      grossVendorCents = addCents(grossVendorCents, item.grossAmountCents);
      const cat = (item.category || "").toLowerCase();
      const rule = rules[cat] || rules[vendorId] || rules.default;

      let itemCommission = Math.round((item.grossAmountCents * rule.commissionRate) / 100);
      if (rule.minFeeCents && itemCommission < rule.minFeeCents) {
        itemCommission = Math.min(rule.minFeeCents, item.grossAmountCents);
      }
      if (rule.maxFeeCents && itemCommission > rule.maxFeeCents) {
        itemCommission = rule.maxFeeCents;
      }

      let itemWht = 0;
      if (rule.withholdingTaxRate && rule.withholdingTaxRate > 0) {
        // WHT on commission fee
        itemWht = Math.round((itemCommission * rule.withholdingTaxRate) / 100);
      }

      vendorCommissionCents = addCents(vendorCommissionCents, itemCommission);
      vendorWhtCents = addCents(vendorWhtCents, itemWht);
    }

    totalItemSalesCents = addCents(totalItemSalesCents, grossVendorCents);

    // Calculate gross payout before B2C fee
    const grossPayoutBeforeB2c = Math.max(
      0,
      subtractCents(grossVendorCents, addCents(vendorCommissionCents, vendorWhtCents))
    );

    // M-Pesa B2C fee on the payout
    const b2cFeeCents = getMpesaB2cDisbursementFeeCents(grossPayoutBeforeB2c);
    const netMerchantPayoutCents = Math.max(0, subtractCents(grossPayoutBeforeB2c, b2cFeeCents));

    totalPlatformCommissionCents = addCents(totalPlatformCommissionCents, vendorCommissionCents);
    totalWithholdingTaxCents = addCents(totalWithholdingTaxCents, vendorWhtCents);
    totalMpesaDisbursementFeesCents = addCents(totalMpesaDisbursementFeesCents, b2cFeeCents);
    totalMerchantPayoutsCents = addCents(totalMerchantPayoutsCents, netMerchantPayoutCents);

    const effectiveRate =
      grossVendorCents > 0
        ? Math.round((vendorCommissionCents / grossVendorCents) * 10000) / 100
        : 0;

    vendors.push({
      vendorId,
      vendorName,
      itemCount: vendorItems.length,
      grossSalesCents: grossVendorCents,
      platformCommissionRate: effectiveRate,
      platformCommissionCents: vendorCommissionCents,
      withholdingTaxCents: vendorWhtCents,
      mpesaB2cDisbursementFeeCents: b2cFeeCents,
      netMerchantPayoutCents,
      netMerchantPayoutKes: centsToKes(netMerchantPayoutCents),
      formattedGrossSales: formatKES(grossVendorCents),
      formattedCommission: formatKES(vendorCommissionCents),
      formattedNetPayout: formatKES(netMerchantPayoutCents),
    });
  }

  const customerTotalCents = addCents(totalItemSalesCents, deliveryFeeCents);
  const accountedTotal = addCents(
    totalMerchantPayoutsCents,
    totalPlatformCommissionCents,
    totalWithholdingTaxCents,
    totalMpesaDisbursementFeesCents,
    deliveryFeeCents
  );
  const difference = customerTotalCents - accountedTotal;

  return {
    orderId,
    customerTotalCents,
    deliveryFeeCents,
    vendors,
    totalPlatformCommissionCents,
    totalWithholdingTaxCents,
    totalMpesaDisbursementFeesCents,
    totalMerchantPayoutsCents,
    zeroLeakageCheck: {
      customerTotal: customerTotalCents,
      accountedTotal,
      difference,
      isValid: difference === 0,
    },
  };
}
