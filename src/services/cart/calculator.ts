/**
 * SoftMarket Kenya — Cart, Kenya VAT 16%, Coupon Discounts & Grand Total Calculator
 */

import {
  addCents,
  allocateCentsByRatios,
  centsToKes,
  formatKES,
  multiplyCents,
  subtractCents,
} from "../../utils/money.js";
import { CouponValidationError } from "../../utils/errors.js";
import { calculateDeliveryFee } from "../delivery/countyMatrix.js";
import type {
  CartCalculationRequest,
  CartCalculationResult,
  CartItem,
  CartLineItemCalculated,
  Coupon,
} from "./types.js";

export const KENYA_STANDARD_VAT_RATE = 0.16; // 16% VAT under Kenya Tax Law

/**
 * Validates a coupon against cart subtotal and parameters.
 */
export function validateCoupon(coupon: Coupon, subtotalCents: number): number {
  if (!coupon.isActive) {
    throw new CouponValidationError(`Coupon code '${coupon.code}' is inactive`, { code: coupon.code });
  }

  if (coupon.expiresAt && Date.now() > coupon.expiresAt) {
    throw new CouponValidationError(`Coupon code '${coupon.code}' has expired`, {
      code: coupon.code,
      expiresAt: coupon.expiresAt,
    });
  }

  if (coupon.minSpendCents && subtotalCents < coupon.minSpendCents) {
    throw new CouponValidationError(
      `Coupon code '${coupon.code}' requires a minimum spend of ${formatKES(coupon.minSpendCents)}`,
      { code: coupon.code, minSpendCents: coupon.minSpendCents, currentSubtotalCents: subtotalCents }
    );
  }

  let discountCents = 0;
  if (coupon.type === "percentage") {
    discountCents = Math.round((subtotalCents * coupon.value) / 100);
  } else if (coupon.type === "fixed_amount") {
    discountCents = coupon.value;
  }

  // Cap discount if coupon has maxDiscountCents
  if (coupon.maxDiscountCents && discountCents > coupon.maxDiscountCents) {
    discountCents = coupon.maxDiscountCents;
  }

  // Discount cannot exceed subtotal
  return Math.min(discountCents, subtotalCents);
}

/**
 * Calculates complete cart financials with Kenya 16% VAT, coupons, and county delivery.
 */
export function calculateCartTotals(req: CartCalculationRequest): CartCalculationResult {
  const items = req.items || [];
  const vatRate = req.vatRate !== undefined ? req.vatRate : KENYA_STANDARD_VAT_RATE;
  const pricesIncludeVat = Boolean(req.pricesIncludeVat);

  let totalQuantity = 0;
  let subtotalCents = 0;
  let totalWeightKg = 0;

  // 1. Calculate raw line item totals
  const lineItemBases: Array<{ item: CartItem; grossTotal: number }> = [];
  for (const item of items) {
    if (item.quantity <= 0) {
      throw new Error(`Invalid item quantity for item ${item.id}: must be >= 1`);
    }
    if (item.unitPriceCents < 0) {
      throw new Error(`Invalid unit price for item ${item.id}: cannot be negative`);
    }

    const grossTotal = multiplyCents(item.unitPriceCents, item.quantity);
    lineItemBases.push({ item, grossTotal });
    subtotalCents = addCents(subtotalCents, grossTotal);
    totalQuantity += item.quantity;
    totalWeightKg += (item.weightKg || 0.5) * item.quantity;
  }

  // 2. Validate and calculate coupon discount
  let discountCents = 0;
  if (req.coupon) {
    discountCents = validateCoupon(req.coupon, subtotalCents);
  }

  const netSubtotalCents = Math.max(0, subtractCents(subtotalCents, discountCents));

  // 3. Allocate discount proportionally to line items without losing cents
  let discountAllocations: number[] = [];
  if (discountCents > 0 && lineItemBases.length > 0) {
    discountAllocations = allocateCentsByRatios(
      discountCents,
      lineItemBases.map((b) => b.grossTotal)
    );
  } else {
    discountAllocations = lineItemBases.map(() => 0);
  }

  // 4. Calculate VAT per line item and total VAT
  let vatAmountCents = 0;
  const calculatedItems: CartLineItemCalculated[] = [];

  for (let i = 0; i < lineItemBases.length; i++) {
    const { item, grossTotal } = lineItemBases[i];
    const discountAllocated = discountAllocations[i] || 0;
    const netLineTotal = Math.max(0, subtractCents(grossTotal, discountAllocated));
    const isTaxable = item.taxable !== false; // default true

    let itemVat = 0;
    if (isTaxable) {
      if (pricesIncludeVat) {
        // Net = Gross / (1 + vatRate), VAT = Gross - Net
        const netExcludingVat = Math.round(netLineTotal / (1 + vatRate));
        itemVat = subtractCents(netLineTotal, netExcludingVat);
      } else {
        // VAT = Net * vatRate
        itemVat = Math.round(netLineTotal * vatRate);
      }
    }

    vatAmountCents = addCents(vatAmountCents, itemVat);

    calculatedItems.push({
      item,
      grossLineTotalCents: grossTotal,
      discountAllocatedCents: discountAllocated,
      netLineTotalCents: netLineTotal,
      vatAmountCents: itemVat,
      finalLineTotalCents: pricesIncludeVat ? netLineTotal : addCents(netLineTotal, itemVat),
    });
  }

  // 5. Calculate delivery fee if county provided
  let deliveryFeeCents = 0;
  let deliveryDetails: CartCalculationResult["deliveryDetails"];

  if (req.deliveryCounty) {
    const deliveryRes = calculateDeliveryFee({
      county: req.deliveryCounty,
      orderSubtotalCents: subtotalCents,
      weightKg: totalWeightKg,
      speed: req.deliverySpeed || "standard",
    });
    deliveryFeeCents = deliveryRes.finalFeeCents;
    deliveryDetails = {
      county: req.deliveryCounty,
      zoneName: deliveryRes.zoneName,
      isFree: deliveryRes.isFreeDelivery,
    };
  }

  // 6. Grand Total
  // If prices include VAT: grandTotal = netSubtotal + deliveryFee
  // If prices exclude VAT: grandTotal = netSubtotal + vatAmount + deliveryFee
  const grandTotalCents = pricesIncludeVat
    ? addCents(netSubtotalCents, deliveryFeeCents)
    : addCents(netSubtotalCents, vatAmountCents, deliveryFeeCents);

  return {
    items: calculatedItems,
    totalQuantity,
    subtotalCents,
    discountCents,
    netSubtotalCents,
    vatRate,
    vatAmountCents,
    deliveryFeeCents,
    deliveryDetails,
    grandTotalCents,
    grandTotalKes: centsToKes(grandTotalCents),
    formattedSubtotal: formatKES(subtotalCents),
    formattedDiscount: formatKES(discountCents),
    formattedVat: formatKES(vatAmountCents),
    formattedDelivery: deliveryDetails?.isFree ? "FREE" : formatKES(deliveryFeeCents),
    formattedGrandTotal: formatKES(grandTotalCents),
  };
}
