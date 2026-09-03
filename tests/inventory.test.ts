import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  InventoryManager,
  DEFAULT_HOLD_DURATION_MS,
} from "../src/services/inventory/index.js";
import {
  InventoryShortfallError,
  InventoryReservationExpiredError,
} from "../src/utils/errors.js";

describe("Inventory Stock Locking, Reservation & Concurrency Engine", () => {
  let inventory: InventoryManager;

  beforeEach(() => {
    inventory = new InventoryManager();
    inventory.setStock({
      productId: "prod-laptop",
      title: "Dev Laptop Pro",
      quantity: 5,
    });
    inventory.setStock({
      productId: "prod-monitor",
      title: "4K Monitor 27inch",
      quantity: 10,
    });
  });

  describe("Stock Setup & Level Queries", () => {
    it("initializes stock levels accurately", () => {
      const laptop = inventory.getStockLevel("prod-laptop");
      expect(laptop).toBeDefined();
      expect(laptop!.totalQuantity).toBe(5);
      expect(laptop!.reservedQuantity).toBe(0);
      expect(laptop!.availableQuantity).toBe(5);
    });

    it("returns undefined for non-existent products", () => {
      expect(inventory.getStockLevel("non-existent")).toBeUndefined();
    });
  });

  describe("Stock Reservation & Locking", () => {
    it("reserves stock and decreases available quantity", () => {
      const reservation = inventory.reserveStock({
        reservationId: "res-001",
        orderId: "ord-001",
        items: [{ productId: "prod-laptop", quantity: 2 }],
      });

      expect(reservation.status).toBe("active");
      expect(reservation.expiresAt).toBeGreaterThan(Date.now());

      const stock = inventory.getStockLevel("prod-laptop")!;
      expect(stock.totalQuantity).toBe(5);
      expect(stock.reservedQuantity).toBe(2);
      expect(stock.availableQuantity).toBe(3);
    });

    it("reserves multiple items atomically", () => {
      inventory.reserveStock({
        reservationId: "res-002",
        orderId: "ord-002",
        items: [
          { productId: "prod-laptop", quantity: 1 },
          { productId: "prod-monitor", quantity: 3 },
        ],
      });

      expect(inventory.getStockLevel("prod-laptop")!.availableQuantity).toBe(4);
      expect(inventory.getStockLevel("prod-monitor")!.availableQuantity).toBe(7);
    });

    it("prevents overselling and throws InventoryShortfallError when stock is insufficient", () => {
      // Try to reserve 6 laptops when only 5 exist
      expect(() =>
        inventory.reserveStock({
          reservationId: "res-fail",
          orderId: "ord-fail",
          items: [{ productId: "prod-laptop", quantity: 6 }],
        })
      ).toThrow(InventoryShortfallError);

      // Verify stock was not locked or partially modified
      const stock = inventory.getStockLevel("prod-laptop")!;
      expect(stock.reservedQuantity).toBe(0);
      expect(stock.availableQuantity).toBe(5);
    });

    it("handles concurrency and race conditions for scarce inventory", () => {
      // Available: 5 laptops
      // Request 1: 3 laptops -> OK
      inventory.reserveStock({
        reservationId: "res-user-1",
        orderId: "ord-user-1",
        items: [{ productId: "prod-laptop", quantity: 3 }],
      });

      // Request 2: 2 laptops -> OK (available becomes 0)
      inventory.reserveStock({
        reservationId: "res-user-2",
        orderId: "ord-user-2",
        items: [{ productId: "prod-laptop", quantity: 2 }],
      });

      expect(inventory.getStockLevel("prod-laptop")!.availableQuantity).toBe(0);

      // Request 3: 1 laptop -> Must reject with shortfall
      expect(() =>
        inventory.reserveStock({
          reservationId: "res-user-3",
          orderId: "ord-user-3",
          items: [{ productId: "prod-laptop", quantity: 1 }],
        })
      ).toThrow(InventoryShortfallError);
    });
  });

  describe("Commit Reservation on Payment Success", () => {
    it("commits reservation and decrements total physical inventory", () => {
      inventory.reserveStock({
        reservationId: "res-commit",
        orderId: "ord-commit",
        items: [{ productId: "prod-laptop", quantity: 2 }],
      });

      const committed = inventory.commitReservation("res-commit");
      expect(committed.status).toBe("committed");
      expect(committed.committedAt).toBeDefined();

      const stock = inventory.getStockLevel("prod-laptop")!;
      // Total decreased from 5 to 3; reserved dropped from 2 to 0; available is 3
      expect(stock.totalQuantity).toBe(3);
      expect(stock.reservedQuantity).toBe(0);
      expect(stock.availableQuantity).toBe(3);
    });

    it("committing an already committed reservation is idempotent", () => {
      inventory.reserveStock({
        reservationId: "res-idem",
        orderId: "ord-idem",
        items: [{ productId: "prod-laptop", quantity: 1 }],
      });

      inventory.commitReservation("res-idem");
      const secondCommit = inventory.commitReservation("res-idem");

      expect(secondCommit.status).toBe("committed");
      expect(inventory.getStockLevel("prod-laptop")!.totalQuantity).toBe(4);
    });
  });

  describe("Rollback & Release on Payment Failure", () => {
    it("releases reservation and returns stock to available pool", () => {
      inventory.reserveStock({
        reservationId: "res-rollback",
        orderId: "ord-rollback",
        items: [{ productId: "prod-laptop", quantity: 3 }],
      });

      expect(inventory.getStockLevel("prod-laptop")!.availableQuantity).toBe(2);

      // Payment failed -> release reservation
      const released = inventory.releaseReservation("res-rollback");
      expect(released.status).toBe("released");
      expect(released.releasedAt).toBeDefined();

      const stock = inventory.getStockLevel("prod-laptop")!;
      expect(stock.totalQuantity).toBe(5);
      expect(stock.reservedQuantity).toBe(0);
      expect(stock.availableQuantity).toBe(5);
    });
  });

  describe("Reservation Expiration & Timeout Cleanup", () => {
    it("automatically releases expired reservations when hold duration passes", () => {
      const now = Date.now();
      vi.useFakeTimers();
      vi.setSystemTime(now);

      inventory.reserveStock({
        reservationId: "res-expire-test",
        orderId: "ord-expire-test",
        items: [{ productId: "prod-laptop", quantity: 2 }],
        holdDurationMs: 10 * 1000, // 10 seconds hold
      });

      expect(inventory.getStockLevel("prod-laptop")!.availableQuantity).toBe(3);

      // Advance time beyond hold duration (e.g. 15 seconds)
      vi.advanceTimersByTime(15 * 1000);

      // When checking stock, expired reservations are automatically swept
      const stockAfterExpiry = inventory.getStockLevel("prod-laptop")!;
      expect(stockAfterExpiry.availableQuantity).toBe(5);
      expect(stockAfterExpiry.reservedQuantity).toBe(0);

      const reservation = inventory.getReservation("res-expire-test")!;
      expect(reservation.status).toBe("expired");

      vi.useRealTimers();
    });

    it("rejects committing an expired reservation", () => {
      const now = Date.now();
      vi.useFakeTimers();
      vi.setSystemTime(now);

      inventory.reserveStock({
        reservationId: "res-late-pay",
        orderId: "ord-late-pay",
        items: [{ productId: "prod-laptop", quantity: 1 }],
        holdDurationMs: 5000,
      });

      vi.advanceTimersByTime(10000); // 10 seconds later

      expect(() => inventory.commitReservation("res-late-pay")).toThrow(
        InventoryReservationExpiredError
      );

      vi.useRealTimers();
    });
  });
});
