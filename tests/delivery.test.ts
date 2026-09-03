import { describe, it, expect } from "vitest";
import {
  getZoneForCounty,
  calculateDeliveryFee,
  normalizeCountyName,
  DELIVERY_ZONES,
} from "../src/services/delivery/index.js";
import { DeliveryZoneNotFoundError } from "../src/utils/errors.js";

describe("47 Kenyan County Delivery Matrix & Pricing", () => {
  describe("Zone Classification & County Mapping", () => {
    it("maps Nairobi to Zone 1 (Metro)", () => {
      const zone = getZoneForCounty("Nairobi");
      expect(zone.id).toBe("zone_1_nairobi_metro");
      expect(zone.baseFeeCents).toBe(25000); // KES 250
      expect(zone.freeDeliveryThresholdCents).toBe(500000); // KES 5,000
    });

    it("maps Central & Nairobi Environs to Zone 2 (Kiambu, Machakos, Kajiado, Nyeri)", () => {
      expect(getZoneForCounty("Kiambu").id).toBe("zone_2_nairobi_environs");
      expect(getZoneForCounty("Machakos").id).toBe("zone_2_nairobi_environs");
      expect(getZoneForCounty("Kajiado").id).toBe("zone_2_nairobi_environs");
      expect(getZoneForCounty("Nyeri").id).toBe("zone_2_nairobi_environs");
      expect(getZoneForCounty("Murang'a").id).toBe("zone_2_nairobi_environs");
    });

    it("maps Major Town counties to Zone 3 (Nakuru, Uasin Gishu, Kisumu, Kakamega, Meru)", () => {
      expect(getZoneForCounty("Nakuru").id).toBe("zone_3_major_towns");
      expect(getZoneForCounty("Uasin Gishu").id).toBe("zone_3_major_towns");
      expect(getZoneForCounty("Kisumu").id).toBe("zone_3_major_towns");
      expect(getZoneForCounty("Kakamega").id).toBe("zone_3_major_towns");
      expect(getZoneForCounty("Meru").id).toBe("zone_3_major_towns");
      expect(getZoneForCounty("Kisii").id).toBe("zone_3_major_towns");
    });

    it("maps Coast & Eastern Hubs to Zone 4 (Mombasa, Kilifi, Kwale, Lamu)", () => {
      expect(getZoneForCounty("Mombasa").id).toBe("zone_4_coast_and_lake");
      expect(getZoneForCounty("Kilifi").id).toBe("zone_4_coast_and_lake");
      expect(getZoneForCounty("Kwale").id).toBe("zone_4_coast_and_lake");
      expect(getZoneForCounty("Lamu").id).toBe("zone_4_coast_and_lake");
    });

    it("maps Frontier / Northern counties to Zone 5 (Garissa, Wajir, Mandera, Turkana, Marsabit)", () => {
      expect(getZoneForCounty("Garissa").id).toBe("zone_5_remote_arid");
      expect(getZoneForCounty("Wajir").id).toBe("zone_5_remote_arid");
      expect(getZoneForCounty("Mandera").id).toBe("zone_5_remote_arid");
      expect(getZoneForCounty("Turkana").id).toBe("zone_5_remote_arid");
      expect(getZoneForCounty("Marsabit").id).toBe("zone_5_remote_arid");
    });

    it("handles common aliases and case-insensitive names", () => {
      expect(getZoneForCounty("eldoret").id).toBe("zone_3_major_towns");
      expect(getZoneForCounty("THIKA").id).toBe("zone_2_nairobi_environs");
      expect(getZoneForCounty("Mombasa County").id).toBe("zone_4_coast_and_lake");
      expect(getZoneForCounty("NAIROBI COUNTY").id).toBe("zone_1_nairobi_metro");
    });

    it("throws DeliveryZoneNotFoundError on empty or unknown county", () => {
      expect(() => getZoneForCounty("")).toThrow(DeliveryZoneNotFoundError);
      expect(() => getZoneForCounty("Atlantis")).toThrow(DeliveryZoneNotFoundError);
    });
  });

  describe("calculateDeliveryFee", () => {
    it("calculates standard delivery fee for Nairobi under threshold", () => {
      const res = calculateDeliveryFee({
        county: "Nairobi",
        orderSubtotalCents: 200000, // KES 2,000 (under KES 5,000 threshold)
      });

      expect(res.finalFeeCents).toBe(25000); // KES 250
      expect(res.isFreeDelivery).toBe(false);
      expect(res.formattedFee).toContain("250");
    });

    it("applies free delivery when subtotal meets threshold in qualifying zones", () => {
      // Nairobi free over KES 5,000
      const nairobiFree = calculateDeliveryFee({
        county: "Nairobi",
        orderSubtotalCents: 550000, // KES 5,500
        speed: "standard",
      });
      expect(nairobiFree.isFreeDelivery).toBe(true);
      expect(nairobiFree.finalFeeCents).toBe(0);
      expect(nairobiFree.formattedFee).toBe("FREE");

      // Kiambu free over KES 8,000
      const kiambuFree = calculateDeliveryFee({
        county: "Kiambu",
        orderSubtotalCents: 850000, // KES 8,500
        speed: "standard",
      });
      expect(kiambuFree.isFreeDelivery).toBe(true);
      expect(kiambuFree.finalFeeCents).toBe(0);
    });

    it("does not apply free delivery in Zone 5 (Remote)", () => {
      const garissa = calculateDeliveryFee({
        county: "Garissa",
        orderSubtotalCents: 5000000, // KES 50,000
      });
      expect(garissa.isFreeDelivery).toBe(false);
      expect(garissa.finalFeeCents).toBe(120000); // KES 1,200
    });

    it("calculates express delivery surcharge", () => {
      const expressNairobi = calculateDeliveryFee({
        county: "Nairobi",
        orderSubtotalCents: 100000,
        speed: "express",
      });
      // Base: 250 KES, Express (1.5x) = 375 KES
      expect(expressNairobi.finalFeeCents).toBe(37500);
      expect(expressNairobi.speedSurchargeCents).toBe(12500);
    });

    it("calculates same-day delivery in Nairobi", () => {
      const sameDay = calculateDeliveryFee({
        county: "Nairobi",
        orderSubtotalCents: 100000,
        speed: "same_day",
      });
      expect(sameDay.finalFeeCents).toBe(45000); // KES 450
      expect(sameDay.estimatedHoursMin).toBe(2);
      expect(sameDay.estimatedHoursMax).toBe(8);
    });

    it("throws error when requesting same-day delivery in non-supported zone", () => {
      expect(() =>
        calculateDeliveryFee({
          county: "Kisumu",
          orderSubtotalCents: 100000,
          speed: "same_day",
        })
      ).toThrow("Same-day delivery is not available");
    });

    it("calculates weight surcharge for heavy packages exceeding 5kg base", () => {
      // 8kg package to Nakuru (Zone 3) -> 3kg extra at KES 70/kg = KES 210 surcharge
      const heavyRes = calculateDeliveryFee({
        county: "Nakuru",
        orderSubtotalCents: 100000,
        weightKg: 8,
        speed: "standard",
      });

      const baseFee = 65000; // KES 650
      const expectedWeightSurcharge = 3 * 7000; // KES 210 = 21,000 cents
      expect(heavyRes.weightSurchargeCents).toBe(expectedWeightSurcharge);
      expect(heavyRes.finalFeeCents).toBe(baseFee + expectedWeightSurcharge);
    });
  });
});
