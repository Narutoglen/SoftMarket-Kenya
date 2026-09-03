import { describe, it, expect } from "vitest";
import {
  normalizeKenyanPhone,
  validateAndSanitizePhone,
  calculateCartTotals,
  InventoryManager,
  OrderStateMachine,
  validateAndExtractStkCallback,
  MpesaIdempotencyTracker,
  calculateOrderPayoutSplits,
  secureCompareTokens,
  formatKES,
} from "../src/index.js";

describe("End-to-End SoftMarket Kenya Commerce & Payment Workflow", () => {
  it("executes full order lifecycle: cart -> inventory lock -> mpesa payment -> state machine -> payout splitting", async () => {
    // 1. Customer phone number validation
    const customerPhoneInput = "+254 (0716) 343-561";
    const phoneRes = validateAndSanitizePhone(customerPhoneInput);
    expect(phoneRes.valid).toBe(true);
    expect(phoneRes.normalized).toBe("254716343561");
    expect(phoneRes.carrier).toBe("Safaricom");

    // 2. Setup inventory
    const inventory = new InventoryManager();
    inventory.setStock({
      productId: "prod-laptop-1",
      title: "Core i7 Dev Laptop",
      quantity: 10,
    });
    inventory.setStock({
      productId: "prod-software-suite",
      title: "POS Pro License",
      quantity: 50,
    });

    // 3. Cart calculation with coupon and delivery to Nakuru (Zone 3)
    const cartItems = [
      {
        id: "item-1",
        productId: "prod-laptop-1",
        vendorId: "vendor-hardware",
        vendorName: "Nairobi Hardware Hub",
        category: "hardware",
        title: "Core i7 Dev Laptop",
        unitPriceCents: 8500000, // KES 85,000
        quantity: 1,
        weightKg: 2.5,
        taxable: true,
      },
      {
        id: "item-2",
        productId: "prod-software-suite",
        vendorId: "vendor-software",
        vendorName: "SoftMarket Software Ltd",
        category: "software",
        title: "POS Pro License",
        unitPriceCents: 1500000, // KES 15,000
        quantity: 1,
        weightKg: 0.1,
        taxable: true,
      },
    ];

    const coupon = {
      code: "WELCOME5K",
      type: "fixed_amount" as const,
      value: 500000, // KES 5,000 off
      minSpendCents: 5000000, // Min spend KES 50,000
      isActive: true,
    };

    const cartResult = calculateCartTotals({
      items: cartItems,
      coupon,
      deliveryCounty: "Nakuru",
      deliverySpeed: "standard",
      pricesIncludeVat: false,
    });

    // Subtotal: 85,000 + 15,000 = 100,000 KES (10,000,000 cents)
    // Discount: 5,000 KES (500,000 cents) -> Net Subtotal = 95,000 KES
    // VAT (16% on 95,000) = 15,200 KES (1,520,000 cents)
    // Nakuru Delivery (Zone 3, order >= 12,000 threshold) = FREE (0 KES)
    // Grand Total = 95,000 + 15,200 + 0 = 110,200 KES (11,020,000 cents)
    expect(cartResult.subtotalCents).toBe(10000000);
    expect(cartResult.discountCents).toBe(500000);
    expect(cartResult.netSubtotalCents).toBe(9500000);
    expect(cartResult.vatAmountCents).toBe(1520000);
    expect(cartResult.deliveryFeeCents).toBe(0);
    expect(cartResult.grandTotalCents).toBe(11020000);

    // 4. Create Order and Lock Inventory
    const stateMachine = new OrderStateMachine();
    const order = stateMachine.createOrder({
      orderId: "ORD-KEN-2026-001",
      amountCents: cartResult.grandTotalCents,
      customerPhone: phoneRes.normalized!,
      reservationId: "RES-2026-001",
    });

    const reservation = inventory.reserveStock({
      reservationId: "RES-2026-001",
      orderId: order.orderId,
      items: [
        { productId: "prod-laptop-1", quantity: 1 },
        { productId: "prod-software-suite", quantity: 1 },
      ],
    });
    expect(reservation.status).toBe("active");
    expect(inventory.getStockLevel("prod-laptop-1")!.availableQuantity).toBe(9);

    await stateMachine.transitionOrder(order, "reserved");
    await stateMachine.transitionOrder(order, "payment_pending");

    // 5. Register M-Pesa Payment and Process STK Callback
    const mpesaTracker = new MpesaIdempotencyTracker();
    const checkoutRequestId = "ws_CO_14082026_SMK_999";
    const webhookToken = "secret_webhook_token_abc";

    mpesaTracker.registerPayment({
      paymentId: "PAY-SMK-001",
      orderId: order.orderId,
      checkoutRequestId,
      amountCents: cartResult.grandTotalCents,
      phone: phoneRes.normalized!,
    });

    // Simulate incoming Daraja webhook
    expect(secureCompareTokens(webhookToken, "secret_webhook_token_abc")).toBe(true);

    const stkPayload = {
      Body: {
        stkCallback: {
          MerchantRequestID: "29115-34620561-1",
          CheckoutRequestID: checkoutRequestId,
          ResultCode: 0,
          ResultDesc: "The service request is processed successfully.",
          CallbackMetadata: {
            Item: [
              { Name: "Amount", Value: cartResult.grandTotalKes }, // 110,200
              { Name: "MpesaReceiptNumber", Value: "QHD99KP88Z" },
              { Name: "TransactionDate", Value: 20260814221000 },
              { Name: "PhoneNumber", Value: 254716343561 },
            ],
          },
        },
      },
    };

    const extracted = validateAndExtractStkCallback(stkPayload, cartResult.grandTotalCents);
    expect(extracted.success).toBe(true);
    expect(extracted.mpesaReceipt).toBe("QHD99KP88Z");

    const callbackRes = mpesaTracker.processCallbackTransition({
      checkoutRequestId,
      success: true,
      resultCode: 0,
      resultDesc: "Success",
      mpesaReceipt: extracted.mpesaReceipt,
      amountCents: extracted.amountCents,
    });
    expect(callbackRes.record.status).toBe("paid");

    // 6. Commit Inventory and Transition Order State
    inventory.commitReservation(reservation.reservationId);
    expect(inventory.getStockLevel("prod-laptop-1")!.totalQuantity).toBe(9);

    await stateMachine.transitionOrder(order, "paid", {
      actor: "mpesa_webhook",
      reason: `Paid via M-Pesa Receipt ${extracted.mpesaReceipt}`,
    });
    await stateMachine.transitionOrder(order, "processing");
    await stateMachine.transitionOrder(order, "shipped");
    await stateMachine.transitionOrder(order, "delivered");

    expect(order.status).toBe("delivered");
    expect(order.history.length).toBe(7);

    // 7. Calculate Vendor Payout Splits
    const payoutResult = calculateOrderPayoutSplits({
      orderId: order.orderId,
      items: [
        {
          productId: "prod-laptop-1",
          vendorId: "vendor-hardware",
          vendorName: "Nairobi Hardware Hub",
          category: "hardware",
          title: "Core i7 Dev Laptop",
          grossAmountCents: 8500000, // KES 85,000
          quantity: 1,
        },
        {
          productId: "prod-software-suite",
          vendorId: "vendor-software",
          vendorName: "SoftMarket Software Ltd",
          category: "software",
          title: "POS Pro License",
          grossAmountCents: 1500000, // KES 15,000
          quantity: 1,
        },
      ],
      deliveryFeeCents: 0,
    });

    expect(payoutResult.vendors.length).toBe(2);
    expect(payoutResult.zeroLeakageCheck.isValid).toBe(true);
    expect(payoutResult.totalMerchantPayoutsCents).toBeGreaterThan(0);
    expect(payoutResult.totalPlatformCommissionCents).toBeGreaterThan(0);
  });
});
