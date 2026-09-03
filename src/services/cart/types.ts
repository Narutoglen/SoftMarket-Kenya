/**
 * SoftMarket Kenya — Cart & Pricing Engine Types
 */

export interface CartItem {
  id: string;
  productId: string;
  vendorId: string;
  title: string;
  unitPriceCents: number;
  quantity: number;
  taxable?: boolean; // Default true (16% VAT), false if zero-rated/exempt
  weightKg?: number;
}

export type CouponType = "percentage" | "fixed_amount";

export interface Coupon {
  code: string;
  type: CouponType;
  value: number; // Percentage (e.g. 10 for 10%) or Fixed Cents (e.g. 50000 for KES 500)
  minSpendCents?: number;
  maxDiscountCents?: number;
  expiresAt?: number;
  isActive: boolean;
  applicableVendorIds?: string[];
  applicableProductIds?: string[];
}

export interface CartCalculationRequest {
  items: CartItem[];
  coupon?: Coupon;
  deliveryCounty?: string;
  deliverySpeed?: "standard" | "express" | "same_day";
  vatRate?: number; // Default 0.16 (16% standard VAT Kenya)
  pricesIncludeVat?: boolean; // Default false (VAT added on top) or true (VAT extracted)
}

export interface CartLineItemCalculated {
  item: CartItem;
  grossLineTotalCents: number;
  discountAllocatedCents: number;
  netLineTotalCents: number;
  vatAmountCents: number;
  finalLineTotalCents: number;
}

export interface CartCalculationResult {
  items: CartLineItemCalculated[];
  totalQuantity: number;
  subtotalCents: number;
  discountCents: number;
  netSubtotalCents: number; // subtotal - discount
  vatRate: number;
  vatAmountCents: number;
  deliveryFeeCents: number;
  deliveryDetails?: {
    county: string;
    zoneName: string;
    isFree: boolean;
  };
  grandTotalCents: number;
  grandTotalKes: number;
  formattedSubtotal: string;
  formattedDiscount: string;
  formattedVat: string;
  formattedDelivery: string;
  formattedGrandTotal: string;
}
