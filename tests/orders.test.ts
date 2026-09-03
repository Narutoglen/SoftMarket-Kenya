import { describe, it, expect, beforeEach, vi } from "vitest";
import { OrderStateMachine } from "../src/services/orders/index.js";
import { InvalidStateTransitionError } from "../src/utils/errors.js";
import type { OrderStateModel } from "../src/services/orders/types.js";

describe("Order Lifecycle State Machine", () => {
  let sm: OrderStateMachine;
  let order: OrderStateModel;

  beforeEach(() => {
    sm = new OrderStateMachine();
    order = sm.createOrder({
      orderId: "ORD-KEN-100",
      amountCents: 500000, // KES 5,000
      customerPhone: "254716343561",
      reservationId: "RES-100",
    });
  });

  describe("Order Creation & Initial State", () => {
    it("creates order in 'pending' status with history log", () => {
      expect(order.status).toBe("pending");
      expect(order.orderId).toBe("ORD-KEN-100");
      expect(order.amountCents).toBe(500000);
      expect(order.history.length).toBe(1);
      expect(order.history[0].toStatus).toBe("pending");
    });
  });

  describe("Standard Happy Path Lifecycle Transitions", () => {
    it("transitions through complete lifecycle: pending -> reserved -> payment_pending -> paid -> processing -> shipped -> delivered", async () => {
      // 1. Reserve stock
      await sm.transitionOrder(order, "reserved", { actor: "system", reason: "Stock locked" });
      expect(order.status).toBe("reserved");

      // 2. Initiate M-Pesa STK Push
      await sm.transitionOrder(order, "payment_pending", {
        actor: "system",
        reason: "STK push sent",
      });
      expect(order.status).toBe("payment_pending");

      // 3. Payment confirmed via Daraja webhook
      await sm.transitionOrder(order, "paid", {
        actor: "mpesa_webhook",
        reason: "M-Pesa payment received QHD51KP72L",
      });
      expect(order.status).toBe("paid");

      // 4. Processing order
      await sm.transitionOrder(order, "processing", {
        actor: "merchant",
        reason: "Packing order items",
      });
      expect(order.status).toBe("processing");

      // 5. Shipped with courier
      await sm.transitionOrder(order, "shipped", {
        actor: "courier",
        reason: "Dispatched via Fargo Courier",
      });
      expect(order.status).toBe("shipped");

      // 6. Delivered to customer
      await sm.transitionOrder(order, "delivered", {
        actor: "courier",
        reason: "Customer signed delivery confirmation",
      });
      expect(order.status).toBe("delivered");
      expect(order.history.length).toBe(7);
    });

    it("handles post-delivery refund flow: delivered -> refunded", async () => {
      await sm.transitionOrder(order, "reserved");
      await sm.transitionOrder(order, "payment_pending");
      await sm.transitionOrder(order, "paid");
      await sm.transitionOrder(order, "processing");
      await sm.transitionOrder(order, "shipped");
      await sm.transitionOrder(order, "delivered");

      await sm.transitionOrder(order, "refunded", {
        actor: "admin",
        reason: "Customer warranty return processed",
      });
      expect(order.status).toBe("refunded");
    });
  });

  describe("Order Cancellations", () => {
    it("allows cancellation from pending, reserved, payment_pending, or processing", async () => {
      // Cancel from pending
      const pendingOrder = sm.createOrder({
        orderId: "ORD-P",
        amountCents: 1000,
        customerPhone: "254711111111",
      });
      await sm.transitionOrder(pendingOrder, "cancelled", { reason: "User cancelled in cart" });
      expect(pendingOrder.status).toBe("cancelled");

      // Cancel from paid (pre-shipment)
      await sm.transitionOrder(order, "reserved");
      await sm.transitionOrder(order, "payment_pending");
      await sm.transitionOrder(order, "paid");
      await sm.transitionOrder(order, "cancelled", { reason: "Out of stock refund" });
      expect(order.status).toBe("cancelled");
    });
  });

  describe("Illegal Transition Guards", () => {
    it("rejects illegal transitions and throws InvalidStateTransitionError", async () => {
      // Cannot jump pending -> shipped directly
      await expect(sm.transitionOrder(order, "shipped")).rejects.toThrow(
        InvalidStateTransitionError
      );

      // Cannot jump pending -> delivered directly
      await expect(sm.transitionOrder(order, "delivered")).rejects.toThrow(
        InvalidStateTransitionError
      );

      // Cancel order and verify terminal state (cannot revive cancelled order)
      await sm.transitionOrder(order, "cancelled");
      await expect(sm.transitionOrder(order, "paid")).rejects.toThrow(
        InvalidStateTransitionError
      );
      await expect(sm.transitionOrder(order, "processing")).rejects.toThrow(
        InvalidStateTransitionError
      );
    });

    it("cannot transition from delivered directly to cancelled (must use refund)", async () => {
      await sm.transitionOrder(order, "reserved");
      await sm.transitionOrder(order, "payment_pending");
      await sm.transitionOrder(order, "paid");
      await sm.transitionOrder(order, "processing");
      await sm.transitionOrder(order, "shipped");
      await sm.transitionOrder(order, "delivered");

      await expect(sm.transitionOrder(order, "cancelled")).rejects.toThrow(
        InvalidStateTransitionError
      );
    });
  });

  describe("Transition Hooks", () => {
    it("triggers registered hooks when transitioning to specific state", async () => {
      const paidHook = vi.fn();
      sm.onTransitionTo("paid", paidHook);

      await sm.transitionOrder(order, "reserved");
      await sm.transitionOrder(order, "payment_pending");
      await sm.transitionOrder(order, "paid", { actor: "mpesa" });

      expect(paidHook).toHaveBeenCalledTimes(1);
      expect(paidHook).toHaveBeenCalledWith(
        expect.objectContaining({ orderId: "ORD-KEN-100", status: "paid" }),
        expect.objectContaining({ toStatus: "paid", actor: "mpesa" })
      );
    });
  });
});
