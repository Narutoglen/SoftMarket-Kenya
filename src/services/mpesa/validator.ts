/**
 * SoftMarket Kenya — M-Pesa Callback Validation & Signature Checking
 */

import { timingSafeEqual } from "node:crypto";
import { kesToCents } from "../../utils/money.js";
import {
  MpesaAuthenticationError,
  MpesaValidationError,
} from "../../utils/errors.js";
import type {
  ExtractedStkData,
  StkCallbackPayload,
  StkCallbackItem,
} from "./types.js";

/**
 * ResultCode dictionary with Safaricom Daraja standard descriptions
 */
export const MPESA_RESULT_CODES: Record<number, string> = {
  0: "Success: The transaction was completed successfully.",
  1: "Insufficient Funds: The subscriber's M-Pesa balance is insufficient for the transaction.",
  1001: "Unable to lock subscriber: The subscriber's wallet is currently locked by another operation.",
  1019: "Transaction expired: The transaction timed out before completion.",
  1025: "System error: Safaricom could not complete the request.",
  1032: "Request cancelled: The user cancelled the STK Push prompt or entered an incorrect PIN.",
  1037: "Timeout / No response: The subscriber did not respond to the USSD push notification.",
  2001: "Invalid PIN: The initiator or subscriber entered an invalid PIN.",
};

/**
 * Performs a constant-time string comparison to prevent timing attack vulnerabilities.
 */
export function secureCompareTokens(
  expectedToken: string,
  providedToken?: string
): boolean {
  if (!providedToken || typeof providedToken !== "string") return false;
  if (!expectedToken || typeof expectedToken !== "string") return false;

  const expectedBuf = Buffer.from(expectedToken, "utf8");
  const providedBuf = Buffer.from(providedToken, "utf8");

  if (expectedBuf.length !== providedBuf.length) {
    return false;
  }

  return timingSafeEqual(expectedBuf, providedBuf);
}

/**
 * Validates the authentication token on an incoming M-Pesa webhook request.
 */
export function verifyWebhookAuthorization(
  expectedToken: string | undefined,
  providedToken: string | undefined
): void {
  if (!expectedToken) {
    // If no token is configured in environment, allow with warning
    return;
  }

  if (!providedToken || !secureCompareTokens(expectedToken, providedToken)) {
    throw new MpesaAuthenticationError(
      "Unauthorized M-Pesa callback: Invalid or missing authentication token",
      { providedTokenProvided: Boolean(providedToken) }
    );
  }
}

/**
 * Validates and extracts structured data from an M-Pesa STK Push callback.
 */
export function validateAndExtractStkCallback(
  payload: unknown,
  expectedAmountCents?: number
): ExtractedStkData {
  if (!payload || typeof payload !== "object") {
    throw new MpesaValidationError("M-Pesa callback payload must be a non-null JSON object");
  }

  const raw = payload as Record<string, any>;
  const body = raw.Body;
  if (!body || typeof body !== "object") {
    throw new MpesaValidationError("Invalid M-Pesa payload: missing 'Body' root object");
  }

  const stk = body.stkCallback;
  if (!stk || typeof stk !== "object") {
    throw new MpesaValidationError("Invalid M-Pesa payload: missing 'stkCallback' object in Body");
  }

  const checkoutRequestId = String(stk.CheckoutRequestID || "").trim();
  if (!checkoutRequestId) {
    throw new MpesaValidationError("Invalid M-Pesa callback: CheckoutRequestID is missing or empty");
  }

  const merchantRequestId = String(stk.MerchantRequestID || "").trim();
  const resultCode = Number(stk.ResultCode);
  if (isNaN(resultCode)) {
    throw new MpesaValidationError("Invalid M-Pesa callback: ResultCode is not a valid number");
  }

  const resultDesc = String(stk.ResultDesc || MPESA_RESULT_CODES[resultCode] || "Unknown response");
  const success = resultCode === 0;

  let mpesaReceipt: string | undefined;
  let amount: number | undefined;
  let amountCents: number | undefined;
  let phoneNumber: string | undefined;
  let transactionDate: string | undefined;
  let balance: number | undefined;

  if (success && stk.CallbackMetadata?.Item && Array.isArray(stk.CallbackMetadata.Item)) {
    const items: StkCallbackItem[] = stk.CallbackMetadata.Item;
    for (const item of items) {
      if (!item || !item.Name) continue;
      const val = item.Value;
      switch (item.Name) {
        case "MpesaReceiptNumber":
          mpesaReceipt = String(val || "").trim();
          break;
        case "Amount":
          if (typeof val === "number" || typeof val === "string") {
            amount = Number(val);
            amountCents = kesToCents(amount);
          }
          break;
        case "PhoneNumber":
          if (val) phoneNumber = String(val).trim();
          break;
        case "TransactionDate":
          if (val) transactionDate = String(val).trim();
          break;
        case "Balance":
          if (typeof val === "number" || typeof val === "string") {
            balance = Number(val);
          }
          break;
      }
    }

    if (!mpesaReceipt) {
      throw new MpesaValidationError("Successful M-Pesa transaction is missing MpesaReceiptNumber");
    }

    // If expected amount is provided, verify it strictly
    if (expectedAmountCents !== undefined && amountCents !== undefined) {
      if (amountCents !== expectedAmountCents) {
        throw new MpesaValidationError(
          `Payment amount mismatch: expected ${expectedAmountCents} cents, but received ${amountCents} cents`,
          { expectedAmountCents, receivedAmountCents: amountCents }
        );
      }
    }
  }

  return {
    merchantRequestId,
    checkoutRequestId,
    resultCode,
    resultDesc,
    success,
    mpesaReceipt,
    amount,
    amountCents,
    phoneNumber,
    transactionDate,
    balance,
  };
}
