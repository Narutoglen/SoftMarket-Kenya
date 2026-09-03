/**
 * SoftMarket Kenya — Delivery Zone & County Types
 */

export type DeliveryZoneId =
  | "zone_1_nairobi_metro"
  | "zone_2_nairobi_environs"
  | "zone_3_major_towns"
  | "zone_4_coast_and_lake"
  | "zone_5_remote_arid";

export type DeliverySpeed = "standard" | "express" | "same_day";

export interface DeliveryZoneConfig {
  id: DeliveryZoneId;
  name: string;
  counties: string[];
  baseFeeCents: number; // Base fee in integer cents
  freeDeliveryThresholdCents?: number; // Order amount above which standard delivery is free
  estimatedHoursMin: number;
  estimatedHoursMax: number;
  expressMultiplier: number;
  sameDayAvailable: boolean;
  sameDayFeeCents?: number;
  extraWeightRatePerKgCents: number; // For packages exceeding 5kg base weight
}

export interface DeliveryCalculationRequest {
  county: string;
  subCountyOrTown?: string;
  orderSubtotalCents: number;
  weightKg?: number;
  speed?: DeliverySpeed;
}

export interface DeliveryCalculationResult {
  zoneId: DeliveryZoneId;
  zoneName: string;
  county: string;
  baseFeeCents: number;
  speed: DeliverySpeed;
  speedSurchargeCents: number;
  weightSurchargeCents: number;
  isFreeDelivery: boolean;
  finalFeeCents: number;
  finalFeeKes: number;
  estimatedHoursMin: number;
  estimatedHoursMax: number;
  formattedFee: string;
}
