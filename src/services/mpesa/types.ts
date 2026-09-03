/**
 * SoftMarket Kenya — M-Pesa Daraja Types
 */

export interface StkCallbackItem {
  Name: string;
  Value?: string | number;
}

export interface StkCallbackData {
  MerchantRequestID: string;
  CheckoutRequestID: string;
  ResultCode: number;
  ResultDesc: string;
  CallbackMetadata?: {
    Item: StkCallbackItem[];
  };
}

export interface StkCallbackPayload {
  Body: {
    stkCallback: StkCallbackData;
  };
}

export interface ExtractedStkData {
  merchantRequestId: string;
  checkoutRequestId: string;
  resultCode: number;
  resultDesc: string;
  success: boolean;
  mpesaReceipt?: string;
  amount?: number; // In KES
  amountCents?: number; // In Cents
  phoneNumber?: string; // e.g. 254712345678
  transactionDate?: string; // YYYYMMDDHHmmss
  balance?: number;
}

export interface C2BValidationPayload {
  TransactionType: string;
  TransID: string;
  TransTime: string;
  TransAmount: string;
  BusinessShortCode: string;
  BillRefNumber: string;
  InvoiceNumber?: string;
  OrgAccountBalance?: string;
  ThirdPartyTransID?: string;
  MSISDN: string;
  FirstName?: string;
  MiddleName?: string;
  LastName?: string;
}

export interface C2BConfirmationPayload extends C2BValidationPayload {}

export interface C2BValidationResponse {
  ResultCode: "0" | "C2B00011" | "C2B00012" | "C2B00013" | "C2B00014" | "C2B00015" | "C2B00016";
  ResultDesc: string;
}

export interface B2CCallbackPayload {
  Result: {
    ResultType: number;
    ResultCode: number;
    ResultDesc: string;
    OriginatorConversationID: string;
    ConversationID: string;
    TransactionID: string;
    ResultParameters?: {
      ResultParameter: Array<{ Key: string; Value: string | number }>;
    };
    ReferenceData?: {
      ReferenceItem: Array<{ Key: string; Value: string }>;
    };
  };
}

export interface ExtractedB2CData {
  conversationId: string;
  originatorConversationId: string;
  transactionId: string;
  resultCode: number;
  resultDesc: string;
  success: boolean;
  amount?: number;
  amountCents?: number;
  receiverPartyPublicName?: string;
  transactionCompletedDateTime?: string;
  b2cUtilityAccountAvailableFunds?: number;
  b2cWorkingAccountAvailableFunds?: number;
}
