/**
 * SoftMarket Kenya — M-Pesa Idempotency & Replay Protection Store
 */

import { MpesaIdempotencyError } from "../../utils/errors.js";

export type PaymentStatus = "pending" | "stk_sent" | "paid" | "failed" | "cancelled" | "refunded";

export interface StoredPaymentRecord {
  paymentId: string;
  orderId: string;
  checkoutRequestId: string;
  amountCents: number;
  phone: string;
  status: PaymentStatus;
  mpesaReceipt?: string;
  resultCode?: number;
  resultDesc?: string;
  createdAt: number;
  updatedAt: number;
  processedCallbacks: number;
}

export class MpesaIdempotencyTracker {
  private records = new Map<string, StoredPaymentRecord>(); // checkoutRequestId -> record
  private receiptIndex = new Map<string, string>(); // mpesaReceipt -> checkoutRequestId

  registerPayment(payment: {
    paymentId: string;
    orderId: string;
    checkoutRequestId: string;
    amountCents: number;
    phone: string;
    status?: PaymentStatus;
  }): StoredPaymentRecord {
    if (!payment.checkoutRequestId) {
      throw new Error("Cannot register payment with empty checkoutRequestId");
    }

    const now = Date.now();
    const record: StoredPaymentRecord = {
      ...payment,
      status: payment.status || "stk_sent",
      createdAt: now,
      updatedAt: now,
      processedCallbacks: 0,
    };

    this.records.set(payment.checkoutRequestId, record);
    return record;
  }

  getRecord(checkoutRequestId: string): StoredPaymentRecord | undefined {
    return this.records.get(checkoutRequestId);
  }

  hasReceipt(receipt: string): boolean {
    return this.receiptIndex.has(receipt);
  }

  /**
   * Applies callback transition with idempotency protection.
   * - If payment is already 'paid', duplicate success callbacks are acknowledged idempotently.
   * - A failed callback cannot downgrade a payment that has already succeeded.
   * - Replayed receipts for different checkout requests are rejected.
   */
  processCallbackTransition(params: {
    checkoutRequestId: string;
    success: boolean;
    resultCode: number;
    resultDesc: string;
    mpesaReceipt?: string;
    amountCents?: number;
  }): { record: StoredPaymentRecord; isDuplicate: boolean; statusChanged: boolean } {
    const record = this.records.get(params.checkoutRequestId);
    if (!record) {
      throw new Error(`Payment record not found for CheckoutRequestID: ${params.checkoutRequestId}`);
    }

    const now = Date.now();
    record.processedCallbacks += 1;

    // Case 1: Already marked PAID
    if (record.status === "paid") {
      if (params.success && params.mpesaReceipt === record.mpesaReceipt) {
        // Idempotent duplicate delivery of success callback
        return { record, isDuplicate: true, statusChanged: false };
      }

      if (!params.success) {
        // Late error callback after payment already succeeded -> reject state downgrade
        throw new MpesaIdempotencyError(
          `Cannot mark payment as failed: payment ${record.paymentId} is already in terminal state 'paid'`,
          { currentStatus: record.status, attemptedResultCode: params.resultCode }
        );
      }
    }

    // Case 2: Check for receipt collision / reuse across transactions
    if (params.mpesaReceipt) {
      const existingCheckout = this.receiptIndex.get(params.mpesaReceipt);
      if (existingCheckout && existingCheckout !== params.checkoutRequestId) {
        throw new MpesaIdempotencyError(
          `MpesaReceiptNumber ${params.mpesaReceipt} has already been processed for a different transaction (${existingCheckout})`,
          { mpesaReceipt: params.mpesaReceipt, existingCheckout }
        );
      }
    }

    // Case 3: Transition to terminal status
    const previousStatus = record.status;
    if (params.success) {
      record.status = "paid";
      if (params.mpesaReceipt) {
        record.mpesaReceipt = params.mpesaReceipt;
        this.receiptIndex.set(params.mpesaReceipt, params.checkoutRequestId);
      }
    } else {
      record.status = "failed";
    }

    record.resultCode = params.resultCode;
    record.resultDesc = params.resultDesc;
    record.updatedAt = now;

    return {
      record,
      isDuplicate: false,
      statusChanged: previousStatus !== record.status,
    };
  }

  clear(): void {
    this.records.clear();
    this.receiptIndex.clear();
  }
}
