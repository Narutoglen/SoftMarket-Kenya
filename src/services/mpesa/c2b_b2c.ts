/**
 * SoftMarket Kenya — M-Pesa C2B & B2C Handlers
 */

import { kesToCents } from "../../utils/money.js";
import { normalizeKenyanPhone } from "../../utils/phone.js";
import { MpesaValidationError } from "../../utils/errors.js";
import type {
  C2BValidationPayload,
  C2BValidationResponse,
  B2CCallbackPayload,
  ExtractedB2CData,
} from "./types.js";

/**
 * Validates C2B (Customer to Business) paybill / buygoods validation request.
 * Returns C2B response code (0 = accept, C2B00012 = reject invalid account).
 */
export function validateC2BTransaction(
  payload: C2BValidationPayload,
  accountValidator?: (billRefNumber: string, amountCents: number) => boolean
): C2BValidationResponse {
  if (!payload || !payload.TransID || !payload.TransAmount) {
    return {
      ResultCode: "C2B00011",
      ResultDesc: "Invalid C2B payload parameters",
    };
  }

  const amountKes = Number(payload.TransAmount);
  if (isNaN(amountKes) || amountKes <= 0) {
    return {
      ResultCode: "C2B00013",
      ResultDesc: "Invalid transaction amount",
    };
  }

  const amountCents = kesToCents(amountKes);
  const billRef = (payload.BillRefNumber || "").trim();

  if (accountValidator && !accountValidator(billRef, amountCents)) {
    return {
      ResultCode: "C2B00012",
      ResultDesc: `Invalid Account Reference / BillRefNumber: ${billRef}`,
    };
  }

  return {
    ResultCode: "0",
    ResultDesc: "Accepted",
  };
}

/**
 * Extracts and parses B2C (Business to Customer) payout result callback.
 */
export function validateAndExtractB2CCallback(payload: unknown): ExtractedB2CData {
  if (!payload || typeof payload !== "object") {
    throw new MpesaValidationError("B2C callback payload must be a non-null JSON object");
  }

  const raw = payload as B2CCallbackPayload;
  const result = raw.Result;
  if (!result || typeof result !== "object") {
    throw new MpesaValidationError("Invalid B2C payload: missing 'Result' root object");
  }

  const conversationId = String(result.ConversationID || "").trim();
  const originatorConversationId = String(result.OriginatorConversationID || "").trim();
  const transactionId = String(result.TransactionID || "").trim();
  const resultCode = Number(result.ResultCode);
  const resultDesc = String(result.ResultDesc || "");
  const success = resultCode === 0;

  let amount: number | undefined;
  let amountCents: number | undefined;
  let receiverPartyPublicName: string | undefined;
  let transactionCompletedDateTime: string | undefined;
  let b2cUtilityAccountAvailableFunds: number | undefined;
  let b2cWorkingAccountAvailableFunds: number | undefined;

  if (result.ResultParameters?.ResultParameter) {
    for (const param of result.ResultParameters.ResultParameter) {
      if (!param || !param.Key) continue;
      const key = param.Key;
      const val = param.Value;

      switch (key) {
        case "TransactionAmount":
          amount = Number(val);
          amountCents = kesToCents(amount);
          break;
        case "ReceiverPartyPublicName":
          receiverPartyPublicName = String(val);
          break;
        case "TransactionCompletedDateTime":
          transactionCompletedDateTime = String(val);
          break;
        case "B2CUtilityAccountAvailableFunds":
          b2cUtilityAccountAvailableFunds = Number(val);
          break;
        case "B2CWorkingAccountAvailableFunds":
          b2cWorkingAccountAvailableFunds = Number(val);
          break;
      }
    }
  }

  return {
    conversationId,
    originatorConversationId,
    transactionId,
    resultCode,
    resultDesc,
    success,
    amount,
    amountCents,
    receiverPartyPublicName,
    transactionCompletedDateTime,
    b2cUtilityAccountAvailableFunds,
    b2cWorkingAccountAvailableFunds,
  };
}
