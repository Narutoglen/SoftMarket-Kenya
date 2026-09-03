/**
 * SoftMarket Kenya — Vendor Commission & Payout Types
 */

export interface VendorItemSale {
  productId: string;
  vendorId: string;
  vendorName?: string;
  category?: string;
  title: string;
  grossAmountCents: number;
  quantity: number;
}

export interface VendorCommissionRule {
  vendorId?: string; // Specific vendor override or default
  category?: string; // e.g. "software", "hardware", "consulting"
  commissionRate: number; // e.g. 10 for 10%
  minFeeCents?: number; // Minimum platform fee in cents (e.g. 5000 for KES 50)
  maxFeeCents?: number; // Cap on platform fee
  withholdingTaxRate?: number; // e.g. 5 for 5% WHT on professional services
  deductMpesaB2cFee?: boolean; // Whether to deduct Safaricom B2C fee from merchant
}

export interface VendorPayoutBreakdown {
  vendorId: string;
  vendorName: string;
  itemCount: number;
  grossSalesCents: number;
  platformCommissionRate: number;
  platformCommissionCents: number;
  withholdingTaxCents: number;
  mpesaB2cDisbursementFeeCents: number;
  netMerchantPayoutCents: number;
  netMerchantPayoutKes: number;
  formattedGrossSales: string;
  formattedCommission: string;
  formattedNetPayout: string;
}

export interface OrderPayoutSplitResult {
  orderId: string;
  customerTotalCents: number;
  deliveryFeeCents: number;
  vendors: VendorPayoutBreakdown[];
  totalPlatformCommissionCents: number;
  totalWithholdingTaxCents: number;
  totalMpesaDisbursementFeesCents: number;
  totalMerchantPayoutsCents: number;
  zeroLeakageCheck: {
    customerTotal: number;
    accountedTotal: number;
    difference: number;
    isValid: boolean;
  };
}
