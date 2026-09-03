/**
 * SoftMarket Kenya — Inventory Reservation & Stock Locking Types
 */

export interface StockItem {
  productId: string;
  sku: string;
  title: string;
  totalQuantity: number;
  reservedQuantity: number;
}

export interface ReservationRequestItem {
  productId: string;
  quantity: number;
}

export interface StockReservationRequest {
  reservationId: string;
  orderId: string;
  items: ReservationRequestItem[];
  holdDurationMs?: number; // Default 15 minutes (900,000 ms)
}

export type ReservationStatus = "active" | "committed" | "released" | "expired";

export interface StockReservation {
  reservationId: string;
  orderId: string;
  items: ReservationRequestItem[];
  status: ReservationStatus;
  createdAt: number;
  expiresAt: number;
  committedAt?: number;
  releasedAt?: number;
}

export interface StockLevel {
  productId: string;
  totalQuantity: number;
  reservedQuantity: number;
  availableQuantity: number; // totalQuantity - reservedQuantity
}
