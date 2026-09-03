import { describe, it, expect } from "vitest";
import {
  reconcileDarajaQueryResult,
  type DarajaQueryResult,
} from "../src/services/mpesa/reconciliation";

describe("M-Pesa STK Push Timeout & Query Reconciliation", () => {
  it("reconciles code 0 as PAID without retry", () => {
    const raw: DarajaQueryResult = {
      ResponseCode: "0",
      ResponseDescription: "The service request has been accepted successfully",
      MerchantRequestID: "merch_101",
      CheckoutRequestID: "ws_CO_12345",
      ResultCode: "0",
      ResultDesc: "The service request is processed successfully.",
    };

    const reconciled = reconcileDarajaQueryResult(raw);
    expect(reconciled.state).toBe("PAID");
    expect(reconciled.canRetry).toBe(false);
    expect(reconciled.checkoutRequestId).toBe("ws_CO_12345");
  });

  it("reconciles user cancellation (1032) allowing order retry", () => {
    const raw: DarajaQueryResult = {
      ResponseCode: "0",
      ResponseDescription: "Accepted",
      MerchantRequestID: "merch_102",
      CheckoutRequestID: "ws_CO_99999",
      ResultCode: "1032",
      ResultDesc: "Request cancelled by user",
    };

    const reconciled = reconcileDarajaQueryResult(raw);
    expect(reconciled.state).toBe("CANCELLED_BY_USER");
    expect(reconciled.canRetry).toBe(true);
  });

  it("reconciles phone unreachable / prompt timeout (1037) allowing retry", () => {
    const raw: DarajaQueryResult = {
      ResponseCode: "0",
      ResponseDescription: "Accepted",
      MerchantRequestID: "merch_103",
      CheckoutRequestID: "ws_CO_77777",
      ResultCode: "1037",
      ResultDesc: "DS timeout user cannot be reached",
    };

    const reconciled = reconcileDarajaQueryResult(raw);
    expect(reconciled.state).toBe("TIMEOUT");
    expect(reconciled.canRetry).toBe(true);
  });

  it("safely handles unexpected error codes", () => {
    const raw: DarajaQueryResult = {
      ResponseCode: "0",
      ResponseDescription: "Accepted",
      MerchantRequestID: "merch_104",
      CheckoutRequestID: "ws_CO_33333",
      ResultCode: "2001",
      ResultDesc: "Invalid initiator information",
    };

    const reconciled = reconcileDarajaQueryResult(raw);
    expect(reconciled.state).toBe("FAILED");
    expect(reconciled.canRetry).toBe(false);
    expect(reconciled.message).toContain("2001");
  });
});
