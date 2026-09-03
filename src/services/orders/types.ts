/**
 * SoftMarket Kenya — Order State Machine Types
 */

export type OrderStatus =
  | "pending"
  | "reserved"
  | "payment_pending"
  | "paid"
  | "processing"
  | "shipped"
  | "delivered"
  | "cancelled"
  | "refunded";

export interface OrderStateTransitionEvent {
  fromStatus: OrderStatus;
  toStatus: OrderStatus;
  timestamp: number;
  actor: string; // "system" | "customer" | "admin" | "mpesa_webhook"
  reason?: string;
  metadata?: Record<string, unknown>;
}

export interface OrderStateModel {
  orderId: string;
  status: OrderStatus;
  amountCents: number;
  customerPhone: string;
  paymentId?: string;
  reservationId?: string;
  trackingNumber?: string;
  history: OrderStateTransitionEvent[];
  createdAt: number;
  updatedAt: number;
}
