import { describe, it, expect, beforeEach } from "vitest";
import {
  secureCompareTokens,
  verifyWebhookAuthorization,
  validateAndExtractStkCallback,
  MpesaIdempotencyTracker,
  validateC2BTransaction,
  validateAndExtractB2CCallback,
  MPESA_RESULT_CODES,
} from "../src/services/mpesa/index.js";
import {
  MpesaAuthenticationError,
  MpesaIdempotencyError,
  MpesaValidationError,
} from "../src/utils/errors.js";

describe("M-Pesa Daraja Payment & Webhook Processing", () => {
  describe("Security & Token Authentication", () => {
    it("secureCompareTokens performs constant-time string comparison", () => {
      const secret = "my_super_secret_mpesa_token_123456";
      expect(secureCompareTokens(secret, "my_super_secret_mpesa_token_123456")).toBe(true);
      expect(secureCompareTokens(secret, "wrong_token")).toBe(false);
      expect(secureCompareTokens(secret, "")).toBe(false);
      expect(secureCompareTokens(secret, undefined)).toBe(false);
      expect(secureCompareTokens("", "test")).toBe(false);
    });

    it("verifyWebhookAuthorization allows valid token and throws MpesaAuthenticationError on invalid", () => {
      const expected = "valid_token_xyz";
      expect(() => verifyWebhookAuthorization(expected, "valid_token_xyz")).not.toThrow();

      expect(() => verifyWebhookAuthorization(expected, "forged_token")).toThrow(
        MpesaAuthenticationError
      );
      expect(() => verifyWebhookAuthorization(expected, undefined)).toThrow(
        MpesaAuthenticationError
      );

      // When no secret is configured in env, verification passes
      expect(() => verifyWebhookAuthorization(undefined, undefined)).not.toThrow();
    });
  });

  describe("STK Push Callback Payload Validation & Data Extraction", () => {
    const validSuccessPayload = {
      Body: {
        stkCallback: {
          MerchantRequestID: "29115-34620561-1",
          CheckoutRequestID: "ws_CO_19122026102036292716343561",
          ResultCode: 0,
          ResultDesc: "The service request is processed successfully.",
          CallbackMetadata: {
            Item: [
              { Name: "Amount", Value: 2500.0 },
              { Name: "MpesaReceiptNumber", Value: "QHD51KP72L" },
              { Name: "Balance", Value: 0 },
              { Name: "TransactionDate", Value: 20260814214500 },
              { Name: "PhoneNumber", Value: 254716343561 },
            ],
          },
        },
      },
    };

    it("extracts all structured fields from a successful STK callback", () => {
      const extracted = validateAndExtractStkCallback(validSuccessPayload);

      expect(extracted.success).toBe(true);
      expect(extracted.resultCode).toBe(0);
      expect(extracted.checkoutRequestId).toBe("ws_CO_19122026102036292716343561");
      expect(extracted.merchantRequestId).toBe("29115-34620561-1");
      expect(extracted.mpesaReceipt).toBe("QHD51KP72L");
      expect(extracted.amount).toBe(2500);
      expect(extracted.amountCents).toBe(250000);
      expect(extracted.phoneNumber).toBe("254716343561");
      expect(extracted.transactionDate).toBe("20260814214500");
    });

    it("verifies expected amount strictly in integer cents", () => {
      // Correct amount: 250,000 cents (KES 2,500)
      expect(() =>
        validateAndExtractStkCallback(validSuccessPayload, 250000)
      ).not.toThrow();

      // Amount mismatch (e.g. expected 500,000 cents) -> throws MpesaValidationError
      expect(() =>
        validateAndExtractStkCallback(validSuccessPayload, 500000)
      ).toThrow(MpesaValidationError);
    });

    it("extracts failed STK callback without metadata items (User Cancelled 1032)", () => {
      const cancelledPayload = {
        Body: {
          stkCallback: {
            MerchantRequestID: "29115-34620561-2",
            CheckoutRequestID: "ws_CO_19122026102036292716343562",
            ResultCode: 1032,
            ResultDesc: "Request cancelled by user",
          },
        },
      };

      const extracted = validateAndExtractStkCallback(cancelledPayload);
      expect(extracted.success).toBe(false);
      expect(extracted.resultCode).toBe(1032);
      expect(extracted.mpesaReceipt).toBeUndefined();
      expect(extracted.checkoutRequestId).toBe("ws_CO_19122026102036292716343562");
    });

    it("extracts failed STK callback for timeout (ResultCode 1037)", () => {
      const timeoutPayload = {
        Body: {
          stkCallback: {
            MerchantRequestID: "29115-34620561-3",
            CheckoutRequestID: "ws_CO_19122026102036292716343563",
            ResultCode: 1037,
            ResultDesc: "DS timeout user cannot be reached",
          },
        },
      };

      const extracted = validateAndExtractStkCallback(timeoutPayload);
      expect(extracted.success).toBe(false);
      expect(extracted.resultCode).toBe(1037);
    });

    it("rejects malformed payloads and empty CheckoutRequestID", () => {
      expect(() => validateAndExtractStkCallback(null)).toThrow(MpesaValidationError);
      expect(() => validateAndExtractStkCallback({})).toThrow(MpesaValidationError);
      expect(() => validateAndExtractStkCallback({ Body: {} })).toThrow(MpesaValidationError);

      const emptyCheckoutPayload = {
        Body: {
          stkCallback: {
            MerchantRequestID: "123",
            CheckoutRequestID: "",
            ResultCode: 0,
          },
        },
      };
      expect(() => validateAndExtractStkCallback(emptyCheckoutPayload)).toThrow(
        MpesaValidationError
      );
    });

    it("rejects success callback that is missing MpesaReceiptNumber", () => {
      const missingReceiptPayload = {
        Body: {
          stkCallback: {
            MerchantRequestID: "123",
            CheckoutRequestID: "ws_CO_123",
            ResultCode: 0,
            ResultDesc: "Success",
            CallbackMetadata: {
              Item: [{ Name: "Amount", Value: 100 }],
            },
          },
        },
      };
      expect(() => validateAndExtractStkCallback(missingReceiptPayload)).toThrow(
        MpesaValidationError
      );
    });
  });

  describe("Idempotency & Replay Protection", () => {
    let tracker: MpesaIdempotencyTracker;

    beforeEach(() => {
      tracker = new MpesaIdempotencyTracker();
    });

    it("registers payment and marks as paid on first successful callback", () => {
      tracker.registerPayment({
        paymentId: "PAY-001",
        orderId: "ORD-001",
        checkoutRequestId: "ws_CO_100",
        amountCents: 200000,
        phone: "254712345678",
      });

      const res = tracker.processCallbackTransition({
        checkoutRequestId: "ws_CO_100",
        success: true,
        resultCode: 0,
        resultDesc: "Success",
        mpesaReceipt: "REC100",
        amountCents: 200000,
      });

      expect(res.isDuplicate).toBe(false);
      expect(res.statusChanged).toBe(true);
      expect(res.record.status).toBe("paid");
      expect(res.record.mpesaReceipt).toBe("REC100");
    });

    it("handles duplicate webhook delivery idempotently without modifying state", () => {
      tracker.registerPayment({
        paymentId: "PAY-002",
        orderId: "ORD-002",
        checkoutRequestId: "ws_CO_200",
        amountCents: 150000,
        phone: "254712345678",
      });

      // First delivery
      tracker.processCallbackTransition({
        checkoutRequestId: "ws_CO_200",
        success: true,
        resultCode: 0,
        resultDesc: "Success",
        mpesaReceipt: "REC200",
      });

      // Second identical delivery (webhook replay)
      const replayRes = tracker.processCallbackTransition({
        checkoutRequestId: "ws_CO_200",
        success: true,
        resultCode: 0,
        resultDesc: "Success",
        mpesaReceipt: "REC200",
      });

      expect(replayRes.isDuplicate).toBe(true);
      expect(replayRes.statusChanged).toBe(false);
      expect(replayRes.record.status).toBe("paid");
      expect(replayRes.record.processedCallbacks).toBe(2);
    });

    it("rejects state downgrade when a failed callback is received after payment was paid", () => {
      tracker.registerPayment({
        paymentId: "PAY-003",
        orderId: "ORD-003",
        checkoutRequestId: "ws_CO_300",
        amountCents: 100000,
        phone: "254712345678",
      });

      // Success callback
      tracker.processCallbackTransition({
        checkoutRequestId: "ws_CO_300",
        success: true,
        resultCode: 0,
        resultDesc: "Success",
        mpesaReceipt: "REC300",
      });

      // Late failed callback -> Must throw MpesaIdempotencyError
      expect(() =>
        tracker.processCallbackTransition({
          checkoutRequestId: "ws_CO_300",
          success: false,
          resultCode: 1032,
          resultDesc: "User Cancelled",
        })
      ).toThrow(MpesaIdempotencyError);
    });

    it("prevents MpesaReceipt collision across different checkout requests", () => {
      tracker.registerPayment({
        paymentId: "PAY-A",
        orderId: "ORD-A",
        checkoutRequestId: "ws_CO_A",
        amountCents: 50000,
        phone: "254711111111",
      });

      tracker.registerPayment({
        paymentId: "PAY-B",
        orderId: "ORD-B",
        checkoutRequestId: "ws_CO_B",
        amountCents: 50000,
        phone: "254722222222",
      });

      // Transaction A succeeds with receipt REC_SHARED
      tracker.processCallbackTransition({
        checkoutRequestId: "ws_CO_A",
        success: true,
        resultCode: 0,
        resultDesc: "Success",
        mpesaReceipt: "REC_SHARED",
      });

      // Transaction B attempts to claim the same receipt -> Must reject
      expect(() =>
        tracker.processCallbackTransition({
          checkoutRequestId: "ws_CO_B",
          success: true,
          resultCode: 0,
          resultDesc: "Success",
          mpesaReceipt: "REC_SHARED",
        })
      ).toThrow(MpesaIdempotencyError);
    });
  });

  describe("C2B Paybill & BuyGoods Processing", () => {
    it("validates valid C2B transaction successfully", () => {
      const payload = {
        TransactionType: "Pay Bill",
        TransID: "RFT123456",
        TransTime: "20260814220000",
        TransAmount: "1500.00",
        BusinessShortCode: "600000",
        BillRefNumber: "ACC-101",
        MSISDN: "254712345678",
      };

      const res = validateC2BTransaction(payload);
      expect(res.ResultCode).toBe("0");
      expect(res.ResultDesc).toBe("Accepted");
    });

    it("validates C2B account with custom account validator callback", () => {
      const payload = {
        TransactionType: "Pay Bill",
        TransID: "RFT123457",
        TransTime: "20260814220000",
        TransAmount: "2000.00",
        BusinessShortCode: "600000",
        BillRefNumber: "UNKNOWN-ACC",
        MSISDN: "254712345678",
      };

      const accountValidator = (billRef: string) => billRef.startsWith("VALID-");
      const res = validateC2BTransaction(payload, accountValidator);
      expect(res.ResultCode).toBe("C2B00012");
      expect(res.ResultDesc).toContain("Invalid Account Reference");
    });
  });

  describe("B2C Payout Result Callback Processing", () => {
    it("extracts structured data from B2C result payload", () => {
      const b2cPayload = {
        Result: {
          ResultType: 0,
          ResultCode: 0,
          ResultDesc: "The service request is processed successfully.",
          OriginatorConversationID: "orig_conv_123",
          ConversationID: "AG_20260814_conv456",
          TransactionID: "QWE789RTY",
          ResultParameters: {
            ResultParameter: [
              { Key: "TransactionAmount", Value: 4500.0 },
              { Key: "TransactionReceipt", Value: "QWE789RTY" },
              { Key: "ReceiverPartyPublicName", Value: "254712345678 - John Doe" },
              { Key: "TransactionCompletedDateTime", Value: "14.08.2026 21:45:00" },
              { Key: "B2CUtilityAccountAvailableFunds", Value: 250000.0 },
            ],
          },
        },
      };

      const extracted = validateAndExtractB2CCallback(b2cPayload);
      expect(extracted.success).toBe(true);
      expect(extracted.transactionId).toBe("QWE789RTY");
      expect(extracted.conversationId).toBe("AG_20260814_conv456");
      expect(extracted.amount).toBe(4500);
      expect(extracted.amountCents).toBe(450000);
      expect(extracted.receiverPartyPublicName).toContain("John Doe");
      expect(extracted.b2cUtilityAccountAvailableFunds).toBe(250000);
    });
  });
});
