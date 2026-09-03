/**
 * SoftMarket Kenya — 47 County Delivery Matrix & Pricing Engine
 */

import { kesToCents, centsToKes, formatKES } from "../../utils/money.js";
import { DeliveryZoneNotFoundError } from "../../utils/errors.js";
import type {
  DeliveryCalculationRequest,
  DeliveryCalculationResult,
  DeliverySpeed,
  DeliveryZoneConfig,
  DeliveryZoneId,
} from "./types.js";

export const DELIVERY_ZONES: Record<DeliveryZoneId, DeliveryZoneConfig> = {
  zone_1_nairobi_metro: {
    id: "zone_1_nairobi_metro",
    name: "Nairobi Metropolitan Area",
    counties: ["Nairobi"],
    baseFeeCents: kesToCents(250), // KES 250
    freeDeliveryThresholdCents: kesToCents(5000), // Free delivery over KES 5,000
    estimatedHoursMin: 2,
    estimatedHoursMax: 24,
    expressMultiplier: 1.5,
    sameDayAvailable: true,
    sameDayFeeCents: kesToCents(450),
    extraWeightRatePerKgCents: kesToCents(30),
  },
  zone_2_nairobi_environs: {
    id: "zone_2_nairobi_environs",
    name: "Central & Nairobi Environs",
    counties: ["Kiambu", "Machakos", "Kajiado", "Murang'a", "Nyeri", "Kirinyaga", "Nyandarua"],
    baseFeeCents: kesToCents(450), // KES 450
    freeDeliveryThresholdCents: kesToCents(8000),
    estimatedHoursMin: 24,
    estimatedHoursMax: 48,
    expressMultiplier: 1.4,
    sameDayAvailable: false,
    extraWeightRatePerKgCents: kesToCents(50),
  },
  zone_3_major_towns: {
    id: "zone_3_major_towns",
    name: "Rift Valley, Western & Mount Kenya",
    counties: [
      "Nakuru",
      "Uasin Gishu",
      "Kisumu",
      "Kakamega",
      "Kisii",
      "Meru",
      "Embu",
      "Laikipia",
      "Kericho",
      "Bomet",
      "Trans Nzoia",
      "Bungoma",
      "Nandi",
      "Homa Bay",
      "Migori",
      "Siaya",
      "Busia",
      "Vihiga",
      "Nyamira",
      "Baringo",
      "Narok",
    ],
    baseFeeCents: kesToCents(650), // KES 650
    freeDeliveryThresholdCents: kesToCents(12000),
    estimatedHoursMin: 48,
    estimatedHoursMax: 72,
    expressMultiplier: 1.35,
    sameDayAvailable: false,
    extraWeightRatePerKgCents: kesToCents(70),
  },
  zone_4_coast_and_lake: {
    id: "zone_4_coast_and_lake",
    name: "Coast & Eastern Hubs",
    counties: ["Mombasa", "Kilifi", "Kwale", "Taita-Taveta", "Kitui", "Makueni", "Tharaka-Nithi", "Lamu"],
    baseFeeCents: kesToCents(750), // KES 750
    freeDeliveryThresholdCents: kesToCents(15000),
    estimatedHoursMin: 48,
    estimatedHoursMax: 96,
    expressMultiplier: 1.35,
    sameDayAvailable: false,
    extraWeightRatePerKgCents: kesToCents(80),
  },
  zone_5_remote_arid: {
    id: "zone_5_remote_arid",
    name: "Northern & Frontier Counties",
    counties: [
      "Garissa",
      "Wajir",
      "Mandera",
      "Marsabit",
      "Turkana",
      "Isiolo",
      "Samburu",
      "West Pokot",
      "Elgeyo-Marakwet",
      "Tana River",
    ],
    baseFeeCents: kesToCents(1200), // KES 1,200
    freeDeliveryThresholdCents: undefined, // No free delivery in remote zones
    estimatedHoursMin: 72,
    estimatedHoursMax: 144,
    expressMultiplier: 1.3,
    sameDayAvailable: false,
    extraWeightRatePerKgCents: kesToCents(120),
  },
};

