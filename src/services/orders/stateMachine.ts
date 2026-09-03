/**
 * SoftMarket Kenya — Order Lifecycle State Machine & Transition Engine
 */

import { InvalidStateTransitionError } from "../../utils/errors.js";
import type {
  OrderStatus,
  OrderStateModel,
  OrderStateTransitionEvent,
} from "./types.js";

/**
 * Transition rule map: allowed target statuses from each source status.
 */
export const ALLOWED_ORDER_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  pending: ["reserved", "cancelled"],
  reserved: ["payment_pending", "cancelled"],
  payment_pending: ["paid", "cancelled", "reserved"],
  paid: ["processing", "cancelled", "refunded"],
  processing: ["shipped", "cancelled", "refunded"],
  shipped: ["delivered", "refunded"],
  delivered: ["refunded"],
  cancelled: [], // Terminal
  refunded: [], // Terminal
};

export type TransitionHook = (
  order: OrderStateModel,
  event: OrderStateTransitionEvent
) => Promise<void> | void;

export class OrderStateMachine {
  private hooks = new Map<OrderStatus, TransitionHook[]>();

  onTransitionTo(status: OrderStatus, hook: TransitionHook): void {
    const list = this.hooks.get(status) || [];
    list.push(hook);
    this.hooks.set(status, list);
  }

  canTransition(currentStatus: OrderStatus, targetStatus: OrderStatus): boolean {
    const allowed = ALLOWED_ORDER_TRANSITIONS[currentStatus] || [];
    return allowed.includes(targetStatus);
  }

  async transitionOrder(
    order: OrderStateModel,
    targetStatus: OrderStatus,
    options: {
      actor?: string;
      reason?: string;
      metadata?: Record<string, unknown>;
    } = {}
  ): Promise<OrderStateModel> {
    if (order.status === targetStatus) {
      return order; // Idempotent same-state transition
    }

    if (!this.canTransition(order.status, targetStatus)) {
      throw new InvalidStateTransitionError(
        `Cannot transition order ${order.orderId} from '${order.status}' to '${targetStatus}'. Allowed target states: [${(ALLOWED_ORDER_TRANSITIONS[order.status] || []).join(", ")}]`,
        {
          orderId: order.orderId,
          fromStatus: order.status,
          toStatus: targetStatus,
          allowed: ALLOWED_ORDER_TRANSITIONS[order.status] || [],
        }
      );
    }

    const now = Date.now();
    const event: OrderStateTransitionEvent = {
      fromStatus: order.status,
      toStatus: targetStatus,
      timestamp: now,
      actor: options.actor || "system",
      reason: options.reason,
      metadata: options.metadata,
    };

    order.status = targetStatus;
    order.updatedAt = now;
    order.history.push(event);

    // Execute transition hooks
    const targetHooks = this.hooks.get(targetStatus) || [];
    for (const hook of targetHooks) {
      await hook(order, event);
    }

    return order;
  }

  createOrder(params: {
    orderId: string;
    amountCents: number;
    customerPhone: string;
    reservationId?: string;
  }): OrderStateModel {
    const now = Date.now();
    return {
      orderId: params.orderId,
      status: "pending",
      amountCents: params.amountCents,
      customerPhone: params.customerPhone,
      reservationId: params.reservationId,
      history: [
        {
          fromStatus: "pending",
          toStatus: "pending",
          timestamp: now,
          actor: "customer",
          reason: "Order created",
        },
      ],
      createdAt: now,
      updatedAt: now,
    };
  }
}
