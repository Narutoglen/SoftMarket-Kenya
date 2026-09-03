/**
 * M-Pesa STK Push Timeout & Callback Reconciliation Engine.
 * Safaricom Daraja Query API response parsing and order state reconciliation.
 */

export interface DarajaQueryResult {
  ResponseCode: string;
  ResponseDescription: string;
  MerchantRequestID: string;
  CheckoutRequestID: string;
  ResultCode: string;
  ResultDesc: string;
}

export type ReconciledPaymentState =
  | "PAID"
  | "CANCELLED_BY_USER"
  | "TIMEOUT"
  | "INSUFFICIENT_FUNDS"
  | "FAILED"
  | "PENDING_INVESTIGATION";

export interface ReconciledStatus {
  state: ReconciledPaymentState;
  canRetry: boolean;
  message: string;
  checkoutRequestId: string;
}

export function reconcileDarajaQueryResult(raw: DarajaQueryResult): ReconciledStatus {
  const code = String(raw.ResultCode).trim();
  const desc = raw.ResultDesc || raw.ResponseDescription || "No description provided";

  switch (code) {
    case "0":
      return {
        state: "PAID",
        canRetry: false,
        message: "Payment successfully verified via Daraja Query API.",
        checkoutRequestId: raw.CheckoutRequestID,
      };
    case "1032":
      return {
        state: "CANCELLED_BY_USER",
        canRetry: true,
        message: "User cancelled the STK push prompt on their phone.",
        checkoutRequestId: raw.CheckoutRequestID,
      };
    case "1037":
      return {
        state: "TIMEOUT",
        canRetry: true,
        message: "STK push timed out. The phone was unreachable or prompt expired.",
        checkoutRequestId: raw.CheckoutRequestID,
      };
    case "1":
      return {
        state: "INSUFFICIENT_FUNDS",
        canRetry: true,
        message: "M-Pesa balance was insufficient to complete transaction.",
        checkoutRequestId: raw.CheckoutRequestID,
      };
    default:
      return {
        state: "FAILED",
        canRetry: false,
        message: `M-Pesa transaction failed with code ${code}: ${desc}`,
        checkoutRequestId: raw.CheckoutRequestID,
      };
  }
}