/**
 * Normalizes county name for comparison.
 */
export function normalizeCountyName(county: string): string {
  if (!county) return "";
  return county
    .trim()
    .toLowerCase()
    .replace(/county/g, "")
    .replace(/[^a-z0-9]/g, "");
}

/**
 * Resolves the delivery zone for any Kenyan county name (case-insensitive, alias-friendly).
 */
export function getZoneForCounty(county: string): DeliveryZoneConfig {
  const normalizedInput = normalizeCountyName(county);
  if (!normalizedInput) {
    throw new DeliveryZoneNotFoundError("County name cannot be empty");
  }

  for (const zone of Object.values(DELIVERY_ZONES)) {
    for (const c of zone.counties) {
      if (normalizeCountyName(c) === normalizedInput) {
        return zone;
      }
    }
  }

  // Common aliases
  if (normalizedInput === "eldoret") return DELIVERY_ZONES.zone_3_major_towns;
  if (normalizedInput === "thika") return DELIVERY_ZONES.zone_2_nairobi_environs;
  if (normalizedInput === "malindi") return DELIVERY_ZONES.zone_4_coast_and_lake;
  if (normalizedInput === "naivasha") return DELIVERY_ZONES.zone_3_major_towns;
  if (normalizedInput === "rongai" || normalizedInput === "kitengela" || normalizedInput === "ngong") {
    return DELIVERY_ZONES.zone_2_nairobi_environs;
  }

  throw new DeliveryZoneNotFoundError(`Delivery zone not configured for county: ${county}`, { county });
}

/**
 * Calculates delivery fee based on county, speed, weight, and cart subtotal.
 */
export function calculateDeliveryFee(req: DeliveryCalculationRequest): DeliveryCalculationResult {
  const zone = getZoneForCounty(req.county);
  const speed: DeliverySpeed = req.speed || "standard";
  const weightKg = req.weightKg !== undefined ? Math.max(0, req.weightKg) : 1;
  const subtotalCents = Math.max(0, req.orderSubtotalCents || 0);

  // Check free delivery threshold on standard delivery
  const isFreeEligible =
    speed === "standard" &&
    zone.freeDeliveryThresholdCents !== undefined &&
    subtotalCents >= zone.freeDeliveryThresholdCents;

  let baseFee = zone.baseFeeCents;
  let speedSurcharge = 0;
  let weightSurcharge = 0;
  let estMin = zone.estimatedHoursMin;
  let estMax = zone.estimatedHoursMax;

  // Weight surcharge for weight above 5kg base threshold
  const BASE_WEIGHT_KG = 5;
  if (weightKg > BASE_WEIGHT_KG) {
    const extraKg = Math.ceil(weightKg - BASE_WEIGHT_KG);
    weightSurcharge = extraKg * zone.extraWeightRatePerKgCents;
  }

  if (speed === "same_day") {
    if (!zone.sameDayAvailable) {
      throw new Error(`Same-day delivery is not available for ${zone.name}`);
    }
    baseFee = zone.sameDayFeeCents || baseFee * 1.8;
    estMin = 2;
    estMax = 8;
  } else if (speed === "express") {
    speedSurcharge = Math.round(baseFee * (zone.expressMultiplier - 1));
    estMin = Math.max(1, Math.round(zone.estimatedHoursMin * 0.5));
    estMax = Math.max(2, Math.round(zone.estimatedHoursMax * 0.6));
  }

  let finalFeeCents = 0;
  if (!isFreeEligible) {
    finalFeeCents = baseFee + speedSurcharge + weightSurcharge;
  }

  return {
    zoneId: zone.id,
    zoneName: zone.name,
    county: req.county,
    baseFeeCents: baseFee,
    speed,
    speedSurchargeCents: speedSurcharge,
    weightSurchargeCents: weightSurcharge,
    isFreeDelivery: isFreeEligible,
    finalFeeCents,
    finalFeeKes: centsToKes(finalFeeCents),
    estimatedHoursMin: estMin,
    estimatedHoursMax: estMax,
    formattedFee: isFreeEligible ? "FREE" : formatKES(finalFeeCents),
  };
}
