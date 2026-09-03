/**
 * SoftMarket Kenya — Concurrency-Safe Stock Reservation & Inventory Engine
 */

import {
  InventoryShortfallError,
  InventoryReservationExpiredError,
} from "../../utils/errors.js";
import type {
  StockItem,
  StockLevel,
  StockReservation,
  StockReservationRequest,
  ReservationStatus,
} from "./types.js";

export const DEFAULT_HOLD_DURATION_MS = 15 * 60 * 1000; // 15 minutes hold

export class InventoryManager {
  private stock = new Map<string, StockItem>();
  private reservations = new Map<string, StockReservation>();

  /**
   * Initializes or updates stock level for a product.
   */
  setStock(item: {
    productId: string;
    sku?: string;
    title?: string;
    quantity: number;
  }): StockLevel {
    const existing = this.stock.get(item.productId);
    const reservedQuantity = existing ? existing.reservedQuantity : 0;
    const totalQuantity = Math.max(0, item.quantity);

    const record: StockItem = {
      productId: item.productId,
      sku: item.sku || `SKU-${item.productId}`,
      title: item.title || `Product ${item.productId}`,
      totalQuantity,
      reservedQuantity,
    };

    this.stock.set(item.productId, record);
    return this.getStockLevel(item.productId)!;
  }

  /**
   * Retrieves current stock level for a product.
   */
  getStockLevel(productId: string): StockLevel | undefined {
    this.cleanExpiredReservations();
    const item = this.stock.get(productId);
    if (!item) return undefined;

    return {
      productId: item.productId,
      totalQuantity: item.totalQuantity,
      reservedQuantity: item.reservedQuantity,
      availableQuantity: Math.max(0, item.totalQuantity - item.reservedQuantity),
    };
  }

  /**
   * Reserves stock atomically for an order.
   * Throws InventoryShortfallError if requested quantity exceeds available stock.
   */
  reserveStock(req: StockReservationRequest): StockReservation {
    this.cleanExpiredReservations();

    if (!req.reservationId || !req.orderId) {
      throw new Error("reservationId and orderId are required");
    }

    if (this.reservations.has(req.reservationId)) {
      const existing = this.reservations.get(req.reservationId)!;
      if (existing.status === "active" && existing.expiresAt > Date.now()) {
        return existing;
      }
    }

    // Step 1: Check availability across all requested items
    for (const reqItem of req.items) {
      if (reqItem.quantity <= 0) {
        throw new Error(`Invalid requested quantity for product ${reqItem.productId}: must be >= 1`);
      }

      const stockItem = this.stock.get(reqItem.productId);
      if (!stockItem) {
        throw new InventoryShortfallError(`Product not found in inventory: ${reqItem.productId}`, {
          productId: reqItem.productId,
        });
      }

      const available = stockItem.totalQuantity - stockItem.reservedQuantity;
      if (available < reqItem.quantity) {
        throw new InventoryShortfallError(
          `Insufficient stock for '${stockItem.title}'. Requested: ${reqItem.quantity}, Available: ${available}`,
          {
            productId: reqItem.productId,
            title: stockItem.title,
            requested: reqItem.quantity,
            available,
            total: stockItem.totalQuantity,
            reserved: stockItem.reservedQuantity,
          }
        );
      }
    }

    // Step 2: Lock stock atomically
    for (const reqItem of req.items) {
      const stockItem = this.stock.get(reqItem.productId)!;
      stockItem.reservedQuantity += reqItem.quantity;
    }

    const now = Date.now();
    const duration = req.holdDurationMs || DEFAULT_HOLD_DURATION_MS;
    const reservation: StockReservation = {
      reservationId: req.reservationId,
      orderId: req.orderId,
      items: req.items.map((i) => ({ ...i })),
      status: "active",
      createdAt: now,
      expiresAt: now + duration,
    };

    this.reservations.set(req.reservationId, reservation);
    return reservation;
  }

  /**
   * Commits an active reservation upon payment confirmation.
   * Decrements total inventory and reserved inventory.
   */
  commitReservation(reservationId: string): StockReservation {
    const reservation = this.reservations.get(reservationId);
    if (!reservation) {
      throw new Error(`Reservation not found: ${reservationId}`);
    }

    if (reservation.status === "committed") {
      return reservation; // Idempotent
    }

    if (reservation.status === "released" || reservation.status === "expired") {
      throw new InventoryReservationExpiredError(
        `Cannot commit reservation ${reservationId} because it is in '${reservation.status}' state`,
        { reservationId, status: reservation.status }
      );
    }

    if (Date.now() > reservation.expiresAt) {
      this.releaseReservation(reservationId, "expired");
      throw new InventoryReservationExpiredError(
        `Reservation ${reservationId} has expired and was released back to inventory`,
        { reservationId }
      );
    }

    // Decrement physical stock
    for (const item of reservation.items) {
      const stockItem = this.stock.get(item.productId);
      if (stockItem) {
        stockItem.totalQuantity = Math.max(0, stockItem.totalQuantity - item.quantity);
        stockItem.reservedQuantity = Math.max(0, stockItem.reservedQuantity - item.quantity);
      }
    }

    reservation.status = "committed";
    reservation.committedAt = Date.now();
    return reservation;
  }

  /**
   * Releases an active reservation upon payment failure, timeout, or cancellation.
   * Returns stock back to available pool.
   */
  releaseReservation(
    reservationId: string,
    targetStatus: "released" | "expired" = "released"
  ): StockReservation {
    const reservation = this.reservations.get(reservationId);
    if (!reservation) {
      throw new Error(`Reservation not found: ${reservationId}`);
    }

    if (reservation.status === "committed") {
      throw new Error(`Cannot release reservation ${reservationId}: already committed`);
    }

    if (reservation.status === "active") {
      for (const item of reservation.items) {
        const stockItem = this.stock.get(item.productId);
        if (stockItem) {
          stockItem.reservedQuantity = Math.max(0, stockItem.reservedQuantity - item.quantity);
        }
      }
    }

    reservation.status = targetStatus;
    reservation.releasedAt = Date.now();
    return reservation;
  }

  /**
   * Sweeps and automatically releases all expired reservations.
   */
  cleanExpiredReservations(): number {
    const now = Date.now();
    let cleaned = 0;

    for (const reservation of this.reservations.values()) {
      if (reservation.status === "active" && now > reservation.expiresAt) {
        this.releaseReservation(reservation.reservationId, "expired");
        cleaned += 1;
      }
    }

    return cleaned;
  }

  getReservation(reservationId: string): StockReservation | undefined {
    return this.reservations.get(reservationId);
  }

  clear(): void {
    this.stock.clear();
    this.reservations.clear();
  }
}
